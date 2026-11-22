# Read-only host preflight

`host_preflight.py` inspects explicit paths and, optionally, an already trusted Codex executable. It runs on the current execution host; it does not select, connect to, or diagnose other Dot devices.

Python 3.10+ and its standard library are sufficient. No installer changes or additional service are required.

```bash
python -B host_preflight.py \
  --workspace /absolute/project \
  --output /absolute/project/result.json \
  --state-dir /explicit/known/codex-state \
  --temp-dir /explicit/known/temp \
  --codex-bin /absolute/trusted/codex
```

Use the actual absolute paths of the selected host. `--state-dir` is repeatable and optional: omit it when the effective state location is unknown. Do not substitute a guessed home directory. Paths are not expanded from `~` or environment variables. Providing a state path records caller-supplied scope; it does not prove that Codex uses that directory.

`--output` names the planned output destination **to inspect**, not a report-writing option. JSON goes to stdout. A caller may redirect stdout to an explicitly selected report file; that separate write is not a write probe and is outside the CLI's read-only operations.

## Boundaries and interpretation

- Reads filesystem metadata only. Does not list directory contents or read config, credentials, transcripts, or environment values.
- Does not create directories/files, change permissions/mounts, install anything, or set `HOME`/`CODEX_HOME`.
- With `--codex-bin`, executes exactly `--version` and `exec --help`, each with a 10-second timeout and without a shell. Use only a binary already trusted for those commands. Raw command output is not persisted; version and known help flags are extracted. No prompt, app-server startup, LLM session, auth check, or remote probe runs.
- `metadata_writable` means access/mount metadata suggests write access; **actual write is `not_run`**. OS policies, locks, quotas, race conditions, and child-process constraints may still prevent a later write. Filesystem read-only metadata may be unavailable on some platforms and remains `null`.
- A missing output file can be inspected through its existing parent. Missing intermediate directories produce an incomplete result; this tool never creates them.
- State path unknown is `incomplete`, never a pass. Even a complete result is `metadata_checks_complete_only`, with native startup explicitly `not_run`.
- A prior startup failure belongs in a separate evidence record; this preflight does not reproduce or erase it. `--ephemeral` is not assumed to make all startup operations disk-free.

Exit codes: `0` = bounded metadata/help checks complete; `1` = observed blocker; `2` = invalid CLI arguments; `3` = incomplete scope. Exit `0` does **not** certify native startup or automatic memory capture.

Run the synthetic tests from this module directory:

```bash
python -B -m unittest discover -s tests -p 'test_host_preflight.py'
```

This is an independent diagnostic helper. CPT retains task/lease/checkpoint ownership; the helper does not change its runtime or ledger.
