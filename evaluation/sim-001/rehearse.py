"""Run one synthetic paired code rehearsal and emit SIM input plus readback evidence."""

import argparse
import hashlib
import json
import platform
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
CASE = HERE / "case.json"
PROBLEM = {
    "id": "SIM-001",
    "stage": "context_handoff",
    "failure_type": "state_update_scope",
    "symptom": "A cancellation may incorrectly close another pending task.",
    "criterion_key": "task-scoped-handoff",
    "criterion": "Apply only the explicit task change with its direct source and both dates; preserve the neighbor's last known state and avoid duplicate reminders.",
    "related": [],
}
RULES = {
    "baseline": (
        "Reconcile a direct update against the pending task with a unique matching title.",
        "An evidence-based recovery keeps pending decisions open until settled. Title matching is an illustrative implementation for this code rehearsal.",
    ),
    "candidate": (
        "Apply a direct update only to a task whose stable ID and title match the source.",
        "An explicit identity check binds the cancellation to its named task.",
    ),
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def setup(folder, first):
    for item in first["pending"]:
        task = {
            **item,
            "last_known_status": "awaiting_reply",
            "current_outcome": None,
            "source": first["id"],
            "occurred_at": first["occurred_at"],
            "captured_at": first["captured_at"],
            "reminders": [],
        }
        write(folder / (task["task_id"] + ".json"), task)


def snapshot(folder):
    return {path.stem: read(path) for path in sorted(folder.glob("*.json"))}


def resolve_target(variant, tasks, change):
    if variant == "candidate":
        task = tasks.get(change["task_id"])
        if task and task["title"] == change["title"]:
            return task["task_id"]
        return None
    matches = [task_id for task_id, task in tasks.items() if task["title"] == change["title"]]
    return matches[0] if len(matches) == 1 else None


def run_variant(folder, variant, sources):
    # Each variant starts from the identical first source in its own empty directory.
    setup(folder, sources[0])
    before = snapshot(folder)
    notice = sources[1]
    writes = []
    for change in notice["changes"]:
        target = resolve_target(variant, snapshot(folder), change)
        if target is None:
            continue
        path = folder / (target + ".json")
        task = read(path)
        task.update(
            last_known_status=change["outcome"], current_outcome=change["outcome"],
            source=notice["id"], occurred_at=notice["occurred_at"], captured_at=notice["captured_at"],
        )
        write(path, task)
        writes.append(target)

    # Score the persisted files after reopening, separately from the policy's target selection.
    after = snapshot(folder)
    a, b = after["A"], after["B"]
    changed = sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
    checks = {
        "one_persisted_change_to_A": writes == ["A"] and changed == ["A"],
        "A_cancelled": a["current_outcome"] == "cancelled",
        "direct_source": a["source"] == "synthetic:notice-02",
        "event_date": a["occurred_at"] == "2026-10-03T14:00:00Z",
        "capture_date": a["captured_at"] == "2026-10-05T10:00:00Z",
        "B_still_waiting_outcome_unknown": b == before["B"] and b["last_known_status"] == "awaiting_reply" and b["current_outcome"] is None,
        "no_new_reminder_for_A": len(a["reminders"]) == len(before["A"]["reminders"]) == 0,
    }
    return {
        "status": "pass" if all(checks.values()) else "fail", "checks": checks,
        "task_writes": writes, "changed_task_ids": changed, "before": before, "readback": after,
    }


def make_record(variant, evidence, run):
    change, rationale = RULES[variant]
    status = evidence["status"]
    return {
        "schema_version": "ddh-sim-attempt/1", "problem": PROBLEM,
        "attempt_id": variant + "-" + run["run_id"], "captured_at": run["captured_at"],
        "source": "synthetic:SIM-001-pair-v1", "environment": run["environment"],
        "rule_version": variant + "-proxy-v1", "change": change, "rationale": rationale,
        "prediction": "The directly named task alone will change; the neighbor's current outcome stays unknown.",
        "result": {"status": status, "observed": (
            f"Code rehearsal {status}. Wrote {evidence['task_writes']}; "
            f"reopened state differed for {evidence['changed_task_ids']}. "
            f"Passed {sum(evidence['checks'].values())}/{len(evidence['checks'])} checks."
        )},
        "decision": "Retain this synthetic measurement for review. Model evaluation is pending.",
        "evidence": [{
            "id": variant + "-readback-" + run["run_id"], "source": "synthetic:SIM-001-pair-v1",
            "content": json.dumps({"provenance": run, "measurement": evidence}, sort_keys=True),
        }],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="New output directory for this measurement")
    args = parser.parse_args()
    case = read(CASE)
    ddh_version = read(HERE.parent.parent / "manifest.json")["version"]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    run = {
        "run_id": uuid.uuid4().hex[:12],
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "kind": "deterministic_code_rehearsal", "case_id": case["case_id"],
        "case_sha256": digest(CASE), "runner_sha256": digest(Path(__file__)),
        "platform": platform.system(), "python": platform.python_version(),
        "environment": {"model": "not_run", "harness": "DDH", "project": "synthetic-continuity", "version": ddh_version},
    }
    results = {}
    for variant in RULES:
        with tempfile.TemporaryDirectory(prefix=variant + "-", dir=out) as tmp:
            evidence = run_variant(Path(tmp), variant, case["sources"])
        results[variant] = evidence
        write(out / (variant + ".json"), make_record(variant, evidence, run))
    report = {
        **run, "rules": RULES, "code_results": results,
        "model_tests": {
            "baseline_vs_candidate": "not_run", "adaptation_with_vs_without_measured_log": "not_run",
            "blinded_held_out_evaluation": "not_run",
            "reason": "This runner only executes deterministic Python policies on synthetic data.",
        },
    }
    write(out / "report.json", report)
    print(json.dumps({"report": str(out / "report.json"), "outcomes": {v: r["status"] for v, r in results.items()}}))
    return int(any(r["status"] != "pass" for r in results.values()))


if __name__ == "__main__":
    sys.exit(main())
