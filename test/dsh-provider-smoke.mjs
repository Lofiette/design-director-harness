import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const [packages] = process.argv.slice(2);
assert.ok(packages, "Pass the installed DSH node_modules/@deepseek-ai directory");
const installed = resolve(packages);
const load = name => import(pathToFileURL(join(installed, name, "lib/index.js")));
const { FileSystemSkillProvider } = await load("dsh-skill-filesystem");
const { renderSkillContent } = await load("dsh-skill");
const { version } = JSON.parse(readFileSync(join(installed, "dsh-skill-filesystem/package.json")));
const cli = fileURLToPath(new URL("../tools/ddh.mjs", import.meta.url));
const parent = realpathSync(tmpdir());
const scratch = mkdtempSync(join(parent, "ddh-5-dsh-"));
const controller = new AbortController();
let provider;
try {
  const project = join(scratch, "project");
  execFileSync(process.execPath, [cli, "pack", "--host", "dsh", "--out", project]);
  const receipt = JSON.parse(readFileSync(join(project, "ddh-pack.json")));
  const ctx = { get: () => undefined, logger: { warn: message => assert.fail(message) } };
  provider = new FileSystemSkillProvider(ctx, { signal: controller.signal, invalidate() {} }, {
    dshHome: join(scratch, "dsh-home"), agentsHome: join(scratch, "agents-home"), watch: false,
  });
  const shared = join(scratch, "shared-project");
  mkdirSync(shared);
  execFileSync(process.execPath, [cli, "install", "--project", shared]);
  const results = {};
  for (const [cwd, source] of [[project, "project-dsh"], [shared, "project-agents"]]) {
    const options = { cwd, signal: controller.signal };
    const candidates = await provider.list(options);
    assert.ok(Array.isArray(candidates), "Provider discovery is incomplete");
    assert.deepEqual(candidates.map(item => item.name).sort(), [...receipt.skills].sort());
    const skills = [];
    for (const candidate of candidates) {
      assert.equal(candidate.source, source);
      const skill = await provider.get(candidate, options);
      assert.equal(skill.name, candidate.name);
      const chars = [...renderSkillContent(skill)].length;
      assert.ok(chars < 7900, skill.name + " rendered over DSH budget");
      skills.push({ name: skill.name, renderedChars: chars });
    }
    results[source] = skills;
  }
  console.log(JSON.stringify({ providerVersion: version, results }, null, 2));
} finally {
  await provider?.dispose();
  const target = realpathSync(scratch);
  assert.equal(dirname(target), parent);
  assert.match(basename(target), /^ddh-5-dsh-[a-zA-Z0-9]+$/);
  rmSync(target, { recursive: true });
}
