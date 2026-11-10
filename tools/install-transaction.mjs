import { createHash, randomUUID } from "node:crypto";
import {
  closeSync, fsyncSync, lstatSync, mkdirSync, openSync, readFileSync,
  renameSync, unlinkSync, writeFileSync,
} from "node:fs";
import { dirname, join } from "node:path";

const lockPath = ".ddh-install.lock";
const journalPath = ".ddh-install.transaction.json";
const recoveryPath = ".ddh-install.recovery.lock";
const uuid = /^[a-f0-9-]{36}$/;
export const runtimeRequirementsPath = ".agents/ddh-runtime-requirements.txt";
export const managedSkillPath = /^\.agents\/skills\/(?:ddh-[a-z]+(?:-[a-z]+)*\/(?:SKILL\.md|references\/[a-z0-9-]+\.md)|cpt-[a-z]+(?:-[a-z]+)*\/(?:SKILL\.md|agents\/openai\.yaml|references\/(?:adapters\/)?[A-Za-z0-9_-]+\.(?:md|yaml|json)|scripts\/[a-z0-9_-]+\.mjs))$/;
export const cptSeedPaths = new Set([
  ".cpt/runtime.yaml", ".cpt/current.yaml", ".cpt/task-index.yaml", ".cpt/runtime-summary.md",
  ".cpt/enforcement.yaml", ".cpt/bin/cpt_runtime.py", ".cpt/bin/cpt_orchestration.py",
  ".cpt/schema-bundle.json", ".cpt/worker-archetypes.json", ".cpt/OPERATIONS.md", ".cpt/install.json",
]);
const allowedPath = path => path === "AGENTS.md" || path === ".gitignore" ||
  path === ".agents/ddh-install.json" || path === runtimeRequirementsPath ||
  managedSkillPath.test(path) || cptSeedPaths.has(path);
const allowed = entry => allowedPath(entry.path) &&
  (!cptSeedPaths.has(entry.path) || entry.before === null && entry.after !== null);

export function check(condition, message) {
  if (!condition) throw new Error(message);
}

export function inspectPath(root, path) {
  let file = root;
  const parts = path.split("/");
  for (const part of parts.slice(0, -1)) {
    file = join(file, part);
    const info = lstatSync(file, { throwIfNoEntry: false });
    check(!info || info.isDirectory(), "Expected a real directory: " + file);
  }
  file = join(file, parts.at(-1));
  const info = lstatSync(file, { throwIfNoEntry: false });
  check(!info || info.isFile(), "Expected a regular file: " + file);
  return info ? readFileSync(file) : null;
}

export function same(left, right) {
  return left === null || right === null ? left === right : left.equals(right);
}

function writeNew(path, contents) {
  const descriptor = openSync(path, "wx");
  try {
    writeFileSync(descriptor, contents);
    fsyncSync(descriptor);
  } finally {
    closeSync(descriptor);
  }
}

function replace(root, path, contents, id) {
  check(allowedPath(path) || path === journalPath, "Invalid transaction path: " + path);
  inspectPath(root, path);
  const file = join(root, path);
  if (contents === null) {
    unlinkSync(file);
    return;
  }
  mkdirSync(dirname(file), { recursive: true });
  const temp = path + ".ddh-" + id + ".tmp";
  check(inspectPath(root, temp) === null, "Interrupted staging file needs recovery: " + temp);
  try {
    writeNew(join(root, temp), contents);
    renameSync(join(root, temp), file);
  } finally {
    if (inspectPath(root, temp) !== null) unlinkSync(join(root, temp));
  }
}

function removeExact(root, path, expected) {
  check(same(inspectPath(root, path), expected), "File changed during cleanup: " + path);
  if (expected !== null) unlinkSync(join(root, path));
}

function readOwner(bytes) {
  const owner = JSON.parse(bytes.toString("utf8"));
  check(owner.schema === "ddh-install-lock-v1" && uuid.test(owner.id) &&
    Number.isSafeInteger(owner.pid) && owner.pid > 0, "Unrecognized install lock requires manual inspection");
  return owner;
}

function isAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    if (error.code === "ESRCH") return false;
    return true;
  }
}

function serialize(journal) {
  return Buffer.from(JSON.stringify(journal, null, 2) + "\n");
}

function serializeJournal(journal) {
  const checksum = createHash("sha256").update(JSON.stringify(journal)).digest("hex");
  return serialize({journal, checksum});
}

function encode(value) {
  return value === null ? null : value.toString("base64");
}

function decode(value) {
  if (value === null) return null;
  check(typeof value === "string" && value.length <= 6 * 1024 * 1024, "Invalid journal file content");
  const bytes = Buffer.from(value, "base64");
  check(bytes.toString("base64") === value, "Noncanonical journal content");
  return bytes;
}

function readJournal(bytes, root) {
  const envelope = JSON.parse(bytes.toString("utf8"));
  const journal = envelope.journal;
  check(envelope.checksum === createHash("sha256").update(JSON.stringify(journal)).digest("hex"),
    "Install journal integrity mismatch");
  check(journal.schema === "ddh-install-transaction-v1" && uuid.test(journal.id) &&
    journal.root === root &&
    ["prepared", "committed"].includes(journal.state) && Array.isArray(journal.entries) &&
    journal.entries.length > 0 && journal.entries.length <= 1000, "Invalid install journal");
  const seen = new Set();
  journal.entries = journal.entries.map(entry => {
    check(typeof entry.path === "string" && allowedPath(entry.path) && !seen.has(entry.path),
      "Invalid or duplicate journal path");
    const decoded = { path: entry.path, before: decode(entry.before), after: decode(entry.after) };
    check(allowed(decoded), "Invalid initial CPT journal entry");
    seen.add(entry.path);
    return decoded;
  });
  return journal;
}

