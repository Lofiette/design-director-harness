import { spawnSync } from "node:child_process";
import { lstatSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join, relative, sep } from "node:path";
import { check, cptSeedPaths, inspectPath, managedSkillPath } from "./install-transaction.mjs";

const cptReceipt = ".cpt/install.json";

const packNames = new Set([
  "cpt-design-ui", "cpt-product-research", "cpt-engineering", "cpt-risk-operations", "cpt-ai-agentic",
]);

export function readProductOSPacks(source, packs) {
  check(Array.isArray(packs) && packs.every(pack => packNames.has(pack)) &&
    new Set(packs).size === packs.length, "Choose distinct known Product OS domain packs");
  const skills = new Map();
  for (const pack of packs) {
    const folder = join(source, "domain-packs", pack, "skills");
    for (const entry of readdirSync(folder, { withFileTypes: true })) {
      const id = entry.name;
      check(entry.isDirectory() && /^cpt-[a-z]+(?:-[a-z]+)*$/.test(id) && !skills.has(id),
        "Invalid or duplicate Product OS skill: " + id);
      const root = join(folder, id);
      const files = new Map();
      for (const file of readdirSync(root, { recursive: true, withFileTypes: true })) {
        if (file.isDirectory()) continue;
        const path = relative(root, join(file.parentPath, file.name)).split(sep).join("/");
        check(file.isFile() && managedSkillPath.test(".agents/skills/" + id + "/" + path),
          "Unsupported Product OS skill resource: " + id + "/" + path);
        files.set(path, readFileSync(join(root, path)));
      }
      const entrypoint = files.get("SKILL.md")?.toString("utf8");
      const frontmatter = /^---\r?\nname: ([^\r\n]+)\r?\ndescription: ([^\r\n]+)\r?\n---\r?\n([\s\S]*)$/.exec(entrypoint ?? "");
      check(frontmatter && frontmatter[1] === id && [...frontmatter[2]].length <= 500 &&
        [...frontmatter[3]].length + 640 <= 7900, "Product OS skill exceeds portable budget: " + id);
      skills.set(id, files);
    }
  }
  return skills;
}

const cptMarkers = /^<!-- CPT-OS KERNEL (BEGIN|END) -->\r?$/gm;

function runPython(python, args) {
  const result = spawnSync(python, ["-B", "-X", "utf8", ...args], { encoding: "utf8", windowsHide: true });
  if (result.error) throw new Error("Product OS requires Python with its runtime dependencies: " + result.error.message);
  check(result.status === 0, "Product OS check failed:\n" + (result.stderr || result.stdout).trim());
}

function append(contents, addition) {
  const text = contents?.toString("utf8") ?? "";
  check(!contents || Buffer.from(text).equals(contents), "Project guidance and ignore rules must be UTF-8");
  const eol = text.includes("\r\n") ? "\r\n" : "\n";
  const separator = text ? (text.endsWith("\n") ? eol : eol + eol) : "";
  return Buffer.from(text + separator + addition.trim().replace(/\r?\n/g, eol) + eol);
}

export function prepareProductOS(root, agents, source, python) {
  const scaffold = join(source, "payload", "repo-scaffold");
  const runtime = inspectPath(root, ".cpt/runtime.yaml");
  const markers = [...(agents?.toString("utf8") ?? "").matchAll(cptMarkers)].map(match => match[1]);
  if (runtime || markers.length) {
    check(runtime && markers.join(",") === "BEGIN,END", "Resolve the existing CPT runtime and kernel before adopting DDH");
    const bytes = inspectPath(root, cptReceipt);
    check(bytes && JSON.parse(bytes.toString("utf8")).version === "4.1.0",
      "Adopt a valid Product OS 4.1 installation before enabling the full DDH profile");
    runPython(python, [join(scaffold, ".cpt/bin/cpt_runtime.py"), "--root", root, "validate"]);
    return { agents, changes: [], status: "preserved", receipt: null };
  }

  const cpt = join(root, ".cpt");
  if (lstatSync(cpt, { throwIfNoEntry: false })) {
    // An interrupted fresh install can leave empty directories after repair.
    const entries = readdirSync(cpt);
    check(entries.every(name => name === "bin") &&
      (entries.length === 0 || lstatSync(join(cpt, "bin")).isDirectory() && readdirSync(join(cpt, "bin")).length === 0),
    "Existing files under .cpt require explicit adoption");
  }

  const parent = realpathSync(tmpdir());
  const stage = mkdtempSync(join(parent, "ddh-cpt-seed-"));
  try {
    runPython(python, [
      join(source, "tools/cpt_dist.py"), "install", "--project", stage,
      "--mode", "local", "--plugin-scope", "none", "--agents-policy", "create", "--enforcement-mode", "off",
    ]);
    const changes = [];
    for (const path of cptSeedPaths) {
      if (path === cptReceipt) continue;
      const after = inspectPath(stage, path);
      check(after, "Product OS scaffold is missing " + path);
      changes.push({ path, before: null, after });
    }
    const receipt = JSON.parse(inspectPath(stage, cptReceipt).toString("utf8"));
    const tracked = spawnSync("git", ["-C", root, "ls-files", "--error-unmatch", "--", "AGENTS.md"], { windowsHide: true });
    receipt.agents.tracked_before_install = tracked.status === 0;
    receipt.agents.result = agents ? "merged" : "created";
    receipt.warnings = receipt.warnings.filter(warning =>
      warning !== "Local mode requested, but no Git repository was detected. Runtime files are not automatically hidden from VCS.");

    const ignore = inspectPath(root, ".gitignore");
    if (ignore?.toString("utf8").trimEnd().split(/\r?\n/).at(-1) !== "/.cpt/") {
      changes.unshift({ path: ".gitignore", before: ignore, after: append(ignore, "/.cpt/") });
    }
    return {
      agents: append(agents, inspectPath(stage, "AGENTS.md").toString("utf8")),
      changes, receipt, status: "installed",
    };
  } finally {
    const target = realpathSync(stage);
    check(dirname(target) === parent && basename(target).startsWith("ddh-cpt-seed-"), "Invalid scaffold staging path");
    rmSync(target, { recursive: true });
  }
}
