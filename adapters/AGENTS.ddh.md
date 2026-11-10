# Design Director Harness 5.0

For a new substantive product, design or engineering request, load ddh-direct and run its intake check at the start, even when the user did not ask for an interview. Use the same skill when the user responds to a pending DDH question. Start work directly when the required inputs are clear.

If a decision depends on a user answer, ask once and pause all dependent work until the answer arrives. In non-interactive runs, put the question in the final response and end the turn. An unanswered question stays open when time passes.

When a project has a CPT kernel and `.cpt/runtime.yaml`, follow the CPT startup and recovery steps. DDH owns intake. CPT owns the task record, lease, checkpoint, and workflow policy. Reuse the settled intake in CPT planning. Obtain any required authorization separately. Keep one task record and use CPT recovery for that task.

From the project root, run CPT with `uv run --no-project --with-requirements .agents/ddh-runtime-requirements.txt python -B .cpt/bin/cpt_runtime.py <command>`. With a Python environment that already has these requirements, run `python -B .cpt/bin/cpt_runtime.py <command>` directly. Start with `validate` if runtime health is unclear.

Use ddh-decision-audit for consequential choices, ddh-design for user-facing design, ddh-verify for acceptance and ddh-recover after interruption. For a small clear change, inspect the target and run the focused check. Follow the project's authority and host permissions.