function cleanStaging(root, journal) {
  for (const path of [...journal.entries.map(entry => entry.path), journalPath]) {
    const temp = path + ".ddh-" + journal.id + ".tmp";
    const data = inspectPath(root, temp);
    if (data !== null) removeExact(root, temp, data);
  }
}

function rollback(root, journal) {
  // Check every target before restoring the first one.
  for (const entry of journal.entries) {
    const current = inspectPath(root, entry.path);
    check(same(current, entry.before) || same(current, entry.after),
      "External edit prevents recovery: " + entry.path);
  }
  cleanStaging(root, journal);
  for (const entry of [...journal.entries].reverse()) {
    const current = inspectPath(root, entry.path);
    if (same(current, entry.before)) continue;
    check(same(current, entry.after), "File changed during recovery: " + entry.path);
    replace(root, entry.path, entry.before, journal.id);
  }
}

export function installTransaction(root, build) {
  check(inspectPath(root, recoveryPath) === null, "Recovery marker requires manual reconciliation");
  check(inspectPath(root, journalPath) === null, "Interrupted update. Run repair-install first");
  const owner = { schema: "ddh-install-lock-v1", id: randomUUID(), pid: process.pid };
  const ownerBytes = serialize(owner);
  writeNew(join(root, lockPath), ownerBytes);
  let journal;
  try {
    check(inspectPath(root, recoveryPath) === null, "Recovery is in progress");
    check(inspectPath(root, journalPath) === null, "Interrupted update. Run repair-install first");
    const { changes, result } = build();
    const entries = changes.filter(entry => !same(entry.before, entry.after));
    if (entries.length === 0) return result;
    check(entries.every(allowed), "Invalid planned install path");
    journal = { schema: "ddh-install-transaction-v1", id: owner.id, root, state: "prepared",
      entries: entries.map(entry => ({path: entry.path, before: encode(entry.before), after: encode(entry.after)})) };
    replace(root, journalPath, serializeJournal(journal), owner.id);
    for (const entry of entries) {
      check(same(inspectPath(root, entry.path), entry.before), "File changed during installation: " + entry.path);
      replace(root, entry.path, entry.after, owner.id);
    }
    const committed = {...journal, state: "committed"};
    replace(root, journalPath, serializeJournal(committed), owner.id);
    removeExact(root, journalPath, serializeJournal(committed));
    return result;
  } catch (error) {
    if (journal) {
      try {
        const persistedBytes = inspectPath(root, journalPath);
        const persisted = readJournal(persistedBytes, root);
        if (persisted.state === "prepared") rollback(root, persisted);
        else cleanStaging(root, persisted);
        removeExact(root, journalPath, persistedBytes);
      } catch (recoveryError) {
        throw new AggregateError([error, recoveryError], "Update interrupted. Preserve the journal and run repair-install");
      }
    }
    throw error;
  } finally {
    if (inspectPath(root, journalPath) === null) removeExact(root, lockPath, ownerBytes);
  }
}

export function repairInstallation(root) {
  const marker = serialize({schema: "ddh-recovery-lock-v1", pid: process.pid, id: randomUUID()});
  writeNew(join(root, recoveryPath), marker);
  let mutated = false;
  let complete = false;
  try {
    const lockBytes = inspectPath(root, lockPath);
    const journalBytes = inspectPath(root, journalPath);
    if (lockBytes !== null) check(!isAlive(readOwner(lockBytes).pid), "Install owner is still running");
    const journal = journalBytes === null ? null : readJournal(journalBytes, root);
    if (journal && lockBytes) check(journal.id === readOwner(lockBytes).id, "Journal and lock identity differ");
    check(!journal || lockBytes !== null, "Missing install lock requires manual inspection");
    if (!journal) {
      if (lockBytes !== null) {
        const temp = journalPath + ".ddh-" + readOwner(lockBytes).id + ".tmp";
        const staged = inspectPath(root, temp);
        if (staged !== null) removeExact(root, temp, staged);
      }
      removeExact(root, lockPath, lockBytes);
      complete = true;
      return {status: lockBytes === null ? "unchanged" : "cleared-stale-lock"};
    }
    if (journal.state === "prepared") {
      for (const entry of journal.entries) {
        const current = inspectPath(root, entry.path);
        check(same(current, entry.before) || same(current, entry.after), "External edit prevents recovery: " + entry.path);
      }
      mutated = true;
      rollback(root, journal);
    } else {
      // Committed installs can already have legitimate user edits.
      mutated = true;
      cleanStaging(root, journal);
    }
    removeExact(root, journalPath, journalBytes);
    removeExact(root, lockPath, lockBytes);
    complete = true;
    return {status: journal.state === "prepared" ? "rolled-back" : "completed-cleanup"};
  } finally {
    if (complete || !mutated) removeExact(root, recoveryPath, marker);
  }
}
