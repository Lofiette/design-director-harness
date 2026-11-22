"""Synthetic contract/failure tests; these are not a live agent or host evaluation."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "context_pack.py"
spec = importlib.util.spec_from_file_location("ddh_context_pack", MODULE)
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)


class ContextPackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "input"
        self.root.mkdir()
        self.raw = b"# Compact source\r\nOne exact byte stream.\r\n"
        self.more = "# Detailed source\nДополнительное свидетельство.\n".encode()
        (self.root / "core.md").write_bytes(self.raw)
        (self.root / "detail.md").write_bytes(self.more)
        self.manifest = {
            "schema_version": cp.MANIFEST_SCHEMA, "mode": "pinned_snapshot",
            "task": {"id": "test.task", "objective": "Continue a synthetic task.", "next_action": "Read selected evidence."},
            "repositories": {"profile": {"repository": "example/profile", "revision": "1" * 40, "visibility": "private"}},
            "documents": [self.doc("core", "core.md", self.raw), self.doc("detail", "detail.md", self.more)],
            "startup": ["core"], "routes": {"evidence": ["detail", "core"]}, "max_utf8_bytes": 32000,
        }
        self.roots = {"profile": self.root}
        self.output = self.base / "bundle"

    def doc(self, id, path, raw):
        return {"id": id, "owner": "profile", "path": path, "role": "evidence", "visibility": "private",
                "git_blob_sha": cp.blob_digest(raw), "sha256": cp.digest(raw), "reason": "Synthetic test source."}

    def build(self, **kw):
        return cp.build(self.manifest, self.roots, self.output, source_mode="export", **kw)

    def test_deterministic_bytes_independent_of_local_roots_and_idempotent_retry(self):
        first = self.build()
        second = self.build()
        another_root = self.base / "moved"
        shutil.copytree(self.root, another_root)
        third = cp.build(self.manifest, {"profile": another_root}, self.base / "bundle2", source_mode="export")
        self.assertEqual(first, second)
        self.assertEqual(first, third)
        self.assertEqual((self.output / "context-pack.md").read_bytes(), (self.base / "bundle2/context-pack.md").read_bytes())
        self.assertEqual((self.output / cp.stored_path("core")).read_bytes(), self.raw)
        self.assertNotIn(str(self.root), json.dumps(first))

    def test_unselected_source_not_read_and_explicit_route_requires_it(self):
        (self.root / "detail.md").unlink()
        first = self.build()
        self.assertEqual(first["deferred_ids"], ["detail"])
        self.assertNotIn("Дополнительное свидетельство", (self.output / "context-pack.md").read_text())
        with self.assertRaises(FileNotFoundError):
            cp.build(self.manifest, self.roots, self.base / "route", source_mode="export", route="evidence")
        self.assertFalse((self.base / "route").exists())

    def test_route_stable_dedup(self):
        receipt = self.build(route="evidence")
        self.assertEqual([x["id"] for x in receipt["included_sources"]], ["core", "detail"])
        self.assertEqual(receipt["deferred_ids"], [])

    def test_changed_source_fails_before_output(self):
        (self.root / "core.md").write_bytes(self.raw + b"modified")
        with self.assertRaisesRegex(cp.Invalid, "SHA-256 mismatch"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_incorrect_blob_pin_fails_independently_of_sha256(self):
        self.manifest["documents"][0]["git_blob_sha"] = "2" * 40
        with self.assertRaisesRegex(cp.Invalid, "Git blob mismatch"):
            self.build()

    def test_missing_required_source_and_missing_root_fail(self):
        with self.assertRaisesRegex(cp.Invalid, "missing source root"):
            cp.build(self.manifest, {}, self.output, source_mode="export")
        (self.root / "core.md").unlink()
        with self.assertRaises(FileNotFoundError):
            self.build()
        self.assertFalse(self.output.exists())

    def test_budget_failure_never_truncates_or_publishes(self):
        with self.assertRaisesRegex(cp.Invalid, "budget_exceeded"):
            self.build(max_bytes=100)
        self.assertFalse(self.output.exists())
        receipt = self.build()
        self.assertEqual(receipt["context_utf8_bytes"], len((self.output / "context-pack.md").read_bytes()))
        self.assertIsNone(receipt["token_count"])

    def test_traversal_and_symlink_escape_are_rejected(self):
        for path in ["../core.md", "/core.md", "a/../../core.md", "a\\core.md", "a/./core.md", "C:/core.md"]:
            with self.subTest(path=path):
                manifest = copy.deepcopy(self.manifest)
                manifest["documents"][0]["path"] = path
                with self.assertRaises(cp.Invalid):
                    cp.validate_manifest(manifest)
        (self.root / "core.md").unlink()
        external = self.base / "external.md"
        external.write_bytes(self.raw)
        (self.root / "core.md").symlink_to(external)
        with self.assertRaisesRegex(cp.Invalid, "symlink"):
            self.build()

    def test_private_output_cannot_be_put_in_public_source_tree(self):
        self.manifest["repositories"]["profile"]["visibility"] = "public"
        with self.assertRaisesRegex(cp.Invalid, "public source root"):
            cp.build(self.manifest, self.roots, self.root / "output", source_mode="export")
        receipt = self.build()
        self.assertEqual(receipt["visibility"], "private")
        self.assertEqual(receipt["included_sources"][0]["visibility"], "private")

    def test_changed_pack_raw_or_receipt_fails_verification(self):
        self.build()
        for relative in ["context-pack.md", cp.stored_path("core"), "context-pack.receipt.json"]:
            with self.subTest(file=relative):
                path = self.output / relative
                before = path.read_bytes()
                if relative.endswith("receipt.json"):
                    data = json.loads(before)
                    data["assurance"]["automatic_capture"] = "connected"
                    path.write_bytes(cp.canonical(data))
                else:
                    path.write_bytes(before + b"tampered")
                with self.assertRaises(cp.Invalid):
                    cp.verify_bundle(self.output)
                path.write_bytes(before)
        self.assertEqual(cp.verify_bundle(self.output)["assurance"]["automatic_capture"], "not_connected")

    def test_output_conflict_preserves_previous_bundle(self):
        first = self.build()
        before = (self.output / "context-pack.md").read_bytes()
        self.manifest["task"]["next_action"] = "Different next action."
        with self.assertRaisesRegex(cp.Invalid, "different bundle"):
            self.build()
        self.assertEqual(before, (self.output / "context-pack.md").read_bytes())
        self.assertEqual(first, cp.verify_bundle(self.output))

    def test_supplied_observed_head_reports_drift_without_claiming_live_state(self):
        self.manifest["observed_heads"] = {"profile": {"revision": "2" * 40, "observed_at": "2026-01-01T12:00:00Z", "basis": "Synthetic provided observation."}}
        receipt = self.build()
        self.assertEqual(receipt["head_comparison"]["profile"]["status"], "differs_from_supplied_observation")
        self.assertEqual(receipt["assurance"]["remote_attestation"], "not_performed")

    def test_cli_get_exact_bytes_and_separate_receipt(self):
        manifest_path = self.base / "manifest.json"
        manifest_path.write_bytes(cp.canonical(self.manifest))
        result = subprocess.run([sys.executable, str(MODULE), "get", "--manifest", str(manifest_path),
                                 "--root", "profile=" + str(self.root), "--source-mode", "export", "--id", "core"], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, self.raw)
        self.assertEqual(json.loads(result.stderr)["sha256"], cp.digest(self.raw))

    def test_invalid_or_missing_revision_never_becomes_main(self):
        self.manifest["repositories"]["profile"]["revision"] = "main"
        with self.assertRaisesRegex(cp.Invalid, "exact commit"):
            self.build()

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_git_reads_pinned_commit_instead_of_dirty_worktree(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"], check=True)
        commit = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"]).decode().strip()
        self.manifest["repositories"]["profile"]["revision"] = commit
        (self.root / "core.md").write_bytes(b"dirty worktree must not replace pinned bytes")
        receipt = cp.build(self.manifest, self.roots, self.output, source_mode="git")
        self.assertEqual((self.output / cp.stored_path("core")).read_bytes(), self.raw)
        self.assertEqual(receipt["assurance"]["source_revision_membership"], "verified_in_local_git_objects")
        self.manifest["repositories"]["profile"]["revision"] = "4" * 40
        with self.assertRaises(cp.Invalid):
            cp.build(self.manifest, self.roots, self.base / "missing_commit", source_mode="git")

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_git_symlink_blob_is_rejected(self):
        (self.root / "core.md").unlink()
        (self.root / "core.md").symlink_to("detail.md")
        raw = b"detail.md"
        self.manifest["documents"][0] = self.doc("core", "core.md", raw)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "symlink fixture"], check=True)
        self.manifest["repositories"]["profile"]["revision"] = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"]).decode().strip()
        with self.assertRaisesRegex(cp.Invalid, "ordinary Git blob"):
            cp.build(self.manifest, self.roots, self.output, source_mode="git")


if __name__ == "__main__":
    unittest.main()
