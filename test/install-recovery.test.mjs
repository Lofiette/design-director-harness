import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync,
  realpathSync, rmSync, writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join } from "node:path";
import { after, test } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const parent = realpathSync(tmpdir());
const scratch = mkdtempSync(join(parent, "ddh-recovery-test-"));
const installer = pathToFileURL(fileURLToPath(new URL("../tools/project-install.mjs", import.meta.url))).href;
const cli = fileURLToPath(new URL("../tools/ddh.mjs", import.meta.url));
const worker = `
  import fs from "node:fs";
  import {syncBuiltinESMExports} from "node:module";
  import {fileURLToPath} from "node:url";
  const [project, version, fault, selected] = process.argv.slice(1);
  const fds = new Map();
  const originalOpen = fs.openSync;
  const originalSync = fs.fsyncSync;
  const originalRename = fs.renameSync;
  fs.openSync = function(path, ...args) {
    const fd = originalOpen.call(this, path, ...args);
    fds.set(fd, String(path));
    return fd;
  };
  fs.fsyncSync = function(fd) {
    const result = originalSync.call(this, fd);
    const path = fds.get(fd) ?? "";
    if (fault === "journal-staging" && path.includes(".ddh-install.transaction.json.ddh-")) process.exit(96);
    if (fault === "lock" && path.endsWith(".ddh-install.lock")) process.exit(96);
    if (fault === "staging" && path.includes("SKILL.md.ddh-")) process.exit(96);
    return result;
  };
  fs.renameSync = function(source, target) {
    const result = originalRename.call(this, source, target);
    if (String(target).endsWith(".ddh-install.transaction.json")) {
      const state = JSON.parse(fs.readFileSync(target, "utf8")).journal.state;
      if ((fault === "journal" && state === "prepared") || (fault === "commit" && state === "committed")) process.exit(96);
    }
    if (fault === "rename" && String(target).replaceAll("\\\\", "/").endsWith(selected)) process.exit(96);
    return result;
  };
  syncBuiltinESMExports();
  const {installProject} = await import(${JSON.stringify(installer)});
  installProject(project, {version}, new Map([
    ["ddh-demo", new Map([["SKILL.md", "skill " + version + "\\n"]])],
    ["ddh-other", new Map([["SKILL.md", "other " + version + "\\n"]])],
  ]), "# DDH\\n\\nGuidance " + version + "\\n", false);
`;

function fixture(name, baseline = true) {
  const root = join(scratch, name);
  mkdirSync(root);
  writeFileSync(join(root, "AGENTS.md"), "# Owner\r\nKeep owner guidance.\r\n");
  if (baseline) assert.equal(change(root, "old").status, 0);
  return root;
}

function change(root, version, fault = "", selected = "") {
  return spawnSync(process.execPath, ["--input-type=module", "-e", worker, root, version, fault, selected], {encoding:"utf8"});
}

function repair(root) {
  return spawnSync(process.execPath, [cli, "repair-install", "--project", root], {encoding:"utf8"});
}

function files(root) {
  const result = {};
  for (const path of readdirSync(root, {recursive:true,withFileTypes:true})) {
    if (path.isFile()) {
      const absolute = join(path.parentPath, path.name);
      const relative = absolute.slice(root.length + 1).replaceAll("\\", "/");
      if (!relative.startsWith(".ddh-install")) result[relative] = readFileSync(absolute).toString("base64");
    }
  }
  return result;
}

after(() => {
  const target = realpathSync(scratch);
  assert.equal(dirname(target), parent);
  assert.match(basename(target), /^ddh-recovery-test-[a-zA-Z0-9]+$/);
  rmSync(target, {recursive:true});
});

test("prepared updates recover after journal, staging, skill, guidance and receipt interruption", () => {
  const faults = [
    ["journal", ""], ["staging", ""], ["rename", "/ddh-demo/SKILL.md"],
    ["rename", "/AGENTS.md"], ["rename", "/.agents/ddh-install.json"],
  ];
  for (const [index, [fault, selected]] of faults.entries()) {
    const root = fixture("prepared-" + index);
    const before = files(root);
    const killed = change(root, "new", fault, selected);
    assert.equal(killed.status, 96, killed.stderr);
    assert.ok(existsSync(join(root, ".ddh-install.transaction.json")));
    const result = repair(root);
    assert.equal(result.status, 0, result.stderr);
    assert.equal(JSON.parse(result.stdout).status, "rolled-back");
    assert.deepEqual(files(root), before);
    assert.equal(JSON.parse(repair(root).stdout).status, "unchanged");
    assert.equal(change(root, "new").status, 0);
  }
});

test("new installs roll back and committed installs retain their new files", () => {
  const fresh = fixture("fresh", false);
  const before = files(fresh);
  assert.equal(change(fresh, "new", "rename", "/ddh-demo/SKILL.md").status, 96);
  assert.equal(repair(fresh).status, 0);
  assert.deepEqual(files(fresh), before);

  const committed = fixture("committed");
  assert.equal(change(committed, "new", "commit").status, 96);
  writeFileSync(join(committed, "AGENTS.md"), "Legitimate guidance after committed update.");
  const newFiles = files(committed);
  const result = repair(committed);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(JSON.parse(result.stdout).status, "completed-cleanup");
  assert.deepEqual(files(committed), newFiles);
});

