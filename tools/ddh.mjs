import { createHash } from "node:crypto";
import {
  closeSync, lstatSync, mkdirSync, openSync, readFileSync, readdirSync, realpathSync,
  rmdirSync, unlinkSync, writeFileSync,
} from "node:fs";
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { installProject } from "./project-install.mjs";
import { repairInstallation } from "./install-transaction.mjs";

const home = fileURLToPath(new URL("../", import.meta.url));
const json = value => JSON.stringify(value, null, 2) + "\n";
const readJson = file => JSON.parse(readFileSync(file, "utf8"));
const hash = data => createHash("sha256").update(data).digest("hex");
const chars = value => [...value].length;
const skillId = /^ddh-[a-z]+(?:-[a-z]+)*$/;
const sha256 = /^[0-9a-f]{64}$/;

function requireThat(condition, message) {
  if (!condition) throw new Error(message);
}

function inside(root, target) {
  const name = relative(root, target);
  return name !== "" && name !== ".." && !name.startsWith(".." + sep) && !isAbsolute(name);
}

function fileBelow(root, path) {
  requireThat(typeof path === "string" && path.split("/").every(part =>
    part && part !== "." && part !== ".." && !/[\\:\x00-\x1f]/.test(part) && !/[ .]$/.test(part)
  ), "Expected a safe workspace-relative path: " + path);
  const file = resolve(root, path);
  requireThat(inside(root, file), "Path escapes workspace: " + path);
  requireThat(inside(root, realpathSync(file)) && lstatSync(file).isFile(), "Expected a regular file in workspace: " + path);
  return file;
}

function writeNew(file, contents) {
  const descriptor = openSync(file, "wx");
  try {
    try {
      writeFileSync(descriptor, contents);
    } finally {
      closeSync(descriptor);
    }
  } catch (error) {
    unlinkSync(file);
    throw error;
  }
}

function inspect() {
  const manifest = readJson(join(home, "manifest.json"));
  const sources = readJson(join(home, "sources.json"));
  const skillsRoot = join(home, "skills");
  const skills = new Map();
  requireThat(
    Array.isArray(manifest.defaultSkills) && manifest.defaultSkills.length > 0 &&
    new Set(manifest.defaultSkills).size === manifest.defaultSkills.length,
    "Default skill IDs must be unique",
  );
  requireThat(
    readdirSync(skillsRoot).sort().join("\n") === [...manifest.defaultSkills].sort().join("\n"),
    "Skill catalog differs from manifest",
  );
  for (const id of manifest.defaultSkills) {
    requireThat(skillId.test(id), "Invalid skill ID: " + id);
    const folder = join(skillsRoot, id);
    requireThat(lstatSync(folder).isDirectory(), "Expected skill directory: " + id);
    const files = new Map();
    const main = readFileSync(fileBelow(folder, "SKILL.md"), "utf8");
    const header = /^---\r?\nname: ([^\r\n]+)\r?\ndescription: ([^\r\n]+)\r?\n---\r?\n([\s\S]+)$/.exec(main);
    requireThat(header && header[1] === id, "Invalid skill frontmatter: " + id);
    const { description, bodyWithWrapper, wrapperReserve, referenceWithWrapper, referenceReserve } = manifest.dshLimits;
    requireThat(chars(header[2]) <= description, "Description exceeds DSH limit: " + id);
    requireThat(chars(header[3]) + wrapperReserve <= bodyWithWrapper, "Body exceeds DSH budget: " + id);
    files.set("SKILL.md", main);
    const children = readdirSync(folder).sort();
    requireThat(children.every(entry => ["SKILL.md", "references"].includes(entry)), "Unexpected skill file: " + id);
    if (children.includes("references")) {
      requireThat(lstatSync(join(folder, "references")).isDirectory(), "Expected references directory: " + id);
      for (const name of readdirSync(join(folder, "references")).sort()) {
        requireThat(/^[a-z0-9-]+\.md$/.test(name), "Unexpected reference: " + name);
        const path = "references/" + name;
        const body = readFileSync(fileBelow(folder, path), "utf8");
        requireThat(chars(body) + referenceReserve <= referenceWithWrapper, "Reference exceeds DSH budget: " + path);
        requireThat(main.includes("](" + path + ")"), "Unlinked reference: " + path);
        files.set(path, body);
      }
    }
    for (const [, path] of main.matchAll(/\]\((references\/[^)]+)\)/g)) {
      requireThat(files.has(path), "Missing reference in " + id + ": " + path);
    }
    skills.set(id, files);
  }
  const ids = new Set();
  for (const source of sources.entries) {
    requireThat(source.id && !ids.has(source.id), "Duplicate or empty source ID: " + source.id);
    requireThat(source.url.startsWith("https://github.com/") && source.license && source.use && source.reason,
      "Incomplete source record: " + source.id);
    requireThat(!source.pin || /^[0-9a-f]{40}$/.test(source.pin), "Invalid commit pin: " + source.id);
    requireThat(!source.observedBlob || /^[0-9a-f]{40}$/.test(source.observedBlob), "Invalid blob ID: " + source.id);
    ids.add(source.id);
  }
  const integrations = new Map();
  for (const id of manifest.optionalIntegrations ?? []) {
    requireThat(/^[a-z]+(?:-[a-z]+)*$/.test(id) && !integrations.has(id), "Invalid integration ID");
    const root = join(home, "integrations", id);
    const definition = readJson(fileBelow(root, "integration.json"));
    requireThat(definition.id === id && definition.enabledByDefault === false &&
      Array.isArray(definition.templates), "Invalid optional integration: " + id);
    const files = new Map();
    for (const name of ["integration.json", "README.md", ...definition.templates]) {
      files.set(name, readFileSync(fileBelow(root, name), "utf8"));
    }
    integrations.set(id, files);
  }
  return { manifest, skills, sources, integrations };
}

