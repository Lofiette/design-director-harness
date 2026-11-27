import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join } from "node:path";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";

const parent = realpathSync(tmpdir());
const scratch = mkdtempSync(join(parent, "ddh-sim-test-"));
const cli = fileURLToPath(new URL("../tools/ddh.mjs", import.meta.url));
const python = process.env.DDH_TEST_PYTHON ?? "python";
const skills = ["ddh-decision-audit", "ddh-design", "ddh-direct", "ddh-recover", "ddh-verify"];
const environment = {
  model: "synthetic-model", harness: "fixture-host", project: "fixture-project", version: "5.0.1",
};
const problem = {
  id: "SIM-001", stage: "handoff", failure_type: "task-state", symptom: "Closing the adjacent task",
  criterion_key: "cancel-only-target", criterion: "Only the explicitly cancelled task is closed.", related: [],
};

after(() => {
  const target = realpathSync(scratch);
  assert.equal(dirname(target), parent);
  assert.match(basename(target), /^ddh-sim-test-[a-zA-Z0-9]+$/);
  rmSync(target, { recursive: true });
});

function command(...args) {
  const result = spawnSync(process.execPath, [cli, ...args], { encoding: "utf8" });
  assert.ifError(result.error);
  return result;
}

function success(result) {
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return JSON.parse(result.stdout);
}

function rejected(result) {
  assert.notEqual(result.status, 0, result.stdout);
  assert.ok(result.stderr.trim(), "a failed command should explain why");
}

function install(action, project, ...options) {
  return success(command(action, "--project", project, "--python", python, ...options));
}

function sim(project, operation, ...options) {
  return command("sim", "--project", project, "--python", python, operation, ...options);
}

function receipt(project) {
  return JSON.parse(readFileSync(join(project, ".agents/ddh-install.json"), "utf8"));
}

function syntheticAttempt(id, status, day, overrides = {}) {
  const observed = {
    pass: "Only A was closed, its source and two dates were retained.",
    fail: "Both A and B were closed.",
  };
  return {
    schema_version: "ddh-sim-attempt/1", problem, attempt_id: id, captured_at: `2030-05-${day}T00:00:00Z`,
    source: "synthetic:handoff-fixture", environment, change: "Scope cancellation to its explicit target.",
    rationale: "An update names only one task.", prediction: "Only A will close.",
    result: { status, observed: observed[status] ?? null },
    decision: "Review before applying.", evidence: status === "not_run" ? [] : [
      { id: "readback", source: "synthetic:readback", content: `Full readback for ${id}: ${observed[status]}` },
    ],
    ...overrides,
  };
}

function storeAttempt(project, item) {
  const input = join(scratch, "synthetic-attempt.json");
  writeFileSync(input, JSON.stringify(item));
  return sim(project, "record", "--input", input);
}

test("fresh default stays at five skills and the SIM entry point is disabled", () => {
  const project = join(scratch, "default");
  mkdirSync(project);
  assert.equal(install("install", project).skills, 5);
  assert.deepEqual(readdirSync(join(project, ".agents/skills")).sort(), skills);
  const installed = receipt(project);
  assert.equal(installed.schema, "ddh-install-v1");
  assert.equal(Object.hasOwn(installed, "modules"), false);
  assert.equal(Object.keys(installed.files).some(path => path.endsWith("/sim.py")), false);
  rejected(sim(project, "index"));
  assert.equal(install("update", project).status, "unchanged");
});

