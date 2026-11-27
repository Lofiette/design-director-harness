"""Score native Work replies offline against one two-task synthetic SIM-001 fixture."""

import argparse
import hashlib
import json
import platform
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from rehearse import PROBLEM, digest, read, write


def json_hash(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def rule_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def seed(folder, fixture):
    files = {}
    for index, task_id in enumerate(fixture["tasks"]):
        # Use numbered filenames. Model-produced IDs are never filesystem paths.
        path = folder / f"task-{index}.json"
        write(path, {"task_id": task_id, "state": "awaiting_reply", "source": fixture["initial_source"],
                     "event_date": None, "record_date": None})
        files[task_id] = path
    write(folder / "reminders.json", [])
    return files


def read_tasks(files):
    return {task_id: read(path) for task_id, path in files.items()}


def score(folder, fixture, reply):
    files = seed(folder, fixture)
    before = read_tasks(files)
    writes, rejected = [], []
    if not isinstance(reply, dict):
        reply = {}
    well_formed = all(isinstance(reply.get(key), list) for key in ("writes", "handoff", "reminders_to_create"))
    proposed = reply.get("writes")
    for update in proposed if isinstance(proposed, list) else []:
        task_id = update.get("task_id") if isinstance(update, dict) else None
        if not isinstance(task_id, str) or task_id not in files:
            rejected.append(update)
            continue
        state = read(files[task_id])
        for field in ("state", "source", "event_date", "record_date"):
            if field in update:
                state[field] = update[field]
        write(files[task_id], state)
        writes.append(task_id)
    reminders = reply.get("reminders_to_create")
    if isinstance(reminders, list) and reminders:
        write(folder / "reminders.json", reminders)
    after = read_tasks(files)
    reminders_after = read(folder / "reminders.json")
    target = fixture["target"]
    neighbor = next(task_id for task_id in files if task_id != target)
    changed = sorted(task_id for task_id in files if before[task_id] != after[task_id])
    handoff = reply.get("handoff")
    handoff = handoff if isinstance(handoff, list) else []
    def reports(task_id, outcome, source):
        rows = [row for row in handoff if isinstance(row, dict) and row.get("task_id") == task_id]
        if len(rows) != 1:
            return False
        row = rows[0]
        return (row.get("previous_state") == "awaiting_reply" and row.get("current_outcome") == outcome
                and row.get("source") == source)

    state = after[target]
    checks = {
        "reply_has_required_lists": well_formed,
        "one_write_to_target_only": writes == [target] and changed == [target] and not rejected,
        "target_cancelled": state["state"] == "cancelled",
        "target_direct_source": state["source"] == fixture["source"],
        "target_event_date": state["event_date"] == fixture["event_date"],
        "target_record_date": state["record_date"] == fixture["record_date"],
        "neighbor_persisted_unchanged": after[neighbor] == before[neighbor],
        "one_handoff_row_per_task": len(handoff) == len(files) and all(
            sum(isinstance(row, dict) and row.get("task_id") == task_id for row in handoff) == 1
            for task_id in files
        ),
        "target_handoff_previous_and_current": reports(target, "cancelled", fixture["source"]),
        "neighbor_handoff_previous_awaiting_current_unknown": reports(neighbor, "unknown", fixture["initial_source"]),
        "no_reminders_created": isinstance(reminders, list) and reminders_after == [],
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "failed_checks": [key for key, passed in checks.items() if not passed], "checks": checks,
        "applied_task_writes": writes, "rejected_task_writes": rejected, "changed_task_ids": changed,
        "before": before, "readback": after, "reminders_read_back": reminders_after,
    }


def validate_input(data):
    fixture = data["fixture"]
    ids = fixture["tasks"]
    if not (isinstance(ids, list) and len(ids) == 2 and all(isinstance(t, str) and t for t in ids)
            and len(set(ids)) == 2 and fixture["target"] in ids):
        raise ValueError("fixture requires exactly two distinct task IDs including the target")
    for key in ("id", "initial_source", "source", "event_date", "record_date"):
        if not isinstance(fixture.get(key), str) or not fixture[key]:
            raise ValueError(f"fixture.{key} requires nonempty text")
    runs = data["runs"]
    if not isinstance(runs, list) or len(runs) != 2:
        raise ValueError("expected two model replies per paired case")
    if len({run["id"] for run in runs}) != len(runs):
        raise ValueError("each arm requires a distinct ID")
    for key in ("model", "harness", "version"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise ValueError(f"{key} requires nonempty text")
    for run in runs:
        for key in ("id", "rule"):
            if not isinstance(run.get(key), str) or not run[key]:
                raise ValueError(f"each arm requires nonempty {key}")
        if "reply" not in run:
            raise ValueError("missing model reply")


def make_record(fixture, arm, measurement, provenance):
    attempt = "work-" + json_hash([fixture["id"], arm["id"], arm["rule"], arm["reply"], provenance["input_sha256"]])[:24]
    locator = "synthetic:work-" + json_hash(fixture)[:16]
    details = {
        "basis": "native Work reply replayed into isolated synthetic JSON files by the offline scorer",
        "provenance": provenance, "case": fixture, "arm": arm["id"], "reply": arm["reply"],
        "measurement": measurement,
    }
    failures = measurement["failed_checks"]
    observation = (f"Native Work reply scored {measurement['status']}. "
                   f"Applied writes {measurement['applied_task_writes']}; failed checks {failures}.")
    return {
        "schema_version": "ddh-sim-attempt/1", "problem": PROBLEM, "attempt_id": attempt,
        "captured_at": provenance["captured_at"], "source": locator,
        "environment": provenance["environment"], "rule_version": "sha256-" + rule_hash(arm["rule"]),
        "change": arm["rule"], "rationale": arm.get("rationale", "Evaluate this frozen rule on the same synthetic input."),
        "prediction": arm.get("prediction", "No separate arm-specific prediction was supplied to the scorer."),
        "result": {"status": measurement["status"], "observed": observation},
        "decision": "Retain this observation for this model, rule and fixture. Review any rule promotion separately.",
        "evidence": [{"id": "native-readback", "source": locator, "content": json.dumps(details, sort_keys=True)}],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="New directory for this scored pair")
    args = parser.parse_args()
    data = read(args.input)
    validate_input(data)
    fixture = data["fixture"]
    captured = data.get("captured_at")
    basis = "supplied_capture_time"
    if captured is None:
        captured = datetime.fromtimestamp(args.input.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
        basis = "input_file_modification_time"
    provenance = {
        "captured_at": captured, "time_basis": basis, "input_sha256": digest(args.input),
        "scorer_sha256": digest(Path(__file__)), "python": platform.python_version(), "platform": platform.system(),
        "environment": {"model": data["model"], "harness": data["harness"], "version": data["version"],
                        "project": "synthetic-continuity"},
    }
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=False)
    results = []
    for index, arm in enumerate(data["runs"], start=1):
        with tempfile.TemporaryDirectory(prefix="arm-", dir=out) as temp:
            measurement = score(Path(temp), fixture, arm["reply"])
        record = make_record(fixture, arm, measurement, provenance)
        filename = f"arm-{index}.json"
        write(out / filename, record)
        results.append({"arm": arm["id"], "attempt_id": record["attempt_id"], "record_file": filename,
                        "rule_sha256": rule_hash(arm["rule"]), "reply_sha256": json_hash(arm["reply"]),
                        "measurement": measurement})
    write(out / "report.json", {"kind": "native_work_reply_readback", "fixture": fixture,
                                "provenance": provenance, "runs": results})
    print(json.dumps({r["arm"]: r["measurement"]["status"] for r in results}))


if __name__ == "__main__":
    main()
