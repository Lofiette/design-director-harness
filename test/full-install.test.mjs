import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, unlinkSync, writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join } from "node:path";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";

const parent = realpathSync(tmpdir());
const scratch = mkdtempSync(join(parent, "ddh-full-test-"));
const source = fileURLToPath(new URL("../product-os/", import.meta.url));
const cli = fileURLToPath(new URL("../tools/ddh.mjs", import.meta.url));
const dist = join(source, "tools", "cpt_dist.py");
const python = process.env.DDH_TEST_PYTHON ?? "python";
const originalAgents = "# Project guidance\r\nKeep these rules.\r\n";
const originalIgnore = "private.txt\r\n";
const projectRequirements = ".agents/ddh-runtime-requirements.txt";
const run = (command, args, options = {}) => spawnSync(command, args, { encoding: "utf8", ...options });

function success(result) {
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return result.stdout.trim();
}

function install(command, root, ...options) {
  return JSON.parse(success(run(process.execPath, [cli, command, "--project", root, "--python", python, ...options])));
}

function runtime(root, ...args) {
  return success(run(python, ["-B", join(root, ".cpt", "bin", "cpt_runtime.py"), "--root", root, ...args]));
}

function fixture(name) {
  const root = join(scratch, name);
  mkdirSync(root);
  writeFileSync(join(root, "AGENTS.md"), originalAgents);
  writeFileSync(join(root, ".gitignore"), originalIgnore);
  return root;
}

function files(root) {
  if (!existsSync(root)) return {};
  return Object.fromEntries(readdirSync(root, { recursive: true, withFileTypes: true })
    .filter(entry => entry.isFile())
    .map(entry => {
      const path = join(entry.parentPath, entry.name);
      return [path.slice(root.length + 1), readFileSync(path).toString("base64")];
    }));
}

after(() => {
  const target = realpathSync(scratch);
  assert.equal(dirname(target), parent);
  assert.match(basename(target), /^ddh-full-test-[a-zA-Z0-9]+$/);
  rmSync(target, { recursive: true });
});

test("the standard commands install both layers and keep an active CPT checkpoint through update", () => {
  const root = fixture("fresh");
  assert.equal(install("install", root).productOS, "installed");
  assert.match(runtime(root, "validate"), /RUNTIME VALIDATION PASSED/);
  const agents = readFileSync(join(root, "AGENTS.md"), "utf8");
  assert.ok(agents.startsWith(originalAgents));
  assert.equal(agents.split("<!-- CPT-OS KERNEL BEGIN -->").length, 2);
  assert.equal(agents.split("<!-- DDH MANAGED BEGIN -->").length, 2);
  assert.equal(readFileSync(join(root, ".gitignore"), "utf8"), originalIgnore + "\r\n/.cpt/\r\n");
  assert.ok(existsSync(join(root, ".cpt/OPERATIONS.md")));
  assert.deepEqual(readFileSync(join(root, projectRequirements)), readFileSync(join(source, "requirements.txt")));
  assert.ok(agents.includes(`--with-requirements ${projectRequirements}`));
  runtime(root, "create-task", "--title", "Fixture", "--objective", "Preserve state", "--activate");
  const checkpoint = runtime(root, "checkpoint", "--source", "phase_handoff", "--reason", "Fixture");
  const cpt = join(root, ".cpt");
  const before = files(cpt);
  const update = install("update", root);
  assert.equal(update.productOS, "preserved");
  assert.equal(update.status, "unchanged");
  assert.deepEqual(files(cpt), before);
  assert.match(runtime(root, "recover", "--checkpoint", checkpoint, "--verify-only"), /CHECKPOINT MATCH/);
});

test("runtime requirements collisions and edits leave project files intact", () => {
  const root = fixture("requirements-protection");
  const requirements = join(root, projectRequirements);
  mkdirSync(dirname(requirements));
  writeFileSync(requirements, "User requirements");
  const beforeInstall = files(root);
  const rejected = run(process.execPath, [cli, "install", "--project", root, "--python", python]);
  assert.equal(rejected.status, 1, rejected.stderr);
  assert.match(rejected.stderr, /Runtime requirements path already exists/);
  assert.deepEqual(files(root), beforeInstall);

  const installed = fixture("requirements-managed");
  install("install", installed);
  writeFileSync(join(installed, projectRequirements), "Modified requirements");
  const before = files(installed);
  const result = run(process.execPath, [cli, "update", "--project", installed, "--python", python]);
  assert.equal(result.status, 1, result.stderr);
  assert.match(result.stderr, /Managed runtime requirements was edited/);
  assert.deepEqual(files(installed), before);
});

test("a partially initialized CPT tree fails closed", () => {
  const root = fixture("partial");
  mkdirSync(join(root, ".cpt"));
  writeFileSync(join(root, ".cpt", "notes.md"), "User notes");
  const before = files(root);
  const result = run(process.execPath, [cli, "install", "--project", root, "--python", python]);
  assert.equal(result.status, 1, result.stderr);
  assert.match(result.stderr, /Existing files under .cpt require explicit adoption/);
  assert.deepEqual(files(root), before);
});

