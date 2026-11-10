# Delegation

Read this before delegating a state change, and when you are a delegated worker. A subagent cannot spawn its own reviewer: the harness allows direct children only.

## When you delegate a state change

Pass only an action you may take yourself: a settled one (step 1), or a verdict that has cleared step 5 (Light or Auto, or Confirm/Escalate after the user answered). The brief states:

- the basis — the reviewed verdict, the user's words quoted, the approved spec or ticket, or the deciding fact;
- the exact action and its targets, with the target check (step 2);
- the rung, or "settled (a | b | c | d)"; for Light, the undo command too;
- "You are a delegated worker; do not spawn a reviewer."

When the worker returns, you confirm the result and write the log. A decision it returns enters your step 3: score it, check it and place it on the ladder before anyone acts on it.

## When you are the worker

You are a worker when a parent agent's brief says so, or when spawning a reviewer fails with a depth error. Act only inside the basis your brief carries. A brief from a script is not a delegation brief: the no-human rule of step 6 applies.

- The action and targets named in your brief are settled for you, whatever the rung: run the target check, act, confirm the result. Do not wait for the user's words in your own chat.
- An emergency stop (step 1, basis d) is settled for you too: stop the process, confirm the damage stopped, and report it to the parent, which logs it.
- As in step 1 (c), implementation details within those targets that change neither outside behaviour, nor reversibility, nor scope are settled.
- Any other decision that leads to a state change: stop and return it to the parent with your candidates and facts. Say "needs the user's choice" when it is irreversible or a preference.
- Do not write decision logs or `settled.md` lines; the parent logs what you return.