test("opt-in installed CLI records, rebuilds and discloses evidence by request", () => {
  const project = join(scratch, "opt-in");
  mkdirSync(project);
  assert.equal(install("install", project, "--modules", "sim").skills, 5);
  assert.deepEqual(readdirSync(join(project, ".agents/skills")).sort(), skills);
  const installed = receipt(project);
  assert.deepEqual(installed.modules, ["sim"]);
  const managedCode = Object.keys(installed.files).filter(path => path.endsWith("/sim.py"));
  assert.equal(managedCode.length, 1);
  assert.ok(existsSync(join(project, managedCode[0])));
  const guidance = readFileSync(join(project, "AGENTS.md"));
  const index = (...args) => success(sim(project, "index", ...args));

  const fresh = index();
  assert.deepEqual(fresh.cards, []);
  assert.equal(fresh.store_status, "uninitialized");
  const sharedStore = join(project, ".cpt", "continuous-memory");
  assert.equal(existsSync(sharedStore), false, "reading an empty index must not create a store");
  const missed = syntheticAttempt("missed", "fail", "01");
  assert.equal(success(storeAttempt(project, missed)).status, "created");
  assert.equal(success(storeAttempt(project, missed)).status, "duplicate");
  const beforeConflict = index();
  rejected(storeAttempt(project, { ...missed, prediction: "Different prediction for the same immutable attempt." }));
  rejected(storeAttempt(project, { ...missed, attempt_id: "other-id", problem: { ...problem, id: "SIM-002" } }));
  rejected(storeAttempt(project, {
    ...missed, attempt_id: "other-key",
    problem: { ...problem, id: "SIM-002", criterion_key: "alias-key", criterion: problem.criterion.replace(" the ", "   the  ") },
  }));
  rejected(storeAttempt(project, {
    ...missed, attempt_id: "other-criterion",
    problem: { ...problem, criterion_key: "different-target", criterion: "A distinct criterion." },
  }));
  assert.deepEqual(index(), beforeConflict);

  const pending = syntheticAttempt("pending", "not_run", "02", {
    prediction: "A high-confidence predicted PASS is still only a forecast.",
  });
  assert.equal(success(storeAttempt(project, pending)).status, "created");
  rejected(storeAttempt(project, { ...pending, attempt_id: "no-proof", result: { status: "pass", observed: null } }));
  const passed = syntheticAttempt("verified", "pass", "03");
  assert.equal(success(storeAttempt(project, passed)).status, "created");
  const elsewhere = { ...environment, model: "second-model" };
  const other = syntheticAttempt("unmeasured-elsewhere", "not_run", "04", { environment: elsewhere });
  assert.equal(success(storeAttempt(project, other)).status, "created");

  const all = index();
  assert.deepEqual(index(), all, "rebuilding the projection from the same events is deterministic");
  const kernel = Object.keys(installed.files).find(path => path.endsWith("/ddh_memory.py"));
  assert.ok(kernel);
  const verified = success(spawnSync(python, ["-B", join(project, kernel), "verify", "--store", sharedStore],
    { encoding: "utf8" }));
  assert.equal(verified.events, 4);
  assert.equal(verified.referenced_raw_objects, 4);
  assert.equal(all.cards.length, 1);
  assert.equal(all.cards[0].problem_id, "SIM-001");
  assert.equal(all.cards[0].attempt_count, 4);
  assert.equal(all.cards[0].latest_verified.attempt_id, "verified");
  assert.deepEqual(all.tree.handoff["task-state"], ["SIM-001"]);
  assert.ok(!JSON.stringify(all).includes("Full readback"));
  assert.ok(!JSON.stringify(all).includes(pending.prediction));
  assert.equal(index("--stage", "unrelated").cards.length, 0);
  assert.equal(index("--failure-type", "unrelated").cards.length, 0);
  assert.equal(index("--harness", "other").cards.length, 0);
  assert.equal(index("--version", "other").cards.length, 0);
  assert.equal(index("--project-name", "other").cards.length, 0);
  const unverified = index("--model", "second-model", "--status", "not_run").cards;
  assert.equal(unverified.length, 1);
  assert.equal(unverified[0].latest_verified, null, "another model's pass cannot qualify this environment");
  const attempts = (...args) => success(sim(project, "attempts", "--problem", "SIM-001", ...args)).attempts;
  assert.equal(attempts().length, 3);
  assert.equal(attempts("--limit", "1").length, 1);
  rejected(sim(project, "attempts", "--problem", "SIM-001", "--limit", "4"));
  const [failed] = attempts("--status", "fail");
  assert.equal(failed.attempt_id, "missed");
  assert.equal(failed.result.observed, missed.result.observed);
  assert.deepEqual(failed.evidence_ids, ["readback"]);
  assert.ok(!JSON.stringify(failed).includes("Full readback"));
  const notRun = attempts("--status", "not_run");
  assert.equal(notRun.length, 2);
  assert.ok(notRun.every(row => row.result.observed === null));
  const evidence = success(sim(project, "evidence", "--problem", "SIM-001", "--attempt", "missed"));
  assert.equal(evidence.source, missed.source);
  assert.deepEqual(evidence.evidence, missed.evidence);

  const scope = ["--project-name", environment.project, "--model", environment.model,
    "--harness", environment.harness, "--version", environment.version];
  assert.deepEqual(success(sim(project, "context", ...scope)), { rules: [] });
  const approved = join(scratch, "synthetic-approved-rules.json");
  const rule = "Only close the explicitly named task.";
  writeFileSync(approved, JSON.stringify({
    schema_version: "ddh-sim-approved-rules/1", rules: [{ problem_id: "SIM-001", rule, environment }],
  }));
  assert.deepEqual(success(sim(project, "context", ...scope, "--approved-rules", approved)),
    { rules: [{ problem_id: "SIM-001", rule }] });
  const wrongScope = scope.map(value => value === environment.model ? "future-model" : value);
  assert.deepEqual(success(sim(project, "context", ...wrongScope, "--approved-rules", approved)), { rules: [] });
  assert.deepEqual(readFileSync(join(project, "AGENTS.md")), guidance);

  assert.equal(install("update", project).status, "unchanged");
  assert.deepEqual(index(), all);
  install("update", project, "--modules", "none");
  assert.equal(existsSync(join(project, managedCode[0])), false);
  rejected(sim(project, "index"));
  install("update", project, "--modules", "sim");
  assert.deepEqual(index(), all, "toggling the installer preserves the underlying memory store");

  const secondProblem = {
    ...problem, id: "SIM-002", failure_type: "source-dates", symptom: "Recording date replaces event date.",
    criterion_key: "retain-both-dates", criterion: "Record and event dates remain distinct.", related: ["SIM-001"],
  };
  assert.equal(success(storeAttempt(project, { ...pending, problem: secondProblem })).status, "created");
  const secondCard = index("--failure-type", "source-dates").cards;
  assert.equal(secondCard.length, 1);
  assert.equal(secondCard[0].problem_id, "SIM-002");
  assert.deepEqual(secondCard[0].related, ["SIM-001"]);

  const adapter = join(project, managedCode[0]);
  writeFileSync(adapter, "# locally edited managed adapter\n");
  rejected(sim(project, "index"));
  rejected(command("update", "--project", project, "--python", python, "--modules", "none"));
  assert.equal(readFileSync(adapter, "utf8"), "# locally edited managed adapter\n");
});