function pack(host, output) {
  const { manifest, skills, integrations } = inspect();
  requireThat(manifest.hosts.includes(host), "Unknown host: " + host);
  const files = new Map();
  let skillsPath = ".dsh/skills";
  if (host === "codex") {
    const plugin = "plugins/" + manifest.name;
    skillsPath = plugin + "/skills";
    files.set(plugin + "/.codex-plugin/plugin.json", json({
      name: manifest.name,
      version: manifest.version,
      description: manifest.description,
      skills: "./skills/",
      interface: { displayName: manifest.displayName, category: "Productivity" },
    }));
    files.set(".agents/plugins/marketplace.json", json({
      name: manifest.name,
      interface: { displayName: manifest.displayName },
      plugins: [{
        name: manifest.name,
        source: { source: "local", path: "./" + plugin },
        policy: { installation: "AVAILABLE", authentication: "ON_INSTALL" },
        category: "Productivity",
      }],
    }));
  }
  files.set("AGENTS.md", readFileSync(join(home, "adapters/AGENTS.ddh.md"), "utf8"));
  files.set("README.md", readFileSync(join(home, "adapters", host, "README.md"), "utf8"));
  for (const [id, bundle] of integrations) {
    for (const [path, contents] of bundle) files.set("integrations/" + id + "/" + path, contents);
  }
  for (const [id, bundle] of skills) {
    for (const [path, contents] of bundle) files.set(skillsPath + "/" + id + "/" + path, contents);
  }
  const receipt = {
    schema: "ddh-pack-v1", host, version: manifest.version, skills: [...skills.keys()],
    files: Object.fromEntries([...files].map(([name, contents]) => [name, hash(contents)])),
  };
  files.set("ddh-pack.json", json(receipt));

  const absolute = resolve(output);
  const destination = join(realpathSync(dirname(absolute)), basename(absolute));
  const sourceHome = realpathSync(home);
  requireThat(destination !== sourceHome && !inside(sourceHome, destination),
    "Place the package outside the DDH source directory");
  const dirs = [];
  const written = [];
  mkdirSync(destination);
  dirs.push(destination);
  try {
    for (const [path, contents] of files) {
      const parts = path.split("/");
      let current = destination;
      for (const part of parts.slice(0, -1)) {
        current = join(current, part);
        if (!dirs.includes(current)) {
          mkdirSync(current);
          dirs.push(current);
        }
      }
      const file = join(current, parts.at(-1));
      writeNew(file, contents);
      written.push(file);
    }
    for (const [path, expected] of Object.entries(receipt.files)) {
      requireThat(hash(readFileSync(join(destination, path))) === expected, "Package hash mismatch: " + path);
    }
  } catch (error) {
    for (const file of written.reverse()) unlinkSync(file);
    for (const dir of dirs.reverse()) rmdirSync(dir);
    throw error;
  }
  return { destination, host, skills: receipt.skills.length, files: files.size };
}

