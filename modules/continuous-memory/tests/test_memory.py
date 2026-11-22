"""Synthetic fixtures only; these are not user observations or live agent runs."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "ddh_memory.py"
SPEC = importlib.util.spec_from_file_location("ddh_memory", MODULE)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def event(identifier, **changes):
    result = {"schema_version": "ddh-memory-event/1", "event_id": identifier,
              "owner": "profile", "kind": "source", "level": "source",
              "captured_at": "2030-01-02T12:00:00+00:00", "occurred_at": None,
              "title": "Synthetic test source", "statement": "This fixture is not a real observation.",
              "visibility": "private", "basis": "synthetic", "sources": [], "raw_refs": [],
              "supersedes": [], "coverage": {"status": "captured_sources_only", "limitations": []}}
    result.update(changes)
    return result


def fingerprint(**changes):
    result = {"schema_version": "ddh-environment-fingerprint/1", "observed_at": "2030-01-02T12:00:00+00:00",
              "evidence": "synthetic:test:host-observation", **{field: None for field in m.FINGERPRINT_FIELDS}}
    result.update(changes)
    return result


REGISTRY = {"schema_version": "ddh-skill-registry/1", "skills": [
    {"skill_id": "example-skill", "owner": "toolkit", "status": "active", "revision": "synthetic-v1", "workflow_keys": ["existing-workflow"]}]}


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.store = m.Store(self.base / "store")
        self.raw = self.base / "raw.txt"
        self.raw.write_bytes("Исходные байты.\n".encode("utf-8"))

    def tearDown(self):
        self.tmp.cleanup()

    def source(self, identifier="source-1", **changes):
        return self.store.ingest(event(identifier, **changes), [self.raw])

    def episode(self, identifier, **changes):
        fields = {"kind": "observation", "level": "episode", "sources": ["source-1"]}
        fields.update(changes)
        return self.store.ingest(event(identifier, **fields))

    def test_exact_bytes_and_idempotency(self):
        first = self.source()
        second = self.source()
        self.assertEqual(first["status"], "created")
        self.assertEqual(second["status"], "duplicate")
        self.assertEqual(self.store.verify()["events"], 1)
        ref = self.store.read("source-1")["raw_refs"][0]
        self.assertEqual((self.store.root / "objects" / ref["sha256"]).read_bytes(), self.raw.read_bytes())

    def test_same_id_cannot_overwrite(self):
        self.source()
        with self.assertRaisesRegex(m.Invalid, "idempotency conflict"):
            self.source(statement="Different contents")
        self.assertEqual(self.store.verify()["events"], 1)

    def test_changed_raw_bytes_same_id_rejected(self):
        self.source()
        self.raw.write_text("Changed", encoding="utf-8")
        with self.assertRaisesRegex(m.Invalid, "idempotency conflict"):
            self.source()

    def test_raw_integrity_failure_is_visible(self):
        self.source()
        ref = self.store.read("source-1")["raw_refs"][0]
        (self.store.root / "objects" / ref["sha256"]).write_bytes(b"corrupt")
        with self.assertRaisesRegex(m.Invalid, "integrity"):
            self.store.verify()

    def test_missing_raw_is_rejected(self):
        ref = {"sha256": "a" * 64, "bytes": 10}
        with self.assertRaisesRegex(m.Invalid, "not archived"):
            self.store.ingest(event("missing-raw", raw_refs=[ref]))
        self.assertEqual(len(self.store.all()), 0)

    def test_missing_source_is_rejected(self):
        with self.assertRaisesRegex(m.Invalid, "missing source"):
            self.episode("dangling")

    def test_correction_preserves_old_record(self):
        self.source()
        self.episode("old", fact_key="career.start", statement="Earlier assertion")
        old_bytes = self.store._file("old").read_bytes()
        self.episode("new", kind="correction", fact_key="career.start", supersedes=["old"], statement="Corrected assertion")
        self.assertEqual(old_bytes, self.store._file("old").read_bytes())
        statuses = {n["event_id"]: n["status"] for n in self.store.index()["nodes"]}
        self.assertEqual(statuses["old"], "superseded")
        self.assertEqual(statuses["new"], "current_record")

    def test_correction_wrong_owner_rejected(self):
        self.source()
        self.episode("old", fact_key="career.start")
        with self.assertRaisesRegex(m.Invalid, "another canonical owner"):
            self.episode("new", owner="identity", kind="correction", fact_key="career.start", supersedes=["old"])

    def test_correction_wrong_fact_rejected(self):
        self.source()
        self.episode("old", fact_key="career.start")
        with self.assertRaisesRegex(m.Invalid, "fact_key mismatch"):
            self.episode("new", kind="correction", fact_key="career.role", supersedes=["old"])

    def test_synthetic_correction_cannot_displace_observed_fact(self):
        self.source(basis="observed")
        self.episode("old", basis="observed", fact_key="career.start")
        with self.assertRaisesRegex(m.Invalid, "synthetic correction"):
            self.episode("new", basis="synthetic", kind="correction", fact_key="career.start", supersedes=["old"])
        active = [n for n in self.store.index()["nodes"] if n["event_id"] == "old"]
        self.assertEqual(active[0]["status"], "current_record")

    def test_supersession_cannot_bypass_source_visibility(self):
        self.source("source-1", basis="observed")
        self.source("source-public", basis="observed", visibility="public")
        self.episode("old", basis="observed", fact_key="career.start")
        with self.assertRaisesRegex(m.Invalid, "supersession cannot implicitly publish"):
            self.episode("new", basis="observed", kind="correction", sources=["source-public"], visibility="public", fact_key="career.start", supersedes=["old"])

    def test_conflicting_facts_are_not_last_write_wins(self):
        self.source()
        self.episode("one", fact_key="career.start")
        self.episode("two", fact_key="career.start")
        self.assertEqual(self.store.index()["fact_conflicts"][0]["events"], ["one", "two"])

    def test_summary_can_drill_down_without_deleting_source(self):
        self.source()
        self.episode("episode")
        self.store.ingest(event("day", kind="summary", level="day", sources=["episode"]))
        self.store.ingest(event("project", kind="summary", level="project", sources=["day"]))
        self.store.ingest(event("overview", kind="summary", level="overview", sources=["project"]))
        index = self.store.index()
        self.assertEqual(index["nodes"][0]["event_id"], "overview")
        self.assertEqual(self.store.verify()["events"], 5)
        self.assertEqual(self.store.read("overview")["sources"], ["project"])
        self.assertEqual(self.store.read("source-1")["raw_refs"][0]["bytes"], len(self.raw.read_bytes()))

    def test_summary_cannot_become_factual_source(self):
        self.source()
        self.store.ingest(event("day", kind="summary", level="day", sources=["source-1"]))
        with self.assertRaisesRegex(m.Invalid, "summary as primary evidence"):
            self.episode("false-fact", sources=["day"])

    def test_lookup_starts_from_high_abstraction_and_keeps_source_links(self):
        self.source(title="Design evidence")
        self.episode("episode", title="Design decision")
        self.store.ingest(event("day", kind="summary", level="day", sources=["episode"], title="Design daily summary"))
        self.store.ingest(event("overview", kind="summary", level="overview", sources=["day"], title="Design overview"))
        result = self.store.lookup("design", owner="profile", limit=2)
        self.assertEqual([n["event_id"] for n in result["matches"]], ["overview", "day"])
        self.assertEqual(result["matches"][0]["sources"], ["day"])

    def test_summary_cannot_own_fact(self):
        self.source()
        with self.assertRaisesRegex(m.Invalid, "summary cannot own"):
            self.store.ingest(event("day", kind="summary", level="day", sources=["source-1"], fact_key="x"))

    def test_no_implicit_publication(self):
        self.source()
        with self.assertRaisesRegex(m.Invalid, "implicit publication"):
            self.episode("public-post", visibility="public")

    def test_synthetic_evidence_cannot_support_observed_fact(self):
        self.source()
        with self.assertRaisesRegex(m.Invalid, "synthetic evidence"):
            self.episode("real-claim", basis="observed")

    def test_unknown_timezone_and_naive_datetime_fail(self):
        with self.assertRaises(m.Invalid):
            self.source(captured_at="2030-01-02T12:00:00")
        self.store.root.mkdir()
        with self.assertRaises(KeyError):
            self.store.daily("2030-01-02", "Not/AZone")

    def test_missing_store_is_not_a_verified_empty_day(self):
        with self.assertRaisesRegex(m.Invalid, "does not exist"):
            self.store.verify()
        with self.assertRaisesRegex(m.Invalid, "does not exist"):
            self.store.daily("2030-01-02", "Europe/Moscow")

    def test_daily_boundary_and_late_arrival(self):
        self.source("at-start", captured_at="2030-01-01T18:00:00Z")
        self.source("inside", captured_at="2030-01-02T17:59:59Z", occurred_at="2029-12-28T12:00:00Z")
        self.source("at-end", captured_at="2030-01-02T18:00:00Z")
        plan = self.store.daily("2030-01-02", "Europe/Moscow")
        self.assertEqual(plan["event_ids"], ["at-start", "inside"])
        self.assertEqual(plan["late_arrivals"], ["inside"])
        self.assertEqual(plan["window_end_exclusive"], "2030-01-02T21:00:00+03:00")

    def test_writer_lock_fails_closed(self):
        self.store.root.mkdir()
        (self.store.root / ".writer-lock").mkdir()
        with self.assertRaisesRegex(m.Invalid, "store locked"):
            self.source()
        self.assertEqual(len(self.store.all()), 0)

    def test_tampered_record_fails_digest(self):
        self.source()
        path = self.store._file("source-1")
        wrapper = m.load_json(path)
        wrapper["record"]["statement"] = "tampered"
        path.write_text(json.dumps(wrapper), encoding="utf-8")
        with self.assertRaisesRegex(m.Invalid, "hash mismatch"):
            self.store.verify()

    def test_imported_cycle_rejected(self):
        self.source()
        self.episode("a")
        self.episode("b", sources=["a"])
        path = self.store._file("a")
        wrapper = m.load_json(path)
        wrapper["record"]["sources"] = ["b"]
        wrapper["record_sha256"] = m.digest(m.canonical(wrapper["record"]))
        path.write_bytes(m.canonical(wrapper))
        with self.assertRaisesRegex(m.Invalid, "cycle"):
            self.store.verify()

    def test_no_candidates_from_synthetic_or_self_report(self):
        self.source()
        for i in range(5):
            self.episode(f"run-{i}", kind="workflow_result", workflow={"key": "flow", "run_id": f"run-{i}", "context_key": f"ctx-{i}", "acceptance": "pass", "verifier": "human", "candidate_owner": "toolkit"})
        result = m.skill_candidates(self.store, REGISTRY)
        self.assertEqual(result["proposals"], [])
        self.assertEqual(len(result["ignored_event_ids"]), 5)

    def test_observed_fixture_branch_counts_runs_not_emissions(self):
        # Temporarily labelled observed to test that branch only; no fixture is exported as factual data.
        self.source(basis="observed")
        for i in range(4):
            self.episode(f"run-{i}", basis="observed", kind="workflow_result", workflow={"key": "flow", "run_id": f"run-{min(i, 2)}", "context_key": f"ctx-{min(i, 2) % 2}", "acceptance": "pass", "verifier": "deterministic", "candidate_owner": "toolkit"})
        result = m.skill_candidates(self.store, REGISTRY)
        self.assertEqual(len(result["proposals"]), 1)
        self.assertEqual(result["proposals"][0]["independent_runs"], 3)
        self.assertEqual(result["proposals"][0]["visibility"], "private")
        self.assertFalse(result["proposals"][0]["automatic_activation"])

    def test_duplicate_workflow_uses_existing_skill(self):
        self.source(basis="observed")
        for i in range(3):
            self.episode(f"run-{i}", basis="observed", kind="workflow_result", workflow={"key": "existing-workflow", "run_id": f"run-{i}", "context_key": f"ctx-{i}", "acceptance": "pass", "verifier": "human", "candidate_owner": "toolkit"})
        proposal = m.skill_candidates(self.store, REGISTRY)["proposals"][0]
        self.assertEqual(proposal["action"], "review_existing")
        self.assertEqual(proposal["existing_skill_ids"], ["example-skill"])

    def test_conflicting_run_reports_do_not_become_skill_evidence(self):
        self.source(basis="observed")
        for i in range(3):
            self.episode(f"run-{i}", basis="observed", kind="workflow_result", workflow={"key": "flow", "run_id": f"run-{i}", "context_key": f"ctx-{i}", "acceptance": "pass", "verifier": "human", "candidate_owner": "toolkit"})
        self.episode("run-2-conflict", basis="observed", kind="workflow_result", workflow={"key": "flow", "run_id": "run-2", "context_key": "ctx-2", "acceptance": "fail", "verifier": "human", "candidate_owner": "toolkit"})
        result = m.skill_candidates(self.store, REGISTRY)
        self.assertEqual(result["proposals"], [])
        self.assertEqual(result["ambiguous_runs"][0]["run_id"], "run-2")


class FingerprintTests(unittest.TestCase):
    def test_empty_registry_does_not_claim_empty_active_catalog(self):
        registry = {"schema_version": "ddh-skill-registry/1", "skills": []}
        result = m.model_scan(None, fingerprint(), registry)
        self.assertEqual(result["registry_entry_count"], 0)
        self.assertEqual(result["active_catalog_coverage"], "unknown")
        self.assertEqual(result["native_provider_discovery"], "not_performed")

    def test_hidden_model_revision_remains_unknown(self):
        fp = fingerprint(provider="example-provider", model_id="stable-alias")
        result = m.model_scan(fp, fp, REGISTRY)
        self.assertFalse(result["model_update_confirmed"])
        self.assertIn("model_revision", result["unknown_dimensions"])
        self.assertEqual(result["hidden_provider_rollout_detection"], "unsupported")

    def test_model_change_proposes_revalidation_not_deletion(self):
        old = fingerprint(provider="example-provider", model_id="model-a", model_revision="version-1")
        new = fingerprint(provider="example-provider", model_id="model-a", model_revision="version-2")
        original_registry = copy.deepcopy(REGISTRY)
        result = m.model_scan(old, new, REGISTRY)
        self.assertTrue(result["model_update_confirmed"])
        self.assertEqual(result["proposals"][0]["action"], "revalidate")
        self.assertEqual(result["automatic_deletions"], [])
        self.assertEqual(REGISTRY, original_registry)

    def test_host_change_not_called_model_update(self):
        old = fingerprint(host_id="example-host", host_version="one")
        new = fingerprint(host_id="example-host", host_version="two")
        result = m.model_scan(old, new, REGISTRY)
        self.assertEqual(result["status"], "observed_configuration_change")
        self.assertFalse(result["model_update_confirmed"])

    def test_newly_observed_revision_not_claimed_upgrade(self):
        old = fingerprint(model_id="model-a")
        new = fingerprint(model_id="model-a", model_revision="now-visible")
        result = m.model_scan(old, new, REGISTRY)
        self.assertFalse(result["model_update_confirmed"])
        self.assertEqual(result["status"], "newly_observable_dimensions")


if __name__ == "__main__":
    unittest.main()
