import { createHash } from "node:crypto";
import { lstatSync, mkdirSync, readFileSync, readdirSync, realpathSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { parseArgs } from "node:util";
import { cases, profiles } from "./cases.mjs";

const digest = data => createHash("sha256").update(data).digest("hex");
const json = value => JSON.stringify(value, null, 2) + "\n";
const readJson = file => JSON.parse(readFileSync(file, "utf8"));
const caseDigest = digest(json(cases));
const runs = profiles.flatMap(profile =>
  Object.keys(cases).map(caseId => ({ id: profile + "-" + caseId, profile, caseId })));

function check(condition, message) {
  if (!condition) throw new Error(message);
}

function save(path, value) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, json(value), { flag: "wx" });
}

function prepare(output) {
  const root = resolve(output);
  mkdirSync(root);
  for (const [caseId, entry] of Object.entries(cases)) {
    const { prompt, secondPrompt, rubric } = entry;
    save(join(root, "operator", caseId + ".json"), { prompt, secondPrompt, rubric });
  }
  for (const run of runs) {
    const folder = join(root, run.id);
    for (const [name, contents] of Object.entries(cases[run.caseId].files)) {
      mkdirSync(join(folder, "project"), { recursive: true });
      writeFileSync(join(folder, "project", name), contents, { flag: "wx" });
    }
    save(join(folder, "review.template.json"), {
      status: null, notes: null, question: null, handoffPath: null,
      checks: Object.fromEntries(Object.keys(cases[run.caseId].rubric).map(id => [id, null])),
      metrics: { elapsedMs: null, attempts: null, inputTokens: null, cachedInputTokens: null, outputTokens: null },
    });
  }
  save(join(root, "plan.json"), { schema: "ddh-benchmark-v1", caseDigest, runs });
  return { root, runs: runs.length };
}