function nonempty(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function validateRecord(record) {
  requireThat(record && !Array.isArray(record) && typeof record === "object", "Expected a checkpoint object");
  for (const field of ["objective", "workspace", "next"]) {
    requireThat(nonempty(record[field]), "Checkpoint requires " + field);
  }
  for (const field of ["scope", "verification", "unresolved"]) {
    requireThat(Array.isArray(record[field]) && record[field].every(nonempty),
      "Checkpoint requires an array of strings for " + field);
  }
  requireThat(record.scope.length > 0, "Checkpoint scope is empty");
  if (record.pending !== undefined) {
    const pending = record.pending;
    requireThat(pending && !Array.isArray(pending) &&
      ["user_input", "review"].includes(pending.kind) &&
      nonempty(pending.request) && nonempty(pending.blockedAction), "Invalid pending checkpoint decision");
  }
}

function checkpoint(workspace, input, output) {
  const root = realpathSync(workspace);
  const absolute = resolve(output);
  const target = join(realpathSync(dirname(absolute)), basename(absolute));
  requireThat(inside(root, target) && !/[: .]$/.test(basename(target)) &&
    !basename(target).includes(":"), "Checkpoint output must be a new file inside workspace");
  const inputRecord = readJson(fileBelow(root, input));
  validateRecord(inputRecord);
  requireThat(
    Array.isArray(inputRecord.artifacts) && inputRecord.artifacts.length > 0 &&
    new Set(inputRecord.artifacts).size === inputRecord.artifacts.length,
    "Checkpoint artifacts must be a nonempty list of unique file paths",
  );
  const { objective, next, workspace: workspaceId, scope, verification, unresolved } = inputRecord;
  const record = {
    objective, workspace: workspaceId, scope, verification, unresolved, next,
    ...(inputRecord.pending === undefined ? {} : {pending: inputRecord.pending}),
    artifacts: inputRecord.artifacts.map(path => ({ path, sha256: hash(readFileSync(fileBelow(root, path))) })),
  };
  const envelope = { schema: "ddh-checkpoint-v1", sha256: hash(json(record)), record };
  writeNew(target, json(envelope));
  return { checkpoint: target, artifacts: record.artifacts.length };
}

function resume(workspace, input, expectedWorkspace) {
  const root = realpathSync(workspace);
  const envelope = readJson(fileBelow(root, input));
  requireThat(envelope?.schema === "ddh-checkpoint-v1" && envelope.sha256 === hash(json(envelope.record)),
    "Checkpoint integrity mismatch");
  const record = envelope.record;
  validateRecord(record);
  requireThat(record.workspace === expectedWorkspace, "Checkpoint workspace identity differs");
  requireThat(Array.isArray(record.artifacts) && record.artifacts.length > 0, "Missing checkpoint artifacts");
  const seen = new Set();
  for (const item of record.artifacts) {
    requireThat(item && sha256.test(item.sha256) && !seen.has(item.path), "Invalid checkpoint artifact");
    requireThat(hash(readFileSync(fileBelow(root, item.path))) === item.sha256,
      "Checkpoint evidence changed: " + item.path);
    seen.add(item.path);
  }
  return record.pending
    ? {...record, readiness: record.pending.kind === "user_input" ? "waiting_for_user" : "waiting_for_review"}
    : record;
}

function options(args, keys) {
  const { values } = parseArgs({
    args, options: Object.fromEntries(keys.map(key => [key, { type: "string" }])),
  });
  for (const key of keys) requireThat(nonempty(values[key]), "Missing --" + key);
  return values;
}

try {
  const [command, ...args] = process.argv.slice(2);
  let result;
  switch (command) {
    case "doctor": {
      options(args, []);
      const { manifest, skills, sources, integrations } = inspect();
      result = { version: manifest.version, hosts: manifest.hosts, skills: [...skills.keys()],
        sources: sources.entries.length, optionalIntegrations: [...integrations.keys()] };
      break;
    }
    case "pack": {
      const { host, out } = options(args, ["host", "out"]);
      result = pack(host, out);
      break;
    }
    case "install":
    case "update": {
      const { project } = options(args, ["project"]);
      const { manifest, skills } = inspect();
      const bootstrap = readFileSync(join(home, "adapters/AGENTS.ddh.md"), "utf8");
      result = installProject(project, manifest, skills, bootstrap, command === "update");
      break;
    }
    case "checkpoint": {
      const { workspace, input, out } = options(args, ["workspace", "input", "out"]);
      result = checkpoint(workspace, input, out);
      break;
    }
    case "repair-install": {
      const { project } = options(args, ["project"]);
      result = repairInstallation(realpathSync(project));
      break;
    }
    case "resume": {
      const { workspace, input, identity } = options(args, ["workspace", "input", "identity"]);
      result = resume(workspace, input, identity);
      break;
    }
    default:
      throw new Error("Usage: ddh.mjs doctor | pack | install | update | repair-install | checkpoint | resume");
  }
  process.stdout.write(json(result));
} catch (error) {
  process.stderr.write("DDH: " + error.message + "\n");
  process.exitCode = 1;
}
