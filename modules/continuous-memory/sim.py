#!/usr/bin/env python3
"""Local SIM adapter for the Continuous Memory store, using synthetic records only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import unicodedata

from ddh_memory import Store, canonical, digest, require, stamp
import sim_projection

ATTEMPT_SCHEMA = "ddh-sim-attempt/1"
RULES_SCHEMA = "ddh-sim-approved-rules/1"
EVENT_PREFIX = "sim.attempt:"
STATUSES = ("pass", "fail", "inconclusive", "not_run")
ENVIRONMENT = ("model", "harness", "project", "version")
PROBLEM_ID = re.compile(r"SIM-[0-9]{3,12}")
LOCAL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
MAX_INPUT = 512 * 1024


def fields(value, required, optional=()):
    require(type(value) is dict, "expected a JSON object")
    missing = set(required) - value.keys()
    extra = value.keys() - set(required) - set(optional)
    require(not missing and not extra,
            f"invalid fields (missing: {sorted(missing)}, unexpected: {sorted(extra)})")


def string(value, name, maximum=2000):
    require(isinstance(value, str) and value.strip() and len(value) <= maximum,
            f"{name}: expected nonempty text of at most {maximum} characters")
    return value


def identifier(value, pattern, name):
    require(isinstance(value, str) and pattern.fullmatch(value), f"invalid {name}")


def synthetic_source(value):
    string(value, "source", 512)
    require(value.startswith("synthetic:") and value[len("synthetic:"):].strip(),
            "pilot source must have a synthetic: locator")


def environment(value):
    fields(value, ENVIRONMENT)
    for name in ENVIRONMENT:
        string(value[name], name, 160)


def unique_fields(pairs):
    result = {}
    for name, value in pairs:
        require(name not in result, f"duplicate JSON field: {name}")
        result[name] = value
    return result


def parse_bytes(raw):
    require(len(raw) <= MAX_INPUT, "SIM input exceeds 512 KiB")
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_fields)


def read_input(path):
    with Path(path).open("rb") as handle:
        return parse_bytes(handle.read(MAX_INPUT + 1))


def validate_attempt(record):
    fields(record, ("schema_version", "problem", "attempt_id", "captured_at", "source",
                    "environment", "change", "rationale", "prediction", "result", "decision",
                    "evidence"), ("rule_version",))
    require(record["schema_version"] == ATTEMPT_SCHEMA, "unsupported SIM attempt schema")
    problem = record["problem"]
    fields(problem, ("id", "stage", "failure_type", "symptom", "criterion_key", "criterion", "related"))
    identifier(problem["id"], PROBLEM_ID, "problem ID")
    identifier(problem["criterion_key"], LOCAL_ID, "criterion key")
    for name, maximum in (("stage", 120), ("failure_type", 120), ("symptom", 480), ("criterion", 1200)):
        string(problem[name], name, maximum)
    related = problem["related"]
    require(isinstance(related, list) and len(related) <= 24, "expected up to 24 related problems")
    for ref in related:
        identifier(ref, PROBLEM_ID, "related problem ID")
    require(problem["id"] not in related and len(related) == len(set(related)),
            "invalid duplicate or self-referential problem link")
    identifier(record["attempt_id"], LOCAL_ID, "attempt ID")
    stamp(record["captured_at"], "captured_at")
    synthetic_source(record["source"])
    environment(record["environment"])
    for name in ("change", "rationale", "prediction", "decision"):
        string(record[name], name)
    if "rule_version" in record:
        string(record["rule_version"], "rule_version", 160)
    result = record["result"]
    fields(result, ("status", "observed"))
    require(result["status"] in STATUSES, "unknown measurement status")
    evidence = record["evidence"]
    require(isinstance(evidence, list) and len(evidence) <= 24, "expected up to 24 evidence items")
    evidence_ids = set()
    for item in evidence:
        fields(item, ("id", "source", "content"))
        identifier(item["id"], LOCAL_ID, "evidence ID")
        require(item["id"] not in evidence_ids, "duplicate evidence ID")
        evidence_ids.add(item["id"])
        synthetic_source(item["source"])
        string(item["content"], "evidence content", 32000)
    if result["status"] == "not_run":
        require(result["observed"] is None, "not_run requires a null observation")
    else:
        string(result["observed"], "observation", 4000)
        require(bool(evidence), "measured results require evidence")
    return record


def event_for(record):
    problem_id = record["problem"]["id"]
    attempt_id = record["attempt_id"]
    return {
        "schema_version": "ddh-memory-event/1",
        "event_id": f"{EVENT_PREFIX}{problem_id}:{attempt_id}",
        "owner": "profile", "kind": "source", "level": "source",
        "captured_at": record["captured_at"], "occurred_at": None,
        "visibility": "private", "basis": "synthetic",
        "title": f"SIM {problem_id} / {attempt_id}",
        "statement": "Synthetic improvement history. Open using the SIM evidence command.",
        "sources": [], "raw_refs": [], "supersedes": [],
        "coverage": {"status": "captured_sources_only", "limitations": []},
        "source_locator": record["source"],
    }


def comparable(text):
    # Keep case and punctuation in criteria, including case-sensitive technical terms.
    return unicodedata.normalize("NFC", " ".join(text.split()))


def check_identities(records):
    by_id, by_key, by_text = {}, {}, {}
    for record in records:
        problem = record["problem"]
        problem_id = problem["id"]
        key = problem["criterion_key"].casefold()
        criterion = comparable(problem["criterion"])
        details = (key, criterion, comparable(problem["stage"]), comparable(problem["failure_type"]),
                   comparable(problem["symptom"]))
        require(by_id.setdefault(problem_id, details) == details,
                f"{problem_id}: inconsistent canonical problem metadata")
        for mapping, identity in ((by_key, key), (by_text, criterion)):
            canonical_id = mapping.setdefault(identity, problem_id)
            require(canonical_id == problem_id, f"criterion already belongs to {canonical_id}")


def records_from(store, events):
    records = []
    for event in events.values():
        if not event["event_id"].startswith(EVENT_PREFIX):
            continue
        require(len(event["raw_refs"]) == 1, "SIM source requires one immutable attempt")
        ref = event["raw_refs"][0]
        raw = (store.root / "objects" / ref["sha256"]).read_bytes()
        require(len(raw) == ref["bytes"] and digest(raw) == ref["sha256"], "SIM source integrity failure")
        record = validate_attempt(parse_bytes(raw))
        expected = event_for(record)
        expected["raw_refs"] = [ref]
        require(event == expected and raw == canonical(record), "SIM payload and source event disagree")
        records.append(record)
    return records


def record_attempt(store, record):
    validate_attempt(record)
    payload = canonical(record)
    require(len(payload) <= MAX_INPUT, "canonical SIM record exceeds 512 KiB")

    def validate_locked(events):
        check_identities([*records_from(store, events), record])

    return store.ingest(event_for(record), raw_bytes=(payload,), validate_records=validate_locked)


def read_records(store):
    for name in ("events", "objects"):
        folder = store.root / name
        require(not folder.exists() or folder.is_dir(), f"invalid memory store directory: {name}")
    store.verify()
    records = records_from(store, store.all())
    check_identities(records)
    return records


def approved_rules(path):
    if path is None:
        return []
    registry = read_input(path)
    fields(registry, ("schema_version", "rules"))
    require(registry["schema_version"] == RULES_SCHEMA, "unsupported approved rule registry")
    rules = registry["rules"]
    require(isinstance(rules, list) and len(rules) <= 512, "invalid approved rules list")
    seen = set()
    for row in rules:
        fields(row, ("problem_id", "rule", "environment"))
        identifier(row["problem_id"], PROBLEM_ID, "approved problem ID")
        string(row["rule"], "approved rule", 4000)
        environment(row["environment"])
        key = (row["problem_id"], *(row["environment"][k] for k in ENVIRONMENT))
        require(key not in seen, "ambiguous approved rules for the same problem and environment")
        seen.add(key)
    return rules


def add_filters(parser, context=False):
    for key in ENVIRONMENT:
        option = "--project-name" if key == "project" else "--" + key
        parser.add_argument(option, dest=key, required=context)
    if not context:
        parser.add_argument("--stage")
        parser.add_argument("--failure-type")
        parser.add_argument("--status", choices=STATUSES)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    parsers = {op: sub.add_parser(op) for op in ("record", "index", "attempts", "evidence", "context")}
    for child in parsers.values():
        child.add_argument("--store", required=True)
    parsers["record"].add_argument("--input", required=True)
    add_filters(parsers["index"])
    add_filters(parsers["attempts"])
    parsers["attempts"].add_argument("--problem", required=True)
    parsers["attempts"].add_argument("--limit", type=int, choices=(1, 2, 3), default=3)
    parsers["evidence"].add_argument("--problem", required=True)
    parsers["evidence"].add_argument("--attempt", required=True)
    add_filters(parsers["context"], context=True)
    parsers["context"].add_argument("--approved-rules", help="Explicit, independently approved JSON rule registry")
    args = parser.parse_args(argv)
    store = Store(args.store)
    filters = {key: getattr(args, key) for key in (*ENVIRONMENT, "stage", "failure_type", "status")
               if getattr(args, key, None) is not None}
    try:
        if args.operation == "context":
            output = sim_projection.context([], filters, approved_rules(args.approved_rules))
        elif args.operation == "record":
            output = record_attempt(store, read_input(args.input))
        else:
            uninitialized = (args.operation in {"index", "attempts"}
                             and not store.root.exists() and not store.root.is_symlink())
            records = [] if uninitialized else read_records(store)
            if args.operation == "index":
                output = sim_projection.index(records, filters)
            elif args.operation == "attempts":
                output = sim_projection.attempts(records, args.problem, filters, args.limit)
            else:
                output = sim_projection.evidence(records, args.problem, args.attempt)
            if uninitialized:
                output["store_status"] = "uninitialized"
        print(json.dumps(output, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
