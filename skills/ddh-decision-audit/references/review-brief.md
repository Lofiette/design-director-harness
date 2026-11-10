# Review brief

Read this at step 4 of [the review procedure](review.md), when spawning the reviewer. The reviewer starts with an empty conversation. Copy the block, fill every `<…>`, add nothing outside it; any language.

```text
## Request
<the user's request, verbatim>
Earlier constraints from the user on this action or target: <each, quoted, or "none">

## Unknowns
- <unknown>: <Verifiable | Preference | Settled (a-d)>

## Candidates
### C1. <name>
What it does: <one or two lines>
Rests on: <command and the output lines that matter, or file:line>
Known caveats: <facts only, not how much they matter; or "none found">

### C2. <name>
<the same three lines; one block per unrefuted candidate>

## Refuted
- <candidate>: <the refuting fact and its source>, or "none"

## Planned action
Action: <exact action>
Target: <exact path, identifier, PID or host>
Observation: <how the result will be observed>
Undo: <how it is undone>

## Scales
Rate a candidate as if its unconfirmed points hold; whatever is unconfirmed lowers depth, not the rating.

| Rating | Anchor |
|---|---|
| 0 | does not work, or costs more than the problem is worth |
| 2 | works only with heavy rework or ongoing cost |
| 5 | works, with real caveats or collateral |
| 8 | works cleanly, minor known drawback |
| 10 | fully answers the question as posed, no caveats |

| Depth | Anchor |
|---|---|
| 10 | proven by reproducible facts obtained here; target verified; consequences known |
| 9 | proven; only minor consequences unconfirmed, nothing material |
| 8 or below | something material still rests on inference |

## Your task
You are an independent reviewer. Work read-only: you may read files and rerun read-only probes; change nothing. For every unrefuted candidate, set your own evidence depth (0-10) from the facts given, using the depth anchors, and your own option rating (0-10), using the rating anchors; you are not shown the author's scores. If a probe refutes a candidate, quote the fact instead of a depth. For each refuted candidate, say whether the cited fact actually rules it out; if it does not, give it a depth and a rating like the others. Discard every candidate with depth 8 or below. For the survivors, check (a) technical soundness: will it break what currently works; (b) completeness: is a mandatory consequence missing (migration, dependency, restart, rollback); (c) target: does it address what the user actually asked, within their constraints. If an obvious alternative that could rate within 2 points of the best one is missing, name it as an objection and describe it, without a rating or depth. Return: depth and rating per candidate (or the refuting fact), which ones you discarded and why, and concrete objections for the survivors, or "no objections".
```