test("the full install journal rolls back a stopped CPT seed and permits a retry", () => {
  const root = fixture("interrupted");
  const before = files(root);
  const worker = [
    'import fs from "node:fs";',
    'import { syncBuiltinESMExports } from "node:module";',
    'const rename = fs.renameSync;',
    'fs.renameSync = (source, target) => {',
    '  rename(source, target);',
    '  if (String(target).replaceAll("\\\\", "/").endsWith("/.cpt/bin/cpt_runtime.py")) process.exit(96);',
    '};',
    'syncBuiltinESMExports();',
    'const cli = process.argv[1];',
    'process.argv = [process.execPath, cli, "install", "--project", process.argv[2], "--python", process.argv[3]];',
    'await import("node:url").then(({ pathToFileURL }) => import(pathToFileURL(cli)));',
  ].join("\n");
  const stopped = run(process.execPath, ["--input-type=module", "-e", worker, cli, root, python]);
  assert.equal(stopped.status, 96, stopped.stderr);
  assert.ok(existsSync(join(root, ".ddh-install.transaction.json")));
  const repaired = success(run(process.execPath, [cli, "repair-install", "--project", root]));
  assert.equal(JSON.parse(repaired).status, "rolled-back");
  assert.deepEqual(files(root), before);
  assert.equal(install("install", root).productOS, "installed");
});

test("CPT personal worker receipts are isolated by Codex profile", () => {
  const root = fixture("worker-status");
  install("install", root);
  const first = join(root, "codex-first");
  const second = join(root, "codex-second");
  const profile = path => ({ env: { ...process.env, CODEX_HOME: path } });
  success(run(python, ["-B", dist, "workers-install", "--scope", "personal"], profile(first)));
  assert.ok(existsSync(join(first, ".cpt-os", "worker-packs", "cpt-workers.json")));
  assert.match(success(run(python, ["-B", dist, "doctor", "--project", root], profile(second))), /workers: PASS \(none\)/);
  const current = JSON.parse(success(run(python, ["-B", dist, "status", "--project", root, "--json"], profile(first))));
  assert.equal(current.workers.installed, true);
  assert.equal(current.workers.valid, true);
});

test("full installation selects portable domain packs and retains the selection on update", () => {
  const root = fixture("design-pack");
  const result = install("install", root, "--packs", "cpt-design-ui,cpt-engineering");
  assert.equal(result.skills, 33);
  assert.deepEqual(result.packs, ["cpt-design-ui", "cpt-engineering"]);
  assert.ok(existsSync(join(root, ".agents/skills/cpt-screen-module-design/references/DESIGN_STRESS_REVIEW.md")));
  const cpt = files(join(root, ".cpt"));
  assert.equal(install("update", root).status, "unchanged");
  assert.equal(install("install-full", root).status, "unchanged");
  assert.equal(install("update-full", root).status, "unchanged");
  assert.equal(install("update", root, "--packs", "").skills, 5);
  assert.ok(!existsSync(join(root, ".agents/skills/cpt-screen-module-design/SKILL.md")));
  assert.deepEqual(files(join(root, ".cpt")), cpt);
});

test("standard update adopts a CPT 4.1 project without changing its checkpoint", () => {
  const root = fixture("legacy-cpt");
  success(run(python, ["-B", dist, "install", "--project", root, "--mode", "local", "--plugin-scope", "none"]));
  const guide = join(root, ".cpt", "OPERATIONS.md");
  const bundledGuide = readFileSync(guide);
  unlinkSync(guide); // Released Product OS 4.1 omitted this file.
  const task = runtime(root, "create-task", "--title", "Existing work", "--objective", "Keep state", "--activate");
  runtime(root, "lease-create", "--task", task, "--read", "fixture", "--write", "notes.md", "--verify", "fixture");
  const checkpoint = runtime(root, "checkpoint", "--source", "phase_handoff", "--reason", "Before adopting DDH");
  const cpt = join(root, ".cpt");
  const before = files(cpt);
  const agents = readFileSync(join(root, "AGENTS.md"), "utf8");
  const result = install("update", root, "--packs", "cpt-design-ui");
  assert.equal(result.productOS, "preserved");
  assert.equal(result.status, "updated");
  assert.equal(result.skills, 21);
  assert.ok(readFileSync(join(root, "AGENTS.md"), "utf8").startsWith(agents));
  assert.deepEqual(files(cpt), { ...before, "OPERATIONS.md": bundledGuide.toString("base64") });
  assert.match(runtime(root, "recover", "--checkpoint", checkpoint, "--verify-only"), /CHECKPOINT MATCH/);
  writeFileSync(guide, "Project CPT operations");
  assert.equal(install("update", root).status, "unchanged");
  assert.equal(readFileSync(guide, "utf8"), "Project CPT operations");
});
