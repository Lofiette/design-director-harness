# Log (step 7)

Read this at step 3, and before writing or updating a decision log.

## What gets logged

- Every decision that entered steps 3–6 gets its own file, including advisory ones and those where every candidate was refuted, even when it touched a shared surface. The one exception is a Light decision.
- A Light decision gets one line in `settled.md`, written after observing:

```
- YYYY-MM-DD light: <action> on <target>; runner-up: <candidate>; undo: `<command>`; outcome: <…>
```

- Settled actions (basis a–d) are not logged, except for a one-line entry in `settled.md` when they were irreversible, touched a shared surface, were an emergency stop, or failed:

```
- YYYY-MM-DD <basis: a | b | c | d>: <action> on <target>; outcome: <…>
```

## Where

The log folder is `<project>/.dsh/decisions/`; each decision is a file `YYYY-MM-DD-<slug>.md`. `<project>` is the nearest folder at or above the working directory that holds `.git`; with no `.git`, the working directory itself. If the file name is taken, append `-2`, `-3`.

**Git.** If `.dsh/decisions/` is not yet listed in the file that `git rev-parse --git-path info/exclude` prints, add it there. In a worktree or submodule, `.git` is a file, not a folder. Without git, say in the report that the log folder is untracked.

## Rules

- **Draft before a review.** Write the file before spawning the reviewer (Rung: pending, Outcome: awaiting review), with your scores; fill the reviewer's columns and section when the verdict arrives.
- **Log first on Confirm and Escalate.** Write the file (Outcome: awaiting user) before presenting, then present and stop.
- **One decision, one file.** A follow-up to an earlier decision gets its own file; name the earlier file in its Question. Do not append a new decision to an old file. An answer that redirects a handed-over plan closes the old file as declined and opens a new one.
- **Keep the header current.** When the outcome changes, update the Outcome line, not only the body: a later session finds open decisions by that line. Use only the listed Outcome values.
- **Anyone updates.** Any session that obtains a fact that changes a logged decision's result (the user's words about it, an observation, a failure it caused) updates that file's Outcome, or that line's outcome, and adds the fact with its source and date, even when another session wrote it.
- **The user's answer.** When the user answers a handed-over decision, in this session or a later one, find its file (Outcome: awaiting user), add their words, and update the Outcome after acting.
- **Acted without the procedure.** If you find you changed state without running the procedure when it applied, stop and tell the user which change it was, which steps were skipped, and what of its result is unverified. Write a decision file for that action with Rung: none, Outcome as it stands, and the skipped steps. Then go back to step 1 before the next change. A delegated worker returns this to the parent instead.
- **Content.** Redact secrets as `<REDACTED>` and quote only the output lines that carry the signal. Record rejected candidates with what rejected them: the refuting fact, or the reviewer's depth.

## Template

Step 3 uses the same Candidates columns; the reviewer's two stay empty until the verdict.

```markdown
# <decision title>

- Date: YYYY-MM-DD
- Rung: pending (before the verdict) | Auto | Confirm | Escalate | none (the procedure was skipped)
- Margin: <yours> / <reviewer's> points, or n/a
- Outcome: advised | acted (verified) | acted (unverified) | failed | declined | nothing works | awaiting review | awaiting user

## Question
<each unknown and its kind; the earlier decision file, for a follow-up>

## Candidates
| # | Candidate | Rating | Depth | Reviewer rating | Reviewer depth | State | Rests on | Refuted by | Next probe |
|---|---|---|---|---|---|---|---|---|---|

## Evidence
<the facts, with the command or file:line each came from>

## Reviewer
<the reviewer's verdict, including discarded candidates and what discarded them>

## Decision
<what was chosen, why, and what follows from it>

## User's answer
<the user's words and the date, when the decision was handed over>

## Observation
<how the result was observed (channel, attempts), or what would confirm it>
```

**Done when** the file exists with every candidate in it (leader, below bar, refuted or discarded), or the one-line entry is appended.
