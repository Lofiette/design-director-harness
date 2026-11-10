import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join } from "node:path";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { installProject } from "../tools/project-install.mjs";

const cli = fileURLToPath(new URL("../tools/ddh.mjs", import.meta.url));
const scratchParent = realpathSync(tmpdir());
const scratch = mkdtempSync(join(scratchParent, "ddh-5-test-"));
const codex = join(scratch, "codex");
const dsh = join(scratch, "dsh");
const codexSkills = join(codex, "plugins/design-director-harness/skills");
const dshSkills = join(dsh, ".dsh/skills");
const read = path => readFileSync(path, "utf8");
const json = path => JSON.parse(read(path));
const version = JSON.parse(readFileSync(new URL("../manifest.json", import.meta.url), "utf8")).version;

function invoke(...args) {
  if (["install", "update"].includes(args[0])) args.push("--python", process.env.DDH_TEST_PYTHON ?? "python");
  const result = spawnSync(process.execPath, [cli, ...args], { encoding: "utf8", cwd: scratch });
  assert.ifError(result.error);
  return result;
}

function ok(...args) {
  const result = invoke(...args);
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

function rejects(pattern, ...args) {
  const result = invoke(...args);
  assert.equal(result.status, 1, result.stderr);
  assert.match(result.stderr, pattern);
}

before(() => {
  ok("pack", "--host", "codex", "--out", codex);
  ok("pack", "--host", "dsh", "--out", dsh);
});

after(() => {
  const target = realpathSync(scratch);
  assert.equal(dirname(target), scratchParent);
  assert.match(basename(target), /^ddh-5-test-[a-zA-Z0-9]+$/);
  rmSync(target, { recursive: true });
});

test("doctor reports both hosts, five canonical skills and source provenance", () => {
  const result = ok("doctor");
  assert.deepEqual(result.hosts, ["codex", "dsh"]);
  assert.equal(result.version, version);
  assert.equal(result.skills.length, 5);
  assert.ok(result.sources >= 10);
  assert.deepEqual(result.runtime, { id: "cpt", upstreamVersion: "4.1.0" });
  assert.equal(result.optionalPacks.length, 5);
});

test("exports are byte-equivalent, hash-verified and use valid host layouts", () => {
  const plugin = json(join(codex, "plugins/design-director-harness/.codex-plugin/plugin.json"));
  const marketplace = json(join(codex, ".agents/plugins/marketplace.json"));
  assert.equal(marketplace.plugins[0].source.path, "./plugins/design-director-harness");
  assert.equal(plugin.skills, "./skills/");
  assert.equal(plugin.version, version);
  for (const [root, host] of [[codex, "codex"], [dsh, "dsh"]]) {
    const receipt = json(join(root, "ddh-pack.json"));
    assert.equal(receipt.host, host);
    for (const [path, expected] of Object.entries(receipt.files)) {
      assert.equal(createHash("sha256").update(readFileSync(join(root, path))).digest("hex"), expected);
    }
    assert.equal(existsSync(join(root, "sources.json")), false);
  }
  for (const id of ok("doctor").skills) {
    assert.deepEqual(readFileSync(join(codexSkills, id, "SKILL.md")), readFileSync(join(dshSkills, id, "SKILL.md")));
  }
});

test("both bootstraps wait on consequential intake and preserve a micro path", () => {
  assert.equal(read(join(codex, "AGENTS.md")), read(join(dsh, "AGENTS.md")));
  const bootstrap = read(join(codex, "AGENTS.md"));
  assert.match(bootstrap, /new substantive.*load ddh-direct/);
  assert.match(bootstrap, /Start work directly when the required inputs are clear/);
  assert.match(bootstrap, /pause all dependent work until the answer arrives/);
  assert.match(bootstrap, /DDH owns intake\. CPT owns the task record/);
  assert.match(bootstrap, /non-interactive runs, put the question in the final response and end the turn/i);
  const route = read(join(codexSkills, "ddh-direct/SKILL.md"));
  assert.match(route, /Do not create or edit a dependent artifact, including a draft/);
  assert.match(route, /Elapsed time, a tool acknowledgement or silence never settles the question/);
  assert.match(route, /Do not poll or sleep for a reply/);
  assert.match(route, /including `codex exec`.*Put the question in the final response and end the turn/);
  assert.match(route, /If it only delivers the question, end the turn without repeating it/);
  assert.match(route, /continue from the blocked step/);
  assert.match(route, /Ask only about a still-material gap in a partial answer/);
  assert.match(route, /If they cancel, stop that task/);
  assert.match(route, /If they explicitly replace the task, close the pending question/);
  assert.match(route, /An unrelated reply leaves the question open/);
  assert.match(route, /reversible edit.*directly from inspection to edit to verification/);
});

test("design, decision audit and recovery route consequential questions through intake", () => {
  const skill = id => read(join(codexSkills, id, "SKILL.md"));
  assert.match(skill("ddh-design"), /ddh-direct intake before writing dependent design/);
  assert.match(skill("ddh-decision-audit"), /ddh-direct intake before choosing or acting/);
  assert.match(skill("ddh-recover"), /If a saved question is still open, return to the waiting step in ddh-direct/);
});

test("complex UX exports carry the same acceptance criteria", () => {
  const matrix = "ddh-design/references/acceptance.md";
  const expected = read(join(codexSkills, matrix));
  assert.equal(read(join(dshSkills, matrix)), expected);
  for (const criterion of ["State coverage", "Recovery", "System", "Layout", "Accessibility", "Handoff"]) {
    assert.ok(expected.includes("| " + criterion + " |"));
  }
});

test("optional Figma templates ship in both exports without enabling the provider", () => {
  assert.deepEqual(ok("doctor").optionalIntegrations, ["figma-console"]);
  for (const root of [codex, dsh]) {
    const folder = join(root, "integrations/figma-console");
    const integration = json(join(folder, "integration.json"));
    assert.equal(integration.version, "1.46.0");
    assert.equal(integration.enabledByDefault, false);
    assert.match(integration.npmIntegrity, /^sha512-/);
    assert.deepEqual(integration.requiredEnvironment, ["FIGMA_ACCESS_TOKEN"]);
    for (const template of integration.templates) {
      const expected = read(fileURLToPath(new URL("../integrations/figma-console/" + template, import.meta.url)));
      assert.equal(read(join(folder, template)), expected);
    }
    assert.match(read(join(root === codex ? codexSkills : dshSkills, "ddh-design/SKILL.md")),
      /references\/figma-console\.md/);
  }
});

test("pack refuses unknown hosts and existing destinations", () => {
  rejects(/Unknown host/, "pack", "--host", "unknown", "--out", "unknown");
  rejects(/EEXIST/, "pack", "--host", "dsh", "--out", dsh);
  assert.equal(json(join(dsh, "ddh-pack.json")).host, "dsh");
});

test("fresh process resumes verified evidence and rejects a changed artifact", () => {
  const evidence = join(scratch, "evidence.md");
  writeFileSync(evidence, "verified UI state\n");
  const state = {
    objective: "Verify form recovery", workspace: "fixture@baseline",
    scope: ["form"], verification: ["retry checked"], unresolved: ["mobile focus"],
    next: "Check focus at 390 px", artifacts: ["evidence.md"],
  };
  writeFileSync(join(scratch, "input.json"), JSON.stringify(state));
  const save = ["checkpoint", "--workspace", scratch, "--input", "input.json", "--out", "checkpoint.json"];
  assert.equal(ok(...save).artifacts, 1);
  rejects(/EEXIST/, ...save);
  const resume = ["resume", "--workspace", scratch, "--input", "checkpoint.json", "--identity"];
  const result = ok(...resume, "fixture@baseline");
  assert.equal(result.next, state.next);
  assert.deepEqual(result.scope, state.scope);
  assert.deepEqual(result.verification, state.verification);
  assert.deepEqual(result.unresolved, state.unresolved);
  rejects(/identity differs/, ...resume, "fixture@other");
  const envelope = json(join(scratch, "checkpoint.json"));
  envelope.record.next = "Unreviewed operation";
  writeFileSync(join(scratch, "altered.json"), JSON.stringify(envelope));
  rejects(/integrity mismatch/, "resume", "--workspace", scratch, "--input", "altered.json", "--identity", state.workspace);
  writeFileSync(evidence, "modified evidence\n");
  rejects(/Checkpoint evidence changed/, ...resume, "fixture@baseline");
});

test("checkpoint rejects paths outside the workspace", () => {
  const record = {
    objective: "Bound the checkpoint", workspace: "fixture",
    scope: ["fixture"], verification: [], unresolved: [], next: "Inspect evidence",
    artifacts: ["../outside.md"],
  };
  writeFileSync(join(scratch, "escape.json"), JSON.stringify(record));
  rejects(/safe workspace-relative path/, "checkpoint", "--workspace", scratch, "--input", "escape.json", "--out", "escape-out.json");
  rejects(/output must be.*inside workspace/, "checkpoint", "--workspace", scratch, "--input", "escape.json", "--out", "../escape-out.json");
  assert.equal(existsSync(join(scratch, "escape-out.json")), false);
});

test("checkpoints retain pending input or review instead of becoming ready on resume", () => {
  for (const kind of ["user_input", "review"]) {
    const input = {
      objective: "Complete a scoped decision", workspace: "waiting-fixture",
      scope: ["form"], verification: [], unresolved: ["pending decision"],
      next: "Continue design after the decision",
      pending: {kind, request: "Which workflow is intended?", blockedAction: "Write design.md"},
      artifacts: ["evidence.md"],
    };
    const name = "waiting-" + kind;
    writeFileSync(join(scratch, name + ".json"), JSON.stringify(input));
    ok("checkpoint", "--workspace", scratch, "--input", name + ".json", "--out", name + "-saved.json");
    const result = ok("resume", "--workspace", scratch, "--input", name + "-saved.json", "--identity", input.workspace);
    assert.deepEqual(result.pending, input.pending);
    assert.equal(result.readiness, kind === "user_input" ? "waiting_for_user" : "waiting_for_review");
  }
  const invalid = {
    objective: "Wait", workspace: "waiting-fixture", scope: ["form"],
    verification: [], unresolved: [], next: "Continue", artifacts: ["evidence.md"],
    pending: {kind: "user_input", request: "A question without its blocked action"},
  };
  writeFileSync(join(scratch, "invalid-wait.json"), JSON.stringify(invalid));
  rejects(/Invalid pending checkpoint decision/, "checkpoint", "--workspace", scratch,
    "--input", "invalid-wait.json", "--out", "invalid-wait-saved.json");
  assert.equal(existsSync(join(scratch, "invalid-wait-saved.json")), false);
});

test("standard update adopts an earlier DDH install and preserves project guidance", () => {
  const project = join(scratch, "install-project");
  mkdirSync(project);
  const agents = join(project, "AGENTS.md");
  const before = "# Existing project\r\n\r\nKeep original instructions.\r\n";
  writeFileSync(agents, before);
  const name = "ddh-direct/SKILL.md";
  const skills = new Map([["ddh-direct", new Map([["SKILL.md", read(join(codexSkills, name)) + "\nLegacy intake fixture.\n"]])]]);
  installProject(project, { version: "5.0.0" }, skills, "# Design Director Harness 5.0\n\nLegacy intake fixture.\n", false);
  assert.equal(json(join(project, ".agents/ddh-install.json")).version, "5.0.0");
  const userAppend = "\r\nOwner's later guidance.\r\n";
  writeFileSync(agents, read(agents) + userAppend);

  assert.equal(ok("update", "--project", project).status, "updated");
  assert.ok(existsSync(join(project, ".cpt", "runtime.yaml")));
  assert.equal(ok("install", "--project", project).status, "unchanged");
  assert.equal(ok("update", "--project", project).status, "unchanged");
  assert.equal(json(join(project, ".agents/ddh-install.json")).version, version);
  assert.equal(read(join(project, ".agents/skills", name)), read(join(codexSkills, name)));
  assert.ok(read(agents).startsWith(before));
  assert.match(read(agents), /pause all dependent work until the answer arrives/);
  assert.doesNotMatch(read(agents), /Legacy intake fixture/);
  assert.equal(read(agents).split(userAppend).length, 2);
});

test("installer rejects an unmanaged collision and an edited managed file without overwriting either", () => {
  const project = join(scratch, "install-conflict");
  const folder = join(project, ".agents/skills/ddh-direct");
  mkdirSync(folder, { recursive: true });
  const path = join(folder, "SKILL.md");
  writeFileSync(path, "local copy");
  rejects(/No DDH or Product OS installation/, "update", "--project", project);
  rejects(/Skill path already exists/, "install", "--project", project);
  assert.equal(read(path), "local copy");
  assert.equal(existsSync(join(project, "AGENTS.md")), false);
  assert.equal(existsSync(join(project, ".ddh-install.lock")), false);

  const installed = join(scratch, "edited-installation");
  mkdirSync(installed);
  ok("install", "--project", installed);
  const edit = join(installed, ".agents/skills/ddh-verify/SKILL.md");
  writeFileSync(edit, "owner edit");
  rejects(/Managed skill was edited/, "update", "--project", installed);
  assert.equal(read(edit), "owner edit");
});
