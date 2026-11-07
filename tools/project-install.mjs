import { createHash } from "node:crypto";
import { lstatSync, realpathSync } from "node:fs";
import { join } from "node:path";
import { prepareProductOS, readProductOSPacks } from "./product-os-install.mjs";
import { check, inspectPath, installTransaction, managedSkillPath, same } from "./install-transaction.mjs";

const receiptPath = ".agents/ddh-install.json";
const digest = data => createHash("sha256").update(data).digest("hex");
const markers = ["<!-- DDH MANAGED BEGIN -->", "<!-- DDH MANAGED END -->"];

function stat(path) {
  return lstatSync(path, { throwIfNoEntry: false });
}

function mergeAgents(previous, template, expectedHash) {
  const source = previous?.toString("utf8") ?? "";
  check(!previous || Buffer.from(source).equals(previous), "AGENTS.md must be UTF-8");
  const eol = source.includes("\r\n") ? "\r\n" : "\n";
  const body = template.trim().replace(/^# /, "## ").replace(/\r?\n/g, eol);
  const block = [markers[0], body, markers[1]].join(eol);
  const found = [...source.matchAll(/^<!-- DDH MANAGED (BEGIN|END) -->\r?$/gm)];
  if (expectedHash) {
    check(found.length === 2 && found[0][1] === "BEGIN" && found[1][1] === "END",
      "DDH block missing or ambiguous in AGENTS.md");
    const start = found[0].index;
    const end = found[1].index + markers[1].length;
    check(digest(source.slice(start, end)) === expectedHash, "DDH block was edited in AGENTS.md");
    return { contents: Buffer.from(source.slice(0, start) + block + source.slice(end)), blockHash: digest(block) };
  }
  check(found.length === 0, "Existing DDH block has no installation receipt");
  const separator = source ? (source.endsWith("\n") ? eol : eol + eol) : "";
  return { contents: Buffer.from(source + separator + block + eol), blockHash: digest(block) };
}

export function installProject(project, manifest, skills, bootstrap, updateOnly, productOS) {
  const root = realpathSync(project);
  check(stat(root)?.isDirectory(), "Project must be an existing directory");
  check(!stat(join(root, "AGENTS.override.md")), "Resolve AGENTS.override.md before enabling DDH intake");
  return installTransaction(root, () => {
    const oldReceiptBytes = inspectPath(root, receiptPath);
    const old = oldReceiptBytes && JSON.parse(oldReceiptBytes.toString("utf8"));
    check(!updateOnly || old, "No DDH installation in this project");
    if (old) {
      check(old.schema === "ddh-install-v1" && old.files && typeof old.files === "object" &&
        !Array.isArray(old.files) && /^[0-9a-f]{64}$/.test(old.blockHash), "Invalid DDH installation receipt");
    }

    check(productOS || !old?.productOS, "Use update-full for the full DDH profile");
    const packs = productOS ? productOS.packs ?? old?.productOS?.packs ?? [] : [];
    const domainSkills = productOS ? readProductOSPacks(productOS.source, packs) : new Map();
    const next = new Map();
    for (const [id, bundle] of [...skills, ...domainSkills]) {
      for (const [path, data] of bundle) next.set(".agents/skills/" + id + "/" + path, Buffer.from(data));
    }
    const paths = new Set([...next.keys(), ...Object.keys(old?.files ?? {})]);
    const changes = [];
    for (const path of paths) {
      check(managedSkillPath.test(path), "Invalid managed skill path: " + path);
      const before = inspectPath(root, path);
      const expected = old?.files[path];
      if (expected === undefined) {
        check(!before, "Skill path already exists outside this installation: " + path);
      } else {
        check(before && digest(before) === expected, "Managed skill was edited or removed: " + path);
      }
      changes.push({ path, before, after: next.get(path) ?? null });
    }

    const agents = inspectPath(root, "AGENTS.md");
    const cpt = productOS && prepareProductOS(root, agents, productOS.source, productOS.python);
    const { contents, blockHash } = mergeAgents(cpt ? cpt.agents : agents, bootstrap, old?.blockHash);
    if (cpt) changes.unshift(...cpt.changes);
    changes.push({ path: "AGENTS.md", before: agents, after: contents });
    if (cpt?.receipt) {
      cpt.receipt.agents.sha256 = digest(contents);
      changes.push({ path: ".cpt/install.json", before: null,
        after: Buffer.from(JSON.stringify(cpt.receipt, null, 2) + "\n") });
    }
    const receipt = {
      schema: "ddh-install-v1", version: manifest.version, blockHash,
      ...(cpt ? { productOS: { packs } } : {}),
      files: Object.fromEntries([...next].map(([path, data]) => [path, digest(data)])),
    };
    const receiptBytes = Buffer.from(JSON.stringify(receipt, null, 2) + "\n");
    changes.push({ path: receiptPath, before: oldReceiptBytes, after: receiptBytes });

    return {changes, result: {
      project: root, version: manifest.version, skills: skills.size + domainSkills.size,
      ...(cpt ? { productOS: cpt.status, packs } : {}),
      status: changes.every(change => same(change.before, change.after)) ? "unchanged" : old ? "updated" : "installed",
    }};
  });
}
