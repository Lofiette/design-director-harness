---
name: ddh-recover
description: Checkpoint and resume meaningful work across chats, context compression or interruption. Recover the approved scope, evidence, unresolved decisions and next operation.
---

# Checkpoint and resume

Before a risky handoff, record the objective, approved scope, worktree or base identity, verification already run, observed evidence and the next exact operation. If waiting for user input, include the pending question and the action that depends on it. Keep the record short and stable. Reference artifacts rather than transcribing them. Avoid putting credentials, private payloads or broad logs in the checkpoint.

For an active CPT task, use the installed CPT runtime to checkpoint and verify its state on return. Check the referenced snapshot with `recover --checkpoint <id> --verify-only` before dependent writes. Keep the task and lease in CPT. A DDH handoff can record artifact hashes or a pending answer that complements the CPT snapshot.

For standalone DDH, when the DDH CLI is available, use its checkpoint and resume commands with a workspace-relative artifact list and one immutable checkpoint per handoff. Otherwise keep the same fields in an explicit project handoff. Record observed branch and HEAD when Git identity matters.

For a pending user answer or review, include `pending` with `kind` set to `user_input` or `review`, the exact `request`, and the `blockedAction`. Resume reports the corresponding waiting state. A saved next operation does not settle that pending decision.

On resumption, verify the record and evidence against the current workspace. Compare branch, dirty files, running processes and user steering when they can change the decision. Treat a mismatch as a reconciliation step. Preserve the checkpoint, diagnose the delta and wait before dependent writes until the state is understood. If a saved question is still open, return to the waiting step in ddh-direct. Continue at the next operation only when its prerequisites are settled.
