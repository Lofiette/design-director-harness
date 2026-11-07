---
name: ddh-direct
description: Start a substantive product, design or engineering task, or continue after an intake question. Resolve material uncertainty before dependent work and choose a workflow by scope, risk and evidence.
---

# Direct the work

## Start with intake

First identify whether this is a new task or an update to the current one. For a new substantive request, check intake even if the user did not ask for an interview. Find the intended outcome, user or workflow when relevant, authoritative inputs, allowed surface and observable acceptance. Inspect only sources that could settle a decision. Reuse facts and choices already given in this chat or recorded in the project.

If different plausible answers would change the deliverable, constraints or acceptance, ask before starting dependent work. Ask the highest-impact question first. Offer a few distinct options with their consequences when that makes the answer easier. Group up to three independent questions only if each changes the work. Own the intake question even when another skill identified the gap.

If an unknown is cheap to verify, verify it. If a choice is delegated or reversible and low impact, state the assumption and proceed. When the goal, scope and acceptance are clear, start work. A request for approval follows the authorization boundary separately from intake.

Reversibility alone does not settle an identified material uncertainty. For partial answers, independent requests or handoffs between skills, consult [the transition contract](references/transitions.md).

## Await the answer

Once a consequential question is asked, pause work that depends on the answer. Do not create or edit a dependent artifact, including a draft. Independent read-only discovery is fine when it helps and the host can still receive the answer. Elapsed time, a tool acknowledgement or silence never settles the question. Do not poll or sleep for a reply.

- **Non-interactive run, including `codex exec`, or unknown reply capability.** Put the question in the final response and end the turn. A visible input tool alone does not establish that a reply can arrive here.
- **Interactive session with a working reply mechanism.** Use the native question tool if it can deliver an answer. If it returns the actual answer, use it. If it only delivers the question, end the turn without repeating it and continue on the next user message. Use a plain chat question if there is no suitable tool.

On the next message, apply the answer to the pending choice and continue from the blocked step. Ask only about a still-material gap in a partial answer. If the user explicitly delegates the choice, state the assumption and continue within scope. If they cancel, stop that task. If they explicitly replace the task, close the pending question and assess the new request. An unrelated reply leaves the question open.

## Choose the workflow

1. A clear, local, reversible edit with a known check can go directly from inspection to edit to verification. Skip task files and reviewer setup for this path. Escalate when the target is shared, behavior crosses boundaries or a consequential choice remains open.
2. For meaningful design or implementation, record a short brief with the outcome, constraints, allowed changes, named verification and open decisions. Consult existing ADRs and components. Record a durable domain term or ADR when the decision will affect future work.
3. Use ddh-decision-audit for unresolved consequential choices, ddh-design for user-facing design, ddh-verify for acceptance and ddh-recover for a handoff or interruption. Load only the relevant skill. Use the host's current tool catalog.
4. Keep tool execution within user authorization. Use focused work slices with independent checks. Reuse native workspace isolation and agent controls when available. Keep a single accountable owner of the result.

For a read-only question, deliver the answer and evidence without creating task state.
