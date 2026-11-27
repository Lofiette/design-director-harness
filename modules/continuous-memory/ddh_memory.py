#!/usr/bin/env python3
"""Portable local memory kernel. No model, network, scheduler or installer dependency.

Canonical records and archived bytes are immutable. Indexes/proposals are projections.
This is DDH's own schema, not another ledger's schema or an installed Agent Skill.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, date, time, timedelta
from itertools import chain
from zoneinfo import ZoneInfo

VERSION = "0.1.0"
OWNERS = {"profile", "toolkit", "identity"}
VISIBILITY = {"public": 0, "internal": 1, "private": 2}
KINDS = {"source", "observation", "decision", "correction", "workflow_result", "summary"}
LEVELS = {"source": 0, "episode": 1, "day": 2, "project": 3, "overview": 4}
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,180}$")
SHA = re.compile(r"^[a-f0-9]{64}$")
FINGERPRINT_FIELDS = ("provider", "model_id", "model_revision", "host_id", "host_version",
                      "toolset_digest", "context_policy_revision", "skills_catalog_digest")
EVENT_FIELDS = {"schema_version", "event_id", "owner", "kind", "level", "captured_at",
                "occurred_at", "valid_from", "valid_to", "title", "statement", "visibility",
                "basis", "sources", "raw_refs", "supersedes", "fact_key", "coverage",
                "source_locator", "workflow"}


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def stamp(value, field, nullable=False):
    if value is None and nullable:
        return None
    require(isinstance(value, str), f"{field}: timezone-aware datetime required")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Invalid(f"{field}: invalid datetime") from exc
    require(result.tzinfo is not None, f"{field}: timezone required")
    return result


def strings(values, name):
    require(isinstance(values, list) and all(isinstance(x, str) and x for x in values),
            f"{name}: non-empty strings required")
    require(len(values) == len(set(values)), f"{name}: duplicate values")


def validate_event(event):
    require(isinstance(event, dict), "event must be an object")
    require(not set(event) - EVENT_FIELDS, f"unknown event fields: {set(event) - EVENT_FIELDS}")
    required = {"schema_version", "event_id", "owner", "kind", "level", "captured_at",
                "occurred_at", "title", "statement", "visibility", "basis", "sources",
                "raw_refs", "supersedes", "coverage"}
    require(required <= set(event), f"missing event fields: {required - set(event)}")
    require(event["schema_version"] == "ddh-memory-event/1", "unsupported schema")
    require(isinstance(event["event_id"], str) and IDENTIFIER.fullmatch(event["event_id"]), "invalid event_id")
    require(event["owner"] in OWNERS, "invalid owner")
    require(event["kind"] in KINDS and event["level"] in LEVELS, "invalid kind/level")
    require(event["visibility"] in VISIBILITY, "invalid visibility")
    require(event["basis"] in {"observed", "derived", "synthetic"}, "invalid basis")
    for field in ("title", "statement"):
        require(isinstance(event[field], str) and event[field].strip(), f"{field}: empty")
    captured = stamp(event["captured_at"], "captured_at")
    stamp(event["occurred_at"], "occurred_at", nullable=True)
    vf = stamp(event.get("valid_from"), "valid_from", nullable=True)
    vt = stamp(event.get("valid_to"), "valid_to", nullable=True)
    require(not (vf and vt) or vf < vt, "validity must be [valid_from, valid_to)")
    for name in ("sources", "supersedes"):
        strings(event[name], name)
        require(all(IDENTIFIER.fullmatch(x) for x in event[name]), f"{name}: invalid ID")
        require(event["event_id"] not in event[name], f"{name}: self reference")
    require(isinstance(event["raw_refs"], list), "raw_refs must be an array")
    hashes = []
    for ref in event["raw_refs"]:
        require(isinstance(ref, dict) and set(ref) == {"sha256", "bytes"}, "invalid raw_ref fields")
        require(isinstance(ref["sha256"], str) and SHA.fullmatch(ref["sha256"]), "invalid raw hash")
        require(type(ref["bytes"]) is int and ref["bytes"] >= 0, "invalid raw byte count")
        hashes.append(ref["sha256"])
    require(len(hashes) == len(set(hashes)), "duplicate raw reference")
    coverage = event["coverage"]
    require(isinstance(coverage, dict) and set(coverage) == {"status", "limitations"}, "invalid coverage")
    require(coverage["status"] in {"captured_sources_only", "partial", "unknown"}, "invalid coverage status")
    strings(coverage["limitations"], "coverage limitations")
    if coverage["status"] != "captured_sources_only":
        require(coverage["limitations"], "partial/unknown coverage requires explanation")
    if event["kind"] == "source":
        require(event["level"] == "source", "source must have source level")
        require(event["basis"] != "derived", "source cannot be a derived summary")
        require(event["raw_refs"], "source requires archived bytes")
        require(not event["sources"] and not event["supersedes"], "raw source cannot overwrite or derive from another source")
    elif event["kind"] == "summary":
        require(LEVELS[event["level"]] >= 2, "summary level must be day, project or overview")
        require(event["basis"] in {"derived", "synthetic"}, "summary cannot become observed fact")
        require(event["sources"], "summary requires source links")
        require(not event.get("fact_key"), "summary cannot own a canonical fact")
    else:
        require(event["level"] == "episode", "non-summary record must have episode level")
        require(event["sources"] or event["raw_refs"], "episode needs evidence")
    if event["kind"] == "correction":
        require(event["supersedes"] and event.get("fact_key"), "correction requires supersedes and fact_key")
    elif event["supersedes"]:
        require(event["kind"] == "summary", "only corrections or revised summaries can supersede")
    if event.get("fact_key") is not None:
        require(isinstance(event["fact_key"], str) and IDENTIFIER.fullmatch(event["fact_key"]), "invalid fact_key")
        require(event["kind"] in {"observation", "correction", "decision"}, "invalid canonical fact kind")
        require(event["basis"] != "derived", "derived interpretation cannot silently update canonical fact")
    if "source_locator" in event:
        require(isinstance(event["source_locator"], str) and event["source_locator"].strip(), "invalid source_locator")
    if event["kind"] == "workflow_result":
        w = event.get("workflow")
        required_w = {"key", "run_id", "context_key", "acceptance", "verifier", "candidate_owner"}
        require(isinstance(w, dict) and set(w) == required_w, "invalid workflow fields")
        require(all(isinstance(w[k], str) and IDENTIFIER.fullmatch(w[k]) for k in ("key", "run_id", "context_key")), "invalid workflow identifiers")
        require(w["acceptance"] in {"pass", "fail", "blocked", "unknown"}, "invalid acceptance")
        require(w["verifier"] in {"human", "deterministic", "independent_agent", "self_report"}, "invalid verifier")
        require(w["candidate_owner"] in OWNERS, "invalid candidate owner")
    else:
        require("workflow" not in event, "workflow payload belongs to workflow_result")
    return captured


class Store:
    def __init__(self, root):
        self.root = Path(root)

    @contextmanager
    def writer(self):
        self.root.mkdir(parents=True, exist_ok=True)
        lock = self.root / ".writer-lock"
        try:
            lock.mkdir()
        except FileExistsError as exc:
            raise Invalid("store locked; inspect an interrupted writer before manually removing .writer-lock") from exc
        try:
            yield
        finally:
            lock.rmdir()

    def _file(self, event_id):
        return self.root / "events" / (digest(event_id.encode("utf-8")) + ".json")

    def _immutable(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            require(path.read_bytes() == content, f"immutable object conflict: {path.name}")
            return False
        fd, tmp = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            # All supported writes hold the directory lock. os.replace avoids exposing partial bytes.
            os.replace(tmp, path)
            if os.name == "posix":
                dfd = os.open(str(path.parent), os.O_RDONLY)
                try:
                    os.fsync(dfd)
                finally:
                    os.close(dfd)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return True

    def read(self, event_id):
        path = self._file(event_id)
        require(path.is_file(), f"missing event: {event_id}")
        wrapper = load_json(path)
        require(set(wrapper) == {"record", "record_sha256"}, "invalid record wrapper")
        event = wrapper["record"]
        require(digest(canonical(event)) == wrapper["record_sha256"], f"record hash mismatch: {event_id}")
        require(event["event_id"] == event_id, "event ID/file mismatch")
        validate_event(event)
        return event

    def all(self):
        records = {}
        for path in sorted((self.root / "events").glob("*.json")):
            wrapper = load_json(path)
            require(isinstance(wrapper, dict) and isinstance(wrapper.get("record"), dict), "invalid record wrapper")
            event_id = wrapper["record"].get("event_id")
            require(isinstance(event_id, str), "record missing ID")
            require(path == self._file(event_id), "misnamed event file")
            require(event_id not in records, "duplicate event ID")
            records[event_id] = self.read(event_id)
        return records

    def _relations(self, event, records):
        for source_id in event["sources"]:
            require(source_id in records, f"missing source: {source_id}")
            source = records[source_id]
            require(VISIBILITY[event["visibility"]] >= VISIBILITY[source["visibility"]], "implicit publication of a private/internal source is forbidden; use a separate reviewed projection")
            if event["basis"] != "synthetic":
                require(source["basis"] != "synthetic", "synthetic evidence cannot support a factual record")
            if event["kind"] == "summary":
                require(LEVELS[source["level"]] < LEVELS[event["level"]], "summary source must be a lower abstraction level")
            else:
                require(source["kind"] != "summary", "an episode/fact cannot use a summary as primary evidence")
        for old_id in event["supersedes"]:
            require(old_id in records, f"missing superseded event: {old_id}")
            old = records[old_id]
            require(old["owner"] == event["owner"], "cannot supersede another canonical owner")
            require(event["basis"] != "synthetic" or old["basis"] == "synthetic",
                    "synthetic correction cannot supersede a non-synthetic record")
            require(VISIBILITY[event["visibility"]] >= VISIBILITY[old["visibility"]],
                    "supersession cannot implicitly publish a private/internal record")
            require(stamp(old["captured_at"], "old captured_at") <= stamp(event["captured_at"], "captured_at"), "correction captured before superseded record")
            if event["kind"] == "correction":
                require(old.get("fact_key") == event["fact_key"], "correction fact_key mismatch")
            else:
                require(old["kind"] == "summary" and old["level"] == event["level"], "summary supersedes only the same level")
        # Source and supersession edges point to existing events on ingestion; verify also catches imported cycles.
        def visit(node, active, done):
            require(node not in active, "reference cycle")
            if node in done:
                return
            active.add(node)
            target = event if node == event["event_id"] else records[node]
            for child in target["sources"] + target["supersedes"]:
                require(child in records, f"missing referenced record: {child}")
                visit(child, active, done)
            active.remove(node)
            done.add(node)
        visit(event["event_id"], set(), set())

    def ingest(self, original, raw_files=(), *, raw_bytes=(), validate_records=None):
        event = copy.deepcopy(original)
        raw = []
        existing_refs = {ref["sha256"]: ref for ref in event.get("raw_refs", [])}
        file_bytes = (Path(filename).read_bytes() for filename in raw_files)
        for data in chain(file_bytes, raw_bytes):
            ref = {"sha256": digest(data), "bytes": len(data)}
            if ref["sha256"] in existing_refs:
                require(existing_refs[ref["sha256"]] == ref, "raw size mismatch")
            existing_refs[ref["sha256"]] = ref
            raw.append((ref, data))
        event["raw_refs"] = sorted(existing_refs.values(), key=lambda x: x["sha256"])
        validate_event(event)
        with self.writer():
            records = self.all()
            if event["event_id"] in records:
                require(canonical(records[event["event_id"]]) == canonical(event), "idempotency conflict: same event_id, different content")
                self.verify()  # Repetition must not hide later corruption.
                return {"status": "duplicate", "event_id": event["event_id"]}
            if validate_records is not None:
                # Check adapter-specific invariants while competing writers are excluded.
                validate_records(records)
            self._relations(event, records)
            supplied = {ref["sha256"] for ref, _ in raw}
            for ref in event["raw_refs"]:
                if ref["sha256"] not in supplied:
                    blob = self.root / "objects" / ref["sha256"]
                    require(blob.is_file(), "raw reference is not archived")
                    content = blob.read_bytes()
                    require(len(content) == ref["bytes"] and digest(content) == ref["sha256"], "raw object integrity failure")
            # An interrupted write can leave an unreferenced object, never a valid event pointing at absent bytes.
            for ref, content in raw:
                self._immutable(self.root / "objects" / ref["sha256"], content)
            wrapper = {"record": event, "record_sha256": digest(canonical(event))}
            self._immutable(self._file(event["event_id"]), canonical(wrapper))
        return {"status": "created", "event_id": event["event_id"], "record_sha256": wrapper["record_sha256"]}

    def verify(self):
        require(self.root.is_dir(), "memory store does not exist; absence is not a verified empty archive")
        records = self.all()
        references = set()
        for event in records.values():
            self._relations(event, records)
            for ref in event["raw_refs"]:
                blob = self.root / "objects" / ref["sha256"]
                require(blob.is_file(), f"missing raw object: {ref['sha256']}")
                content = blob.read_bytes()
                require(len(content) == ref["bytes"] and digest(content) == ref["sha256"], "raw object integrity failure")
                references.add(ref["sha256"])
        objects = {x.name for x in (self.root / "objects").glob("*") if x.is_file() and SHA.fullmatch(x.name)}
        return {"status": "pass", "events": len(records), "referenced_raw_objects": len(references),
                "unreferenced_objects": sorted(objects - references), "coverage": "captured_sources_only",
                "not_proven": ["all host conversations captured", "remote backup", "semantic correctness of summaries"]}

    def index(self):
        self.verify()
        records = self.all()
        superseded = {x for event in records.values() for x in event["supersedes"]}
        nodes = [{"event_id": e["event_id"], "owner": e["owner"], "level": e["level"],
                  "title": e["title"], "statement": e["statement"], "visibility": e["visibility"],
                  "sources": e["sources"], "raw_refs": e["raw_refs"],
                  "status": "superseded" if e["event_id"] in superseded else "current_record",
                  "captured_at": e["captured_at"], "occurred_at": e["occurred_at"],
                  "valid_from": e.get("valid_from"), "valid_to": e.get("valid_to"),
                  "record_sha256": digest(canonical(e))}
                 for e in records.values()]
        nodes.sort(key=lambda n: (-LEVELS[n["level"]], n["captured_at"], n["event_id"]))
        # Two unsuperseded assertions are a conflict, not "last timestamp wins".
        facts = {}
        for e in records.values():
            if e.get("fact_key") and e["event_id"] not in superseded:
                facts.setdefault((e["owner"], e["fact_key"]), []).append(e["event_id"])
        conflicts = [{"owner": k[0], "fact_key": k[1], "events": sorted(ids)} for k, ids in facts.items() if len(ids) > 1]
        return {"schema_version": "ddh-memory-index/1", "derived": True,
                "revision": digest(canonical(sorted((e["event_id"], digest(canonical(e))) for e in records.values()))),
                "nodes": nodes, "fact_conflicts": conflicts}

    def daily(self, day, timezone, cutoff="21:00"):
        self.verify()
        local_date = date.fromisoformat(day)
        zone = ZoneInfo(timezone)
        end = datetime.combine(local_date, time.fromisoformat(cutoff), zone)
        start = datetime.combine(local_date - timedelta(days=1), time.fromisoformat(cutoff), zone)
        records = self.all()
        # Use capture time for the catch-up window so late arriving material cannot silently disappear.
        selected = [e for e in records.values() if start <= stamp(e["captured_at"], "captured_at") < end]
        selected.sort(key=lambda e: (e["captured_at"], e["event_id"]))
        return {"schema_version": "ddh-daily-plan/1", "date": day, "timezone": timezone,
                "window_start_inclusive": start.isoformat(), "window_end_exclusive": end.isoformat(),
                "selection_clock": "captured_at", "event_ids": [e["event_id"] for e in selected],
                "late_arrivals": [e["event_id"] for e in selected if e["occurred_at"] and stamp(e["occurred_at"], "occurred_at") < start],
                "status": "ready_for_synthesis" if selected else "no_captured_activity",
                "public_post": None, "limitations": ["No claim of exhaustive host activity capture", "Publication and narrative synthesis are separate adapters"]}

    def lookup(self, query, owner=None, limit=8, include_history=False):
        require(isinstance(query, str) and query.strip(), "query must be non-empty")
        require(owner is None or owner in OWNERS, "invalid owner filter")
        require(type(limit) is int and 1 <= limit <= 100, "limit must be 1..100")
        tokens = query.casefold().split()
        index = self.index()
        matches = []
        for node in index["nodes"]:
            if owner and node["owner"] != owner:
                continue
            if not include_history and node["status"] == "superseded":
                continue
            haystack = (node["title"] + " " + node["statement"]).casefold()
            score = sum(token in haystack for token in tokens)
            if score:
                matches.append((LEVELS[node["level"]], score, node))
        matches.sort(key=lambda x: (-x[0], -x[1], x[2]["event_id"]))
        return {"derived": True, "index_revision": index["revision"], "retrieval": "lexical_highest_matching_abstraction_first",
                "matches": [{"event_id": n["event_id"], "owner": n["owner"], "level": n["level"],
                             "title": n["title"], "excerpt": n["statement"][:600], "sources": n["sources"],
                             "record_sha256": n["record_sha256"], "status": n["status"]}
                            for _, _, n in matches[:limit]],
                "fact_conflicts": index["fact_conflicts"], "authorization": "Local filesystem access only; this command is not a multiuser access-control service"}


def validate_registry(registry):
    require(isinstance(registry, dict) and set(registry) == {"schema_version", "skills"}, "invalid registry")
    require(registry["schema_version"] == "ddh-skill-registry/1" and isinstance(registry["skills"], list), "invalid registry schema")
    ids = set()
    for skill in registry["skills"]:
        require(isinstance(skill, dict) and set(skill) == {"skill_id", "owner", "status", "revision", "workflow_keys"}, "invalid skill registry entry")
        require(isinstance(skill["skill_id"], str) and IDENTIFIER.fullmatch(skill["skill_id"]), "invalid skill ID")
        require(skill["skill_id"] not in ids, "duplicate skill ID")
        ids.add(skill["skill_id"])
        require(skill["owner"] in OWNERS and skill["status"] in {"active", "candidate", "retired"}, "invalid skill owner/status")
        require(isinstance(skill["revision"], str) and skill["revision"], "skill revision required")
        strings(skill["workflow_keys"], "workflow keys")
    return registry


def skill_candidates(store, registry, min_successes=3, min_contexts=2):
    require(type(min_successes) is int and min_successes >= 2, "min_successes must be >=2")
    require(type(min_contexts) is int and min_contexts >= 1, "min_contexts must be >=1")
    validate_registry(registry)
    store.verify()
    groups = {}
    ignored = []
    by_run = {}
    for e in store.all().values():
        if e["kind"] != "workflow_result":
            continue
        w = e["workflow"]
        by_run.setdefault((w["candidate_owner"], w["key"], w["run_id"]), []).append(e)
    ambiguous_runs = []
    for run_key, emissions in by_run.items():
        signatures = {canonical([e["workflow"], e["basis"]]) for e in emissions}
        if len(signatures) != 1:
            ambiguous_runs.append({"owner": run_key[0], "workflow_key": run_key[1], "run_id": run_key[2],
                                   "event_ids": sorted(e["event_id"] for e in emissions)})
            ignored.extend(e["event_id"] for e in emissions)
            continue
        e = emissions[0]
        w = e["workflow"]
        if e["basis"] != "observed" or w["acceptance"] != "pass" or w["verifier"] == "self_report":
            ignored.extend(x["event_id"] for x in emissions)
            continue
        groups.setdefault((w["candidate_owner"], w["key"]), []).extend(emissions)
    proposals = []
    for (owner, key), events in sorted(groups.items()):
        runs = {e["workflow"]["run_id"] for e in events}
        contexts = {e["workflow"]["context_key"] for e in events}
        if len(runs) < min_successes or len(contexts) < min_contexts:
            continue
        existing = [s for s in registry["skills"] if s["owner"] == owner and key in s["workflow_keys"] and s["status"] != "retired"]
        evidence = sorted(e["event_id"] for e in events)
        proposals.append({"proposal_id": "workflow-" + digest(canonical([owner, key, evidence]))[:20],
                          "action": "review_existing" if existing else "author_candidate", "owner": owner,
                          "workflow_key": key, "status": "proposed", "independent_runs": len(runs),
                          "contexts": len(contexts), "evidence_event_ids": evidence,
                          "existing_skill_ids": [s["skill_id"] for s in existing],
                          "visibility": max((e["visibility"] for e in events), key=VISIBILITY.get),
                          "required_next_steps": ["Extract reusable procedure from original evidence", "Remove instance facts from generic procedure",
                                                  "Check overlap and actual host discovery", "Run paired holdout evaluation with and without the candidate"],
                          "automatic_activation": False})
    return {"schema_version": "ddh-skill-proposals/1", "derived": True, "policy": {"min_successes": min_successes, "min_contexts": min_contexts, "status": "configurable_starting_rule_not_research_threshold"},
            "proposals": proposals, "ignored_event_ids": sorted(ignored), "ambiguous_runs": ambiguous_runs,
            "catalog_scope": "provided_registry_only", "registry_entry_count": len(registry["skills"]),
            "active_catalog_coverage": "unknown", "native_provider_discovery": "not_performed",
            "automatic_deletions": []}


def validate_fingerprint(fp):
    required = set(FINGERPRINT_FIELDS) | {"schema_version", "observed_at", "evidence"}
    require(isinstance(fp, dict) and set(fp) == required, "invalid fingerprint fields")
    require(fp["schema_version"] == "ddh-environment-fingerprint/1", "invalid fingerprint schema")
    stamp(fp["observed_at"], "fingerprint observed_at")
    for field in FINGERPRINT_FIELDS:
        require(fp[field] is None or isinstance(fp[field], str) and fp[field].strip(), f"invalid fingerprint {field}")
    require(isinstance(fp["evidence"], str) and fp["evidence"].strip(), "fingerprint evidence locator required")


def model_scan(previous, current, registry):
    validate_fingerprint(current)
    validate_registry(registry)
    if previous is not None:
        validate_fingerprint(previous)
    changed, unknown, newly_observable = [], [], []
    for field in FINGERPRINT_FIELDS:
        before = previous[field] if previous else None
        after = current[field]
        if after is None:
            unknown.append(field)
        elif before is None:
            newly_observable.append(field)
        elif before != after:
            changed.append({"field": field, "before": before, "after": after})
    if changed:
        status = "observed_configuration_change"
    elif previous is None:
        status = "baseline_needed"
    elif newly_observable:
        status = "newly_observable_dimensions"
    elif unknown:
        status = "unchanged_observed_dimensions_hidden_dimensions_unknown"
    else:
        status = "unchanged_observed_fingerprint"
    needs_review = bool(changed or newly_observable or previous is None)
    proposals = [{"skill_id": s["skill_id"], "owner": s["owner"], "revision": s["revision"],
                  "action": "revalidate", "status": "proposed", "reason": status,
                  "evaluation": "paired same-task same-input with/without skill plus held-out trigger tests",
                  "automatic_activation": False}
                 for s in registry["skills"] if s["status"] == "active" and needs_review]
    return {"schema_version": "ddh-model-scan/1", "status": status, "changed": changed,
            "unknown_dimensions": unknown, "newly_observable_dimensions": newly_observable,
            "catalog_scope": "provided_registry_only", "registry_entry_count": len(registry["skills"]),
            "active_catalog_coverage": "unknown", "native_provider_discovery": "not_performed",
            "model_update_confirmed": any(c["field"] in {"provider", "model_id", "model_revision"} for c in changed),
            "hidden_provider_rollout_detection": "unsupported", "proposals": proposals,
            "automatic_deletions": [], "retirement_policy": "Retirement requires separate comparative evidence and an explicit accepted proposal; version change alone is insufficient"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("ingest", "verify", "index", "get", "lookup", "daily", "skill-candidates"):
        p = sub.add_parser(name)
        p.add_argument("--store", required=True)
        if name == "ingest":
            p.add_argument("--event", required=True)
            p.add_argument("--raw", action="append", default=[])
        if name == "daily":
            p.add_argument("--date", required=True)
            p.add_argument("--timezone", required=True)
            p.add_argument("--cutoff", default="21:00")
        if name == "get":
            p.add_argument("--event-id", required=True)
        if name == "lookup":
            p.add_argument("--query", required=True)
            p.add_argument("--owner", choices=sorted(OWNERS))
            p.add_argument("--limit", type=int, default=8)
            p.add_argument("--include-history", action="store_true")
        if name == "skill-candidates":
            p.add_argument("--registry", required=True)
            p.add_argument("--min-successes", type=int, default=3)
            p.add_argument("--min-contexts", type=int, default=2)
    p = sub.add_parser("model-scan")
    p.add_argument("--previous")
    p.add_argument("--current", required=True)
    p.add_argument("--registry", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "model-scan":
            result = model_scan(load_json(args.previous) if args.previous else None, load_json(args.current), load_json(args.registry))
        else:
            store = Store(args.store)
            if args.command == "ingest":
                result = store.ingest(load_json(args.event), args.raw)
            elif args.command == "verify":
                result = store.verify()
            elif args.command == "index":
                result = store.index()
            elif args.command == "get":
                store.verify()
                result = store.read(args.event_id)
            elif args.command == "lookup":
                result = store.lookup(args.query, args.owner, args.limit, args.include_history)
            elif args.command == "daily":
                result = store.daily(args.date, args.timezone, args.cutoff)
            else:
                result = skill_candidates(store, load_json(args.registry), args.min_successes, args.min_contexts)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (Invalid, ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
