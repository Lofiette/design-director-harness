"""Synthetic filesystem/command fixtures; no real native startup or model runs."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "host_preflight.py"
SPEC = importlib.util.spec_from_file_location("host_preflight", MODULE)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class HostPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.binary = self.root / "trusted-codex"
        self.binary.write_text("Synthetic placeholder, never executed.\n", encoding="utf-8")
        self.binary.chmod(0o700)
        self.help_results = [
            subprocess.CompletedProcess([], 0, "codex-cli 0.172.0-alpha.2\n", ""),
            subprocess.CompletedProcess([], 0, "Usage: codex exec [OPTIONS]\n--json --ephemeral --output-schema", ""),
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def test_unknown_state_cannot_be_complete(self):
        with patch.object(m.subprocess, "run", side_effect=self.help_results):
            report = m.preflight(self.root, self.root / "future.json", [], self.root, self.binary)
        self.assertEqual(report["status"], "incomplete")
        self.assertIn("state_location_unknown", report["unknowns"])
        self.assertEqual(m.exit_code(report), 3)
        self.assertEqual(report["native_startup"]["status"], "not_run")

    def test_complete_metadata_is_not_a_write_or_startup_test(self):
        with patch.object(m.subprocess, "run", side_effect=self.help_results):
            report = m.preflight(self.root, self.root / "future.json", [self.root], self.root, self.binary)
        self.assertEqual(report["status"], "metadata_checks_complete_only")
        self.assertEqual(m.exit_code(report), 0)
        self.assertEqual(report["actual_write_probe"], "not_run")
        self.assertEqual(report["native_startup"]["status"], "not_run")
        self.assertFalse((self.root / "future.json").exists())

    def test_readonly_mount_overrides_positive_access_metadata(self):
        volume = SimpleNamespace(f_flag=getattr(os, "ST_RDONLY", 1), f_bavail=100, f_frsize=4096)
        with patch.object(m.os, "access", return_value=True), patch.object(m.os, "statvfs", return_value=volume, create=True), patch.object(m.os, "ST_RDONLY", 1, create=True):
            report = m.preflight(self.root, self.root, [self.root], self.root, None)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["paths"][0]["status"], "filesystem_readonly")
        self.assertEqual(m.exit_code(report), 1)

    def test_missing_output_parents_are_not_created(self):
        output = self.root / "absent" / "nested" / "result.json"
        report = m.preflight(self.root, output, [self.root], self.root, None)
        item = report["paths"][1]
        self.assertEqual(item["status"], "parent_metadata_writable_missing_directories")
        self.assertEqual(item["missing_parent_directories"], 2)
        self.assertFalse((self.root / "absent").exists())

    def test_no_file_contents_or_directory_listing_needed(self):
        with patch("builtins.open", side_effect=AssertionError("File contents must not be read")), patch.object(Path, "iterdir", side_effect=AssertionError("Directory must not be listed")), patch.object(Path, "read_bytes", side_effect=AssertionError("No reads")), patch.object(Path, "read_text", side_effect=AssertionError("No reads")):
            report = m.preflight(self.root, self.root / "result.json", [], self.root, None)
        self.assertEqual(report["paths"][0]["status"], "metadata_writable")

    def test_only_exact_help_commands_execute_and_no_env_override(self):
        with patch.object(m.subprocess, "run", side_effect=self.help_results) as runner:
            result = m.inspect_codex(self.binary, self.root, True)
        self.assertEqual([call.args[0] for call in runner.call_args_list], [
            [str(self.binary), "--version"], [str(self.binary), "exec", "--help"]])
        for call in runner.call_args_list:
            self.assertFalse(call.kwargs["shell"])
            self.assertNotIn("env", call.kwargs)
            self.assertEqual(call.kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(result["status"], "cli_help_ok")
        self.assertEqual(result["version"], "0.172.0-alpha.2")

    def test_failed_binary_output_is_not_disclosed(self):
        with patch.object(m.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "secret-stdout", "secret-stderr")) as runner:
            result = m.inspect_codex(self.binary, self.root, True)
        self.assertEqual(result["status"], "cli_help_failed")
        self.assertEqual(runner.call_count, 1)
        self.assertNotIn("secret", json.dumps(result))

    def test_help_option_prefixes_do_not_count_as_exact_flags(self):
        help_output = "Usage: codex exec [OPTIONS]\n--jsonl --ephemeral-session --output-schema-file --remote-config"
        replies = [self.help_results[0], subprocess.CompletedProcess([], 0, help_output, "")]
        with patch.object(m.subprocess, "run", side_effect=replies):
            result = m.inspect_codex(self.binary, self.root, True)
        self.assertEqual(result["status"], "cli_help_ok")
        self.assertEqual(result["help_flags_observed"], [])

    def test_timeout_does_not_retry_or_emit_captured_output(self):
        failure = subprocess.TimeoutExpired([str(self.binary), "--version"], 10, output="secret-output")
        with patch.object(m.subprocess, "run", side_effect=failure) as runner:
            result = m.inspect_codex(self.binary, self.root, True)
        self.assertEqual(result["status"], "cli_help_failed")
        self.assertEqual(runner.call_count, 1)
        self.assertNotIn("secret", json.dumps(result))

    def test_invalid_workspace_skips_binary(self):
        with patch.object(m.subprocess, "run", side_effect=AssertionError("No execution")):
            report = m.preflight(self.root / "missing", self.root, [], None, self.binary)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["codex"]["status"], "skipped_invalid_workspace")

    def test_state_file_is_not_a_directory(self):
        report = m.preflight(self.root, self.root, [self.binary], self.root, None)
        self.assertIn("state:not_directory", report["blockers"])

    def test_symlink_inspection_reads_no_target_contents(self):
        target = self.root / "target"
        target.mkdir()
        link = self.root / "link"
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks not supported by this test host")
        item = m.path_metadata(link, "state")
        self.assertTrue(item["is_symlink"])
        self.assertEqual(item["resolved_path"], str(target.resolve()))

    def test_absolute_paths_only_without_home_expansion(self):
        for value in ("relative/path", "~/state", "$CODEX_HOME"):
            with self.assertRaises(m.argparse.ArgumentTypeError):
                m.absolute_path(value)


if __name__ == "__main__":
    unittest.main()
