import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join } from "node:path";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { cases, profiles } from "../evaluation/cases.mjs";

const bench = fileURLToPath(new URL("../evaluation/bench.mjs", import.meta.url));
const parent = realpathSync(tmpdir());
const scratch = mkdtempSync(join(parent, "ddh-bench-test-"));
const root = join(scratch, "benchmark");
const call = (...args) => spawnSync(process.execPath, [bench, ...args], { encoding: "utf8" });
const ok = (...args) => {
  const result = call(...args);
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
};
const capture = (id, phase) => ok("capture", "--suite", root, "--run", id, "--phase", phase);
const report = id => ok("report", "--suite", root).runs.find(run => run.id === id);
const project = id => join(root, id, "project");
const write = (id, path, contents) => writeFileSync(join(project(id), path), contents);
function review(id, caseId, fields = {}) {
  const checks = Object.fromEntries(Object.keys(cases[caseId].rubric).map(checkId =>
    [checkId, { pass: true, evidence: "Synthetic grading test for " + checkId }]));
  writeFileSync(join(root, id, "review.json"), JSON.stringify({ status: "completed", checks, ...fields }));
}

after(() => {
  const target = realpathSync(scratch);
  assert.equal(dirname(target), parent);
  assert.match(basename(target), /^ddh-bench-test-[a-zA-Z0-9]+$/);
  rmSync(target, { recursive: true });
});

test("prepare creates nine identical inputs, keeps operator guidance separate and starts pending", () => {
  assert.equal(ok("prepare", "--out", root).runs, 9);
  assert.notEqual(call("prepare", "--out", root).status, 0);
  for (const profile of profiles) {
    for (const [id, entry] of Object.entries(cases)) {
      const run = profile + "-" + id;
      for (const [path, contents] of Object.entries(entry.files)) {
        assert.equal(readFileSync(join(project(run), path), "utf8"), contents);
      }
      assert.equal(existsSync(join(project(run), "review.template.json")), false);
      capture(run, "initial");
    }
  }
  assert.ok(ok("report", "--suite", root).runs.every(run => run.status === "PENDING"));
});

test("micro change checks byte-exact output and distinguishes missing evidence and collateral edits", () => {
  const good = "ddh-5.0-copy";
  write(good, "action.html", cases.copy.expected["action.html"]);
  assert.equal(spawnSync(process.execPath, ["check.mjs"], { cwd: project(good) }).status, 0);
  capture(good, "final");
  review(good, "copy", { checks: {} });
  assert.equal(report(good).status, "PENDING");
  review(good, "copy", { metrics: { inputTokens: 200, cachedInputTokens: 40 } });
  assert.equal(report(good).status, "PASS");
  assert.equal(report(good).metrics.elapsedMs, null);

  const bad = "codex-plain-copy";
  write(bad, "action.html", cases.copy.expected["action.html"]);
  write(bad, "extra.txt", "unexpected");
  capture(bad, "final");
  review(bad, "copy");
  assert.equal(report(bad).status, "FAIL");
  assert.match(report(bad).failures.join(), /extra\.txt/);
});

test("UX needs a recorded question before product edits and an independently graded design", () => {
  const good = "ddh-5.0-ux";
  assert.notEqual(call("capture", "--suite", root, "--run", good, "--phase", "final").status, 0);
  capture(good, "first");
  write(good, "design.md", "Synthetic design evidence");
  capture(good, "final");
  review(good, "ux", { question: "Кто заполняет форму и где возникает сбой?" });
  assert.equal(report(good).status, "PASS");

  const bad = "codex-plain-ux";
  write(bad, "design.md", "Premature design");
  capture(bad, "first");
  capture(bad, "final");
  review(bad, "ux");
  assert.equal(report(bad).status, "FAIL");
  assert.deepEqual(report(bad).failures, ["product changed before clarification", "no first question recorded"]);
});

test("recovery requires a new first-stage handoff, protects evidence and reports blocked runs", () => {
  const good = "ddh-5.0-recovery";
  const handoff = ".ddh/handoff.md";
  mkdirSync(join(project(good), ".ddh"));
  write(good, handoff, "Recorded next operation");
  capture(good, "first");
  write(good, "status.txt", cases.recovery.expected["status.txt"]);
  capture(good, "final");
  review(good, "recovery", { handoffPath: handoff });
  assert.equal(report(good).status, "PASS");
  assert.equal(report(good).serviceFilesChanged, 1);
  review(good, "recovery", { handoffPath: "evidence.txt" });
  assert.match(report(good).failures.join(), /missing first-stage handoff/);
  const blocked = "product-os-4.1-recovery";
  review(blocked, "recovery", { status: "blocked", notes: "Synthetic environment failure" });
  assert.equal(report(blocked).status, "BLOCKED");
});