const serviceNames = new Set([".cpt", ".ddh", ".agents", ".codex", ".dsh", "AGENTS.md", ".ddh-install.lock"]);
function scan(root) {
  const product = {};
  const service = {};
  function walk(folder) {
    for (const child of readdirSync(folder, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      if (child.name === ".git") continue;
      const file = join(folder, child.name);
      const path = relative(root, file).split("\\").join("/");
      if (child.isDirectory()) {
        walk(file);
      } else {
        check(child.isFile() && lstatSync(file).size <= 4 * 1024 * 1024, "Unsupported fixture file: " + path);
        const group = serviceNames.has(path.split("/")[0]) ? service : product;
        Object.defineProperty(group, path, { value: digest(readFileSync(file)), enumerable: true });
      }
    }
  }
  walk(root);
  return { product, service };
}

function changes(left, right) {
  return [...new Set([...Object.keys(left), ...Object.keys(right)])]
    .filter(path => Object.hasOwn(left, path) !== Object.hasOwn(right, path) || left[path] !== right[path])
    .sort();
}

function loadSuite(suite) {
  const root = realpathSync(suite);
  const plan = readJson(join(root, "plan.json"));
  check(plan.schema === "ddh-benchmark-v1" && plan.caseDigest === caseDigest &&
    JSON.stringify(plan.runs) === JSON.stringify(runs),
    "Benchmark plan differs from this version");
  return root;
}

function capture(root, run, phase) {
  const folder = join(root, run.id);
  const project = join(folder, "project");
  check(realpathSync(project) === project, "Benchmark project path is redirected");
  const entry = cases[run.caseId];
  const snapshot = scan(project);
  const expected = Object.fromEntries(Object.entries(entry.files).map(([path, body]) => [path, digest(body)]));
  if (phase === "initial") check(changes(expected, snapshot.product).length === 0, "Fixture differs from the source baseline");
  if (phase === "first") {
    check(entry.secondPrompt, "This case has one stage");
    readJson(join(folder, "initial.json"));
  }
  if (phase === "final") readJson(join(folder, entry.secondPrompt ? "first.json" : "initial.json"));
  save(join(folder, phase + ".json"), snapshot);
  return { run: run.id, phase, productFiles: Object.keys(snapshot.product).length, serviceFiles: Object.keys(snapshot.service).length };
}

function optionalJson(path) {
  try { return readJson(path); } catch (error) { if (error.code !== "ENOENT") throw error; return null; }
}

function grade(root, run) {
  const folder = join(root, run.id);
  const entry = cases[run.caseId];
  const initial = optionalJson(join(folder, "initial.json"));
  const first = optionalJson(join(folder, "first.json"));
  const final = optionalJson(join(folder, "final.json"));
  const review = optionalJson(join(folder, "review.json"));
  const result = { ...run, status: "PENDING" };
  if (!review) return result;
  check(review.status === "completed" || review.status === "blocked", "Invalid review status: " + run.id);
  const metrics = review.metrics ?? {};
  const keys = ["elapsedMs", "attempts", "inputTokens", "cachedInputTokens", "outputTokens"];
  result.metrics = Object.fromEntries(keys.map(key => {
    const value = metrics[key] ?? null;
    check(value === null || (Number.isSafeInteger(value) && value >= 0), "Invalid metric " + key + " for " + run.id);
    return [key, value];
  }));
  const { cachedInputTokens, inputTokens } = result.metrics;
  check(cachedInputTokens === null || inputTokens === null || cachedInputTokens <= inputTokens,
    "Cached input exceeds input tokens: " + run.id);
  if (review.status === "blocked") {
    check(typeof review.notes === "string" && review.notes.trim(), "Blocked review needs a reason: " + run.id);
    return { ...result, status: "BLOCKED", notes: review.notes };
  }
  if (!initial || !final || (entry.secondPrompt && !first)) return result;

  const expected = { ...initial.product };
  for (const [path, contents] of Object.entries(entry.expected)) expected[path] = digest(contents);
  const product = { ...final.product };
  const failures = [];
  const protectedChanges = [...new Set([
    ...changes(initial.service, final.service),
    ...(first ? changes(initial.service, first.service) : []),
  ])]
    .filter(path => path === "AGENTS.md" || /^\.(?:agents|codex|dsh)\//.test(path));
  if (protectedChanges.length) failures.push("changed profile instructions: " + protectedChanges.join(", "));
  const rubric = Object.keys(entry.rubric);
  for (const id of rubric) {
    const assessment = review.checks?.[id];
    if (!assessment || typeof assessment.pass !== "boolean" ||
        typeof assessment.evidence !== "string" || !assessment.evidence.trim()) return result;
    if (!assessment.pass) failures.push(id);
  }
  if (entry.deliverable) {
    if (!Object.hasOwn(product, entry.deliverable) || product[entry.deliverable] === digest("")) failures.push("missing design.md");
    delete product[entry.deliverable];
    if (changes(initial.product, first.product).length > 0) failures.push("product changed before clarification");
    if (typeof review.question !== "string" || !review.question.trim()) failures.push("no first question recorded");
  }
  if (run.caseId === "recovery") {
    const path = review.handoffPath;
    const saved = typeof path === "string" && !Object.hasOwn(initial.product, path) &&
      (Object.hasOwn(first.product, path) || Object.hasOwn(first.service, path)) &&
      (first.product[path] ?? first.service[path]);
    const handoff = saved && saved !== digest("") && saved !== initial.service[path];
    if (!handoff) failures.push("missing first-stage handoff");
    if (handoff) delete product[path];
    if (Object.keys(entry.files).some(path => first.product[path] !== initial.product[path])) failures.push("product changed before handoff");
  }
  const unexpected = changes(expected, product);
  if (unexpected.length) failures.push("unexpected product delta: " + unexpected.join(", "));
  return {
    ...result, status: failures.length ? "FAIL" : "PASS", failures,
    serviceFilesChanged: changes(initial.service, final.service).length,
    question: review.question ?? null,
  };
}

function options(args, keys) {
  const { values } = parseArgs({ args, options: Object.fromEntries(keys.map(key => [key, { type: "string" }])) });
  for (const key of keys) check(values[key], "Missing --" + key);
  return values;
}

try {
  const [command, ...args] = process.argv.slice(2);
  let result;
  if (command === "prepare") {
    result = prepare(options(args, ["out"]).out);
  } else if (command === "capture") {
    const { suite, run, phase } = options(args, ["suite", "run", "phase"]);
    const selected = runs.find(candidate => candidate.id === run);
    check(selected && ["initial", "first", "final"].includes(phase), "Unknown run or phase");
    result = capture(loadSuite(suite), selected, phase);
  } else if (command === "report") {
    const root = loadSuite(options(args, ["suite"]).suite);
    result = { schema: "ddh-benchmark-report-v1", runs: runs.map(run => grade(root, run)) };
  } else {
    throw new Error("Usage: bench.mjs prepare | capture | report");
  }
  process.stdout.write(json(result));
} catch (error) {
  process.stderr.write("Benchmark: " + error.message + "\n");
  process.exitCode = 1;
}
