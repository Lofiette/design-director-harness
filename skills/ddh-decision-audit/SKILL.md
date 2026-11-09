---
name: ddh-decision-audit
description: "Choose an approach, dependency, config or fix by proof, before any state change. Use when alternatives stay open, before editing an unread file, and before every delete, move, process kill, write-API call or shared-surface change, even when ordered; also when the user corrects, rejects or answers a handed-over decision. Proves the answer with facts, scores candidates, and puts a check between the verdict and the action."
---

# Decision audit

The failure this prevents: stopping research once an answer looks plausible. Dig until facts prove it, score it, and put a check between the verdict and any state change. Order: classify → research → score → check → ladder → act → log; skip a step only where this text says so. If this text was pruned, load the skill again before the next step.

**Terms.** A *fact* is observed here and now: command output, file contents, a response, a primary-source quote, the user's own words. A *shared surface* is a corporate system, another person's data, a running service, or the harness you run in (its config files, installed plugins, UI). *Observing a result* means seeing the effect where it happens; a written file or a passing build is only a probe. The reviewer's [brief](references/review-brief.md) has the exact shape.

**Consequential choices need ddh-direct intake before choosing or acting.** This skill owns the evidence, the candidates and the check, not the intake question.

## Scores

Keep both apart. Rate as if unconfirmed points hold; what is unconfirmed lowers depth.

- **Rating**, how well it answers: 0 fails or costs more than the problem; 2 heavy rework or ongoing cost; 5 works, real caveats; 8 clean, minor drawback; 10 fully answers, no caveats.
- **Depth**, how proven: 10 reproducible facts obtained here, target verified, consequences known; 9 only minor consequences unconfirmed; 8 or below: something material is inference. The bar is 9. Refuted by a fact: no depth; record the fact.
- **Leader**: your highest-rated candidate at the bar, provisional until step 4. **Margin** exists only after a review; [the review procedure](references/review.md) defines it.

## 1. Classify

Name each unknown that holds the choice: **Verifiable** (fetch it), **Preference** (research the verifiable part; one viable option left means it was verifiable; one the user left to you is yours; otherwise Escalate), or **Settled**, allowed only on a stated basis:

- (a) the user's message names the concrete action and target and leaves no choice of how ("fix X" settles that, not how);
- (b) reversible, local, no shared surface, rates 5+, result observable, and a cited fact rules out each alternative;
- (c) an implementation edit inside an approach the user approved or a check chose (a TDD step only inside one): reversible, local, no shared surface, version-controlled, no change to outside behaviour or scope; name the check and its expected result;
- (d) emergency stop: output shows damage now (data or resources destroyed or exhausted). Confirm the PID and that it is the source, stop it and its children, confirm the damage stopped.

A parent agent or script is never (a); a delegated worker reads [delegation](references/delegation.md) first. Irreversible: only (a) or (d). Settled actions skip steps 3–5: check the target, act, observe. An unexpected (c) result: undo, or reproduce the cause first; the next edit is a fix ((b) or step 3); stop after two in a row.

**Follow-ups are new decisions.** A correction, rejection, rework request or an answer that redirects a handed-over plan opens a new decision; an earlier approval covers only what it named.

## 2. Research

Close every verifiable uncertainty that can change the leader or the rung before anything reaches the user; the next cheap probe is the work. Probes change nothing lasting (output, build artifacts, your own scaffolding removed at the end, git operations that restore the tree, not history, index or stash); everything else is a state change. Before a delete, move, kill, config overwrite or write-API call, state what confirmed the target; for an irreversible one name it exactly (resolved path, contents, whether links are followed; PID; host and identifier); a mismatch with what the user meant, data behind links included, opens the choice. Causes are verifiable: reproduce before fixing; candidates are fixes.

**Exit** to step 5 as Escalate after scoring what you have: the next probe needs access you lack or an irreversible or shared change (a dry run or scratch copy counts as runnable); two probes at the Next-probe point settled nothing; a failure did not reproduce within the budget you set. All refuted: look once more, then report that nothing works.

## 3. Candidates

Two to four, including the strongest alternative; one only when facts refuted the rest. Tabulate them in the Candidates columns of [the log](references/log.md) (read it now). Only the leader must reach the bar. End with a one-line recommendation; the user sees the full ranking.

## 4. Check

Read [the review procedure](references/review.md): every state change chosen here gets one check (not a preference-only choice between reversible, local candidates).

- **Light**, when all hold: only files change, prior state committed or copied aside first; local, no shared surface; no delete or move; no open Preference; you can observe the result; one undo command works even if the change breaks what it touches. Self-check per that file.
- **Review** otherwise: brief, log draft, then one `subagent` spawn as your last tool call. The brief skeleton is in [the review procedure](references/review.md). Then one line with no tool call ends the turn; the verdict starts the next. Until then: no state change, `list_agents` or job polling, sleep, or asking the user to choose.

## 5. Ladder (the most restrictive match wins)

| Rung | Test | Who decides |
|---|---|---|
| Light | light check passed; leader rates 5+ | you act, observe, report the runner-up and the undo |
| Auto | reversible, local, no shared surface, result observable, both raters rate the leader 5+, margin 2+ | you act and report |
| Confirm | costly to undo, a shared surface, or a result you cannot observe | you act only after an explicit yes in chat |
| Escalate | irreversible; margin under 2 after a review; leader under 5 by either rater; open Preference; failed review | the user chooses |

A reviewed gap under 2 is not evidence: the user separates close candidates, even routine ones. Judge by what breaks if you are wrong.

## 6. Act or hand over

Confirm or Escalate: log first, then present every candidate with each rater's scores, the discarded ones and the reasoning, also in a question tool. Advice only: the answer is the result; a pick is not a request to act. The user's pick settles it; an answer outside the candidates is a follow-up. Observe the result: cheapest channel first (DOM or accessibility text before pixels), in the state that exercises the change, within an attempt budget set beforehand (default 3). Driving the user's live app (keys, clicks, reload) needs their yes each time, naming the inputs. Unobserved is not done: say what would confirm it. A failure: stop and report; reverting is a new decision, unless Light stated the undo.

## 7. Log

Log per [the log](references/log.md) every decision from steps 3–6 and every settled action that was irreversible, shared, an emergency stop or failed. A fact that changes a logged result: update that file, whoever wrote it. Acted without this procedure? Tell the user, log it with Rung: none, return to step 1. Before delegating, read [delegation](references/delegation.md).