test("recovery refuses external edits, corrupted journals and a live install owner", () => {
  const root = fixture("conflict");
  assert.equal(change(root, "new", "rename", "/ddh-demo/SKILL.md").status, 96);
  writeFileSync(join(root, "AGENTS.md"), "Owner changed guidance during interruption.");
  const before = files(root);
  const conflict = repair(root);
  assert.equal(conflict.status, 1);
  assert.match(conflict.stderr, /External edit/);
  assert.deepEqual(files(root), before);
  assert.ok(existsSync(join(root, ".ddh-install.transaction.json")));

  const journal = join(root, ".ddh-install.transaction.json");
  writeFileSync(journal, readFileSync(journal, "utf8").replace("prepared", "committed"));
  assert.match(repair(root).stderr, /integrity mismatch/);
  const active = fixture("active");
  writeFileSync(join(active, ".ddh-install.lock"), JSON.stringify({
    schema:"ddh-install-lock-v1",id:"00000000-0000-4000-8000-000000000000",pid:process.pid,
  }));
  assert.match(repair(active).stderr, /still running/);
});

test("stale pre-journal locks clear and interrupted repair stays closed", () => {
  const root = fixture("stale");
  assert.equal(change(root, "new", "lock").status, 96);
  assert.equal(JSON.parse(repair(root).stdout).status, "cleared-stale-lock");
  const staged = fixture("staged-journal");
  const before = files(staged);
  assert.equal(change(staged, "new", "journal-staging").status, 96);
  assert.equal(JSON.parse(repair(staged).stdout).status, "cleared-stale-lock");
  assert.deepEqual(files(staged), before);
  assert.ok(!readdirSync(staged).some(path => path.includes(".ddh-install.transaction.json.ddh-")));

  const interrupted = fixture("repair-killed");
  assert.equal(change(interrupted, "new", "rename", "/.agents/ddh-install.json").status, 96);
  const repairWorker = `
    import fs from "node:fs";
    import {syncBuiltinESMExports} from "node:module";
    const original = fs.renameSync;
    fs.renameSync = function(source,target) { original(source,target); process.exit(97); };
    syncBuiltinESMExports();
    process.argv = [process.execPath, ${JSON.stringify(cli)}, "repair-install", "--project", process.argv[1]];
    await import(${JSON.stringify(pathToFileURL(cli).href)});
  `;
  const killed = spawnSync(process.execPath, ["--input-type=module","-e",repairWorker,interrupted], {encoding:"utf8"});
  assert.equal(killed.status, 97, killed.stderr);
  assert.ok(existsSync(join(interrupted, ".ddh-install.recovery.lock")));
  assert.ok(existsSync(join(interrupted, ".ddh-install.transaction.json")));
  assert.equal(repair(interrupted).status, 1);
  assert.match(change(interrupted, "new").stderr, /manual reconciliation/);
});

test("held recovery refuses another repair and an installer before changing any targets", async () => {
  const root = fixture("parallel");
  const original = files(root);
  assert.equal(change(root, "new", "rename", "/AGENTS.md").status, 96);
  const ready = join(scratch, "recovery-ready");
  const release = join(scratch, "recovery-release");
  const barrierWorker = `
    import fs from "node:fs";
    import {syncBuiltinESMExports} from "node:module";
    const [project,ready,release] = process.argv.slice(1);
    const fds = new Map();
    const open = fs.openSync, sync = fs.fsyncSync;
    fs.openSync = function(path,...args) { const fd=open(path,...args); fds.set(fd,String(path)); return fd; };
    fs.fsyncSync = function(fd) {
      sync(fd);
      if (fds.get(fd)?.endsWith(".ddh-install.recovery.lock")) {
        fs.writeFileSync(ready,"ready");
        const until = Date.now() + 10000;
        while (!fs.existsSync(release)) {
          if (Date.now() > until) process.exit(98);
          Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,10);
        }
      }
    };
    syncBuiltinESMExports();
    process.argv=[process.execPath,${JSON.stringify(cli)},"repair-install","--project",project];
    await import(${JSON.stringify(pathToFileURL(cli).href)});
  `;
  const child = spawn(process.execPath, ["--input-type=module","-e",barrierWorker,root,ready,release], {stdio:"ignore"});
  const closed = new Promise(resolve => child.on("close", code => resolve(code)));
  try {
    const until = Date.now() + 5000;
    while (!existsSync(ready)) {
      assert.ok(Date.now() < until, "Recovery barrier did not become ready");
      await new Promise(resolve => setTimeout(resolve, 10));
    }
    const held = files(root);
    assert.equal(repair(root).status, 1);
    const competing = change(root, "new");
    assert.equal(competing.status, 1);
    assert.match(competing.stderr, /Recovery marker/);
    assert.deepEqual(files(root), held);
  } finally {
    writeFileSync(release, "release");
  }
  assert.equal(await closed, 0);
  assert.deepEqual(files(root), original);
  assert.equal(repair(root).status, 0);
  assert.equal(change(root, "new").status, 0);
});

test("journal root, duplicate paths and unsafe paths are rejected before restoration", () => {
  const root = fixture("journal-validation");
  assert.equal(change(root, "new", "rename", "/AGENTS.md").status, 96);
  const path = join(root, ".ddh-install.transaction.json");
  const original = readFileSync(path);
  for (const mutate of [
    journal => { journal.root = join(scratch, "other"); },
    journal => { journal.entries.push(journal.entries[0]); },
    journal => { journal.entries[0].path = "../unmanaged.txt"; },
  ]) {
    const envelope = JSON.parse(original);
    mutate(envelope.journal);
    envelope.checksum = createHash("sha256").update(JSON.stringify(envelope.journal)).digest("hex");
    writeFileSync(path, JSON.stringify(envelope));
    const before = files(root);
    assert.equal(repair(root).status, 1);
    assert.deepEqual(files(root), before);
  }
  writeFileSync(path, original);
  assert.equal(repair(root).status, 0);
});
