# Codex adapter

Install DDH into the project with `node tools/ddh.mjs install --project <project>` from the shared distribution. It adds the CPT runtime, writes the skills under `.agents/skills` and adds intake guidance to `AGENTS.md`. Open a fresh Codex chat in that project.

For a marketplace adapter test, run the following commands from the parent directory of the exported `ddh-codex-5` folder in a test Codex profile.

```powershell
codex plugin marketplace add ./ddh-codex-5
codex plugin add design-director-harness@design-director-harness
```

Add the included intake guidance to the project's AGENTS.md if you want it to apply automatically at the start of a new task. Verify the five DDH skill names in the new session. Use native approvals, worktrees, subagents and Goals where they fit the user's request.

Use a read-only, fresh-context reviewer if the host can supply one and the scope permits it. Keep the checkpoint in the project and provide its path in the new chat. The generated plugin contains skills and declares no hooks or MCP services.
