# Check (step 4)

Read this at step 4: the light check when every Light condition there holds, a review otherwise.

## Light check

It replaces the reviewer, not the evidence: the leader still needs depth 9.

1. **Undo first.** Write the one command that restores the prior state, e.g. `git checkout <commit> -- <path>`, or copying `<backup>` over `<path>`. Not committed yet: copy the files aside now. The undo must not need the changed code to run.
2. **Three answers, each resting on a fact** (command output or `file:line`): does it break what works now (callers, code it shares, states it was not built for)? Is a mandatory consequence missing (reload or restart, migration, dependency, cleanup on unload)? Does it do what the user asked, within their constraints, and nothing more? An answer without a fact is a doubt: review instead.

The check has **passed** when the undo is written and all three answers rest on facts. Nothing is changed yet: go to step 5. Only on the Light rung, in step 6:

- **Act and observe** in the state that exercises the change, and in one it was not built for (another tab, section or theme) if you can reach it. Keys, clicks or a reload in the user's live app need their yes first, each time.
- **Report** what changed, how you observed it, the runner-up with what put it second, and the undo.
- **Failure** or a side effect: run the undo, confirm the prior state is back, report. A retry is a new decision on the review path, never settled (b) or (c).
- **Log** one `settled.md` line (see [the log](log.md)).

## Review

Before dispatch, check the host has an independent reviewer tool and the task allows delegation. In CPT, require an active Standard Task, a scoped lease allowing this reviewer, a bounded worker contract and the required quorum. Follow native host permissions as well. If any precondition is missing, record the reason within authorized scope, mark the decision unreviewed, and keep the action pending. Escalate with the missing check and ask through ddh-direct only if a user choice or authorization can resolve it.

When those checks pass, proceed in order.

1. Fill in the brief skeleton in [the brief](review-brief.md).
2. Check it before sending: no candidate carries a rating, depth or score of yours, in any language or form ("rating 8", "8/10", "Оценка 8, глубина 9"). Rating and depth numbers appear only in the anchor tables.
3. Draft the decision file (see [the log](log.md), read it now) with your scores, the evidence and Outcome: awaiting review. Your scores go there, never in the brief.
4. Use the host reviewer tool and send only the brief. Start with a clean reviewer context, without the parent scores or conversation history.
5. If the tool returns a verdict, process it. If it returns a job ID, use the documented completion mechanism. If completion arrives on a later turn, leave the decision pending and resume on that notice.

Keep the action pending until a usable verdict arrives. Avoid polling or repeating the reviewer probes. Present Confirm and Escalate after the verdict unless review was unavailable.

## Margin

The leader's rating minus the best other unrefuted candidate's, at the bar or not, computed with your ratings and again with the reviewer's for the same leader; if either is under 2, it is under 2. A margin of 2+ counts only if the runner-up's rating rests on a cited fact. No unrefuted rival: met.

## Handle the answer

- **Ratings** feed the margin. A rating disagreement is not an objection and needs no fact.
- **Refutation rejected** → that candidate is unrefuted again; recompute the margin.
- **Objections**, including a refuting fact the reviewer found → back to step 2. Close each by a fact, not by argument. If the fact confirms the objection, the verdict changes.
- **Missing alternative** → research and score it yourself, then send it to the second review. A number the reviewer gave it is not a review: until reviewed, it cannot lead, be acted on, or be shown to the user with a score.
- **Everything discarded** → back to step 2 for one round of probes aimed at the reviewer's reasons, entered as each candidate's Next probe. If the next review discards everything again, take step 2's exit.
- **No usable answer** → retry once for a transient call failure or an incomplete verdict, while the review is still authorized. If the retry fails, go to step 5 as Escalate, marked "unreviewed", and keep the action pending.
- **Reviewer unavailable or authorization denied** → use the pre-dispatch unavailable path, without retrying.
- **Depth-limit rejection** → do not retry: you are a worker (see [delegation](delegation.md)).
- **No objections** → step 5.

Review again whenever new facts or a changed plan change the leader, the action or the target, or add a candidate. A leader change caused by the review's own discards needs no new review. A decision gets at most two reviews; if a third would be needed, go to step 5 as Escalate.

**Done when** the reviewer has rated every unrefuted candidate, the leader passed, and every objection is closed by a fact.
