"""Read-only SIM views over verified Continuous Memory records."""
from datetime import datetime

from ddh_memory import Invalid

ENVIRONMENT = ("model", "harness", "project", "version")


def _matches(record, filters):
    for field, expected in filters.items():
        if field in ENVIRONMENT:
            actual = record["environment"][field]
        elif field == "status":
            actual = record["result"]["status"]
        else:
            actual = record["problem"][field]
        if actual != expected:
            return False
    return True


def _newest(records):
    def order(record):
        captured = datetime.fromisoformat(record["captured_at"].replace("Z", "+00:00"))
        return captured, record["attempt_id"]
    return sorted(records, key=order, reverse=True)


def _excerpt(value, limit):
    if value is None:
        return None
    line = " ".join(value.split())
    return line if len(line) <= limit else line[:limit - 1].rstrip() + "…"


def _rule_scope(record):
    environment = tuple(record["environment"][key] for key in ENVIRONMENT)
    version = record.get("rule_version") or record["change"]
    return record["problem"]["id"], environment, version


def index(records, filters):
    # Classify prior measurements before filtering. A status filter cannot revive a regressed rule.
    links, groups, last_measured = {}, {}, {}
    known = set()
    for record in _newest(records):
        problem = record["problem"]
        problem_id = problem["id"]
        known.add(problem_id)
        links.setdefault(problem_id, set()).update(problem["related"])
        for other in problem["related"]:
            links.setdefault(other, set()).add(problem_id)
        if record["result"]["status"] != "not_run":
            last_measured.setdefault(_rule_scope(record), record["attempt_id"])
        if _matches(record, filters):
            groups.setdefault(problem_id, []).append(record)

    cards, tree = [], {}
    for problem_id, group in sorted(groups.items()):
        latest = group[0]
        problem = latest["problem"]
        passed = next((r for r in group if r["result"]["status"] == "pass"
                       and r["attempt_id"] == last_measured[_rule_scope(r)]), None)
        verified = None
        if passed:
            verified = {
                "attempt_id": passed["attempt_id"],
                "environment": passed["environment"],
                "source": passed["source"],
                "captured_at": passed["captured_at"],
                "change": _excerpt(passed["change"], 160),
            }
        cards.append({
            "problem_id": problem_id,
            "stage": problem["stage"],
            "failure_type": problem["failure_type"],
            "symptom": _excerpt(problem["symptom"], 160),
            "criterion": _excerpt(problem["criterion"], 160),
            "related": sorted(links[problem_id] & known),
            "unresolved_related": sorted(links[problem_id] - known),
            "attempt_count": len(group),
            "latest_status": latest["result"]["status"],
            "latest_verified": verified,
        })
        failures = tree.setdefault(problem["stage"], {})
        failures.setdefault(problem["failure_type"], []).append(problem_id)
    return {"cards": cards, "tree": tree}


def attempts(records, problem, filters, limit):
    if not 1 <= limit <= 3:
        raise Invalid("select between one and three attempts")
    relevant = (r for r in records if r["problem"]["id"] == problem and _matches(r, filters))
    entries = []
    for record in _newest(relevant)[:limit]:
        result = record["result"]
        entries.append({
            "attempt_id": record["attempt_id"],
            "captured_at": record["captured_at"],
            "environment": record["environment"],
            "rule_version": record.get("rule_version"),
            "change": _excerpt(record["change"], 320),
            "rationale": _excerpt(record["rationale"], 320),
            "prediction": _excerpt(record["prediction"], 320),
            "result": {"status": result["status"], "observed": _excerpt(result["observed"], 480)},
            "decision": _excerpt(record["decision"], 320),
            "evidence_ids": [item["id"] for item in record["evidence"]],
        })
    return {"problem_id": problem, "attempts": entries}


def evidence(records, problem, attempt):
    for record in records:
        if record["problem"]["id"] == problem and record["attempt_id"] == attempt:
            return {
                "problem_id": problem, "attempt_id": attempt, "source": record["source"],
                "evidence": record["evidence"], "record": record,
            }
    raise Invalid("unknown problem/attempt pair")


def context(records, filters, approved_rules):
    # A measured result cannot authorize a rule. This view reads only the caller's registry.
    environment = {key: filters[key] for key in ENVIRONMENT}
    matches = {}
    for row in approved_rules:
        if row["environment"] != environment:
            continue
        problem_id = row["problem_id"]
        if problem_id in matches and matches[problem_id] != row["rule"]:
            raise Invalid("conflicting approved rules for " + problem_id)
        matches[problem_id] = row["rule"]
    return {"rules": [{"problem_id": key, "rule": matches[key]} for key in sorted(matches)]}
