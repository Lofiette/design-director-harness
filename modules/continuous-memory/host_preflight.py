#!/usr/bin/env python3
"""Inspect explicit host paths and trusted Codex help; never start an agent.

No config/credential reads, directory enumeration, write probes, environment
overrides, installation, network probes, or changes to host permissions.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
from typing import Any

VERSION = "0.1.0"
COMMAND_TIMEOUT_SECONDS = 10
HELP_FLAGS = ("--json", "--ephemeral", "--output-schema", "--remote")


def absolute_path(value: str) -> Path:
    """Do not expand environment variables or infer a home directory."""
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("Pass an explicit absolute path.")
    return path


def path_metadata(path: Path, role: str) -> dict[str, Any]:
    """Inspect one path. For a missing output, inspect its nearest parent only."""
    result: dict[str, Any] = {
        "role": role, "path": str(path), "status": "unknown",
        "exists": None, "resolved_path": None, "is_symlink": None,
        "metadata_target": None, "access_write": None,
        "filesystem_readonly": None, "free_bytes": None,
        "write_probe": "not_run",
    }
    try:
        result["is_symlink"] = path.is_symlink()
        result["resolved_path"] = str(path.resolve(strict=False))
        try:
            info = path.stat()
            result["exists"] = True
        except FileNotFoundError:
            info = None
            result["exists"] = False
        probe = path
        if info is None:
            if role != "output" or result["is_symlink"]:
                result["status"] = "missing"
                return result
            probe = path.parent
            missing_parents = 0
            while True:
                try:
                    info = probe.stat()
                    break
                except FileNotFoundError:
                    if probe == probe.parent:
                        result["status"] = "missing"
                        return result
                    missing_parents += 1
                    probe = probe.parent
            result["missing_parent_directories"] = missing_parents
            result["destination_uncreated"] = True
        if role != "output" and not stat.S_ISDIR(info.st_mode):
            result["status"] = "not_directory"
            return result
        if role == "output" and not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            result["status"] = "unsupported_file_type"
            return result
        if result.get("destination_uncreated") and not stat.S_ISDIR(info.st_mode):
            result["status"] = "parent_not_directory"
            return result
        result["metadata_target"] = str(probe)
        result["access_write"] = os.access(probe, os.W_OK)
        result["access_search"] = os.access(probe, os.X_OK) if stat.S_ISDIR(info.st_mode) else None
        if hasattr(os, "statvfs"):
            try:
                volume = os.statvfs(probe)
                readonly_flag = getattr(os, "ST_RDONLY", None)
                if readonly_flag is not None:
                    result["filesystem_readonly"] = bool(volume.f_flag & readonly_flag)
                result["free_bytes"] = volume.f_bavail * volume.f_frsize
            except OSError as exc:
                result["filesystem_metadata_error"] = type(exc).__name__
        if result["filesystem_readonly"] is True:
            result["status"] = "filesystem_readonly"
        elif not result["access_write"] or result["access_search"] is False:
            result["status"] = "metadata_not_writable"
        elif result.get("missing_parent_directories", 0):
            result["status"] = "parent_metadata_writable_missing_directories"
        else:
            result["status"] = "metadata_writable"
    except (OSError, RuntimeError) as exc:
        result["status"] = "metadata_error"
        result["error_type"] = type(exc).__name__
    return result


def inspect_codex(binary: Path | None, workspace: Path, workspace_ok: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "not_requested", "binary": str(binary) if binary else None,
        "version": None, "help_flags_observed": [], "commands": [],
        "native_startup": "not_run",
    }
    if binary is None:
        return result
    if not workspace_ok:
        result["status"] = "skipped_invalid_workspace"
        return result
    try:
        if not stat.S_ISREG(binary.stat().st_mode) or not os.access(binary, os.X_OK):
            result["status"] = "binary_not_executable"
            return result
    except OSError as exc:
        result["status"] = "binary_unavailable"
        result["error_type"] = type(exc).__name__
        return result

    for arguments in (("--version",), ("exec", "--help")):
        record: dict[str, Any] = {"arguments": list(arguments), "status": "not_run"}
        result["commands"].append(record)
        try:
            completed = subprocess.run(
                [str(binary), *arguments], cwd=workspace,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                timeout=COMMAND_TIMEOUT_SECONDS, check=False, shell=False,
            )
            record.update(returncode=completed.returncode, stderr_present=bool(completed.stderr))
            if completed.returncode != 0:
                record["status"] = "command_failed"
                result["status"] = "cli_help_failed"
                return result
            if arguments == ("--version",):
                match = re.fullmatch(r"codex-cli ([A-Za-z0-9][A-Za-z0-9.+_-]{0,99})", completed.stdout.strip())
                if not match:
                    record["status"] = "unrecognized_version_output"
                    result["status"] = "cli_identity_unconfirmed"
                    return result
                result["version"] = match.group(1)
            else:
                if "Usage: codex exec" not in completed.stdout:
                    record["status"] = "unrecognized_help_output"
                    result["status"] = "cli_help_unconfirmed"
                    return result
                result["help_flags_observed"] = [
                    flag for flag in HELP_FLAGS
                    if re.search(r"(?<![\w-])" + re.escape(flag) + r"(?![\w-])", completed.stdout)
                ]
            record["status"] = "ok"
        except (OSError, subprocess.TimeoutExpired) as exc:
            record.update(status="command_failed", error_type=type(exc).__name__)
            result["status"] = "cli_help_failed"
            return result
    result["status"] = "cli_help_ok"
    return result


def preflight(workspace: Path, output: Path, state_dirs: list[Path],
              temp_dir: Path | None, codex_bin: Path | None) -> dict[str, Any]:
    paths = [path_metadata(workspace, "workspace"), path_metadata(output, "output")]
    paths.extend(path_metadata(path, "state") for path in state_dirs)
    if temp_dir is not None:
        paths.append(path_metadata(temp_dir, "temp"))
    workspace_ok = paths[0]["status"] == "metadata_writable"
    cli = inspect_codex(codex_bin, workspace, workspace_ok)
    incomplete: list[str] = []
    blockers: list[str] = []
    if not state_dirs:
        incomplete.append("state_location_unknown")
    if temp_dir is None:
        incomplete.append("temp_location_not_inspected")
    if codex_bin is None:
        incomplete.append("codex_cli_not_inspected")
    for item in paths:
        if item["status"] == "parent_metadata_writable_missing_directories":
            incomplete.append("output_parent_directories_uncreated")
        elif item["status"] != "metadata_writable":
            blockers.append(item["role"] + ":" + item["status"])
    if codex_bin is not None and cli["status"] != "cli_help_ok":
        blockers.append("codex:" + cli["status"])
    status = "blocked" if blockers else "incomplete" if incomplete else "metadata_checks_complete_only"
    return {
        "schema_version": "ddh-host-preflight/1", "tool_version": VERSION,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "host_scope": "current_execution_host_only",
        "platform": platform.system(), "status": status,
        "paths": paths, "codex": cli, "blockers": blockers, "unknowns": incomplete,
        "native_startup": {"status": "not_run", "reason": "Only version and help commands are permitted by this preflight."},
        "actual_write_probe": "not_run",
        "state_path_coverage": "explicit_paths_only" if state_dirs else "unknown",
        "limitations": [
            "Filesystem metadata is not an actual write test or proof that a future process can write.",
            "Effective Codex state locations are not resolved from config or environment.",
            "Explicit state paths are caller supplied and are not verified as the active Codex configuration.",
            "Help success does not establish app-server initialization, authentication, hook trust, or model execution.",
            "No other device, network connection, or Dot session was inspected.",
        ],
    }


def exit_code(report: dict[str, Any]) -> int:
    return {"metadata_checks_complete_only": 0, "blocked": 1, "incomplete": 3}[report["status"]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=absolute_path, required=True)
    parser.add_argument("--output", type=absolute_path, required=True,
                        help="Planned output path to inspect; this CLI does not write to it.")
    parser.add_argument("--state-dir", type=absolute_path, action="append", default=[],
                        help="Explicit state directory, repeatable; never inferred from environment/config.")
    parser.add_argument("--temp-dir", type=absolute_path)
    parser.add_argument("--codex-bin", type=absolute_path,
                        help="Already trusted Codex executable; runs only --version and exec --help.")
    args = parser.parse_args(argv)
    report = preflight(args.workspace, args.output, args.state_dir, args.temp_dir, args.codex_bin)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
