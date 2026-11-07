# Design stress review

### 10. Stress the design

Test the solution against:

- novice, expert, first-time, and second-time use;
- high-frequency and repeated work;
- error, interruption, branch change, and re-entry;
- extreme, missing, stale, conflicting, or localized content;
- permissions, roles, selection scope, and partial success;
- keyboard, touch, pointer, zoom, and assistive technology;
- narrow, wide, resized, and multi-workspace contexts;
- implementation, rendering, network, and performance constraints.

### 11. Adversarial critique

Assume the solution is competent but mediocre. Use the review rubric to find unnecessary UI, copied pattern logic, false simplicity, ambiguous hierarchy, weak defaults, premature questions, expert inefficiency, novice traps, hidden state loss, inconsistent controls, vendor lock-in, accidental complexity, and unsupported rationale.

Change the design or explicitly accept the trade-off with evidence.

## Evidence standard

- Product and behavior claims must trace to evidence or explicit hypothesis status.
- Pattern names and source screenshots are not proof of fit.
- Visual decisions must trace to the design system, project criteria, source-derived invariant, or explicit testable hypothesis.
- Numeric UI recipes are contextual defaults unless the project makes them authoritative.
- Current standards and platform behavior must come from current project sources or separate research.
- Execution availability must be observed in the runtime; missing capabilities must not be imagined.

## Failure modes to avoid

- Starting from the requested screen.
- Producing cosmetic alternatives.
- Copying a named pattern or visual reference.
- Treating form design as field arrangement.
- Cardifying professional data and losing comparison.
- Hiding expert actions for visual cleanliness.
- Letting an execution provider silently change the design decision.
- Claiming visual PASS from text or self-generated QA alone.