test("a failed recheck retires the same rule in its environment and keeps its original pass in history", () => {
  const project = join(scratch, "rechecked-rule");
  mkdirSync(project);
  install("install", project, "--modules", "sim");
  const original = syntheticAttempt("original-pass", "pass", "05", { rule_version: "rule-1" });
  const recheck = syntheticAttempt("same-rule-fails", "fail", "06", { rule_version: "rule-1" });
  const pending = syntheticAttempt("new-rule-proposed", "not_run", "07", {
    rule_version: "rule-2", change: "Consider both sources before assigning a final state.",
  });
  const current = (...args) => success(sim(project, "index", ...args)).cards[0];

  assert.equal(success(storeAttempt(project, original)).status, "created");
  assert.equal(current().latest_verified.attempt_id, "original-pass");
  assert.equal(success(storeAttempt(project, recheck)).status, "created");
  assert.equal(success(storeAttempt(project, pending)).status, "created");
  assert.equal(current().latest_status, "not_run");
  assert.equal(current().latest_verified, null);
  assert.equal(current("--status", "pass").latest_verified, null,
    "filtering the history for passes must not restore an invalidated rule");
  const history = success(sim(project, "attempts", "--problem", problem.id, "--status", "pass"));
  assert.deepEqual(history.attempts.map(row => row.attempt_id), ["original-pass"]);
  const full = success(sim(project, "evidence", "--problem", problem.id, "--attempt", "original-pass"));
  assert.deepEqual(full.record, original);
});
