# Workflow transitions

| Event | Owner and next action |
|---|---|
| New clear local task | Direct selects inspection, edit and focused verification |
| Material unknown | Direct owns one question and records what depends on its answer |
| Question delivered without an answer | End the turn and retain the blocked step |
| Partial answer | Apply known facts and ask only about a remaining material gap |
| Explicitly delegated choice | State the assumption and continue within authorized scope |
| Cancellation | Stop that task and close its pending question |
| Explicit replacement | Close the old pending question and assess the new request |
| Independent request during a wait | Preserve the original pending step and work only on the independent scope |
| Review required before a choice | Decision audit owns the independent challenge |
| Verification after execution | Verify checks the outcome against acceptance criteria |
| Handoff while waiting | Recover retains the pending question or review and the blocked action |
| Resume with mismatching evidence | Reconcile the delta before dependent changes |

Design owns criteria and design intent. Verify owns observed acceptance evidence. A review of a choice before implementation and a review of the result answer distinct questions. Reuse already sufficient evidence, and add another review only when it owns an unresolved decision.

For a meaningful task, explain the current step, why a specialist is needed, and the next observable check in a short brief or existing task record. A clear micro change can remain in the conversation. Loading a skill alone does not show that it affected the outcome.
