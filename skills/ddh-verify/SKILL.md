---
name: ddh-verify
description: Verify a changed product, design or code outcome before reporting completion. Choose targeted checks, reproduce failures, and collect evidence from the feature's normal entry point.
---

# Verify the outcome

Restate the observable expected result and the affected boundary. Select the cheapest check that can falsify the claim. Use repository-owned verification when applicable and widen the checks when contracts or shared components change.

For defects, reproduce the symptom with a tight feedback loop. Identify the cause before changing behavior. Capture a regression check when existing checks would miss it. Run the normal entry point again and inspect the actual result. For UX, exercise states and layout on the intended surface.

Keep artifact, command, result and limitation together. A successful build supports a build claim. Behavioral and visual claims need matching evidence. Distinguish pass, fail, blocked and unverified. Carry forward negative trials that could prevent duplicate work. Never count a skipped check as a pass.

Use a fresh-context review when independence matters and the user has authorized it. The main agent verifies coverage and integrates the result.

Review the executed outcome against the agreed criteria. Consult any earlier decision review and avoid repeating it unless the result changes its assumptions.
