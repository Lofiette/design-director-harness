# Pinned context packs

`context_pack.py` is an experimental standalone helper, version **0.1.0**, requiring Python 3.10+ and its standard library. It builds an explicitly selected, private startup packet; an optional route adds relevant sources. Other documents appear only as addresses. It does not install skills, connect host hooks, maintain a task ledger, discover models, publish content or synchronize repositories.

## Input contract

The trusted instance manifest has schema `ddh-context-manifest/1`:

```json
{
  "schema_version": "ddh-context-manifest/1",
  "mode": "pinned_snapshot",
  "task": {"id": "task.id", "objective": "Task objective", "next_action": "Concrete continuation"},
  "repositories": {
    "profile": {"repository": "owner/repository", "revision": "<40 lowercase hex commit SHA>", "visibility": "private"}
  },
  "documents": [
    {"id": "profile.core", "owner": "profile", "path": "docs/context.md", "role": "projection", "visibility": "private", "git_blob_sha": "<40 lowercase hex Git blob SHA>", "sha256": "<64 lowercase hex SHA-256>", "reason": "Compact current context"}
  ],
  "startup": ["profile.core"],
  "routes": {},
  "max_utf8_bytes": 32000
}
```

Placeholders are explanatory and must be replaced before execution. Source roles are `instruction`, `projection`, or `evidence`; classification is `public`, `internal`, or `private`. A document may be more restricted than its repository. The resulting aggregate is always private. The 32,000-byte default is an engineering limit, not a token estimate or a claimed optimal context size. Override it explicitly when a necessary route requires more. Mandatory content is never truncated; an oversized packet fails without publication.

Optional `observed_heads` maps a repository owner to `{revision, observed_at, basis}`. The timestamp must include a timezone. These are supplied observations, not live GitHub verification. Optional `existing_checkpoint_reference` is `{system: "cpt" | "ddh" | "external", reference, sha256?}`. It remains an unverified locator; this module neither creates nor modifies CPT/DDH checkpoint or task state.

## Build and retrieve

```bash
python3 context_pack.py build \
  --manifest /private/instance/session-context.json \
  --root profile=/private/export/profile \
  --source-mode export \
  --output-dir /private/instance/context-packs/new-session

python3 context_pack.py verify --pack-dir /private/instance/context-packs/new-session

python3 context_pack.py build \
  --manifest /private/instance/session-context.json \
  --root profile=/private/checkout/profile \
  --source-mode git --route research --max-bytes 64000 \
  --output-dir /private/instance/context-packs/research

python3 context_pack.py get \
  --manifest /private/instance/session-context.json \
  --root profile=/private/export/profile --source-mode export \
  --id profile.core
```

Repeat `--root owner=path` for each selected owner. No root is required for a repository whose documents are all deferred. There is no fallback to nearby folders or branch names. `get` writes exact UTF-8 source bytes to stdout and a small validation receipt to stderr. Both hashes are checked again. A route selects startup plus its listed sources in stable order, with duplicates removed.

**Export mode** checks local bytes against the caller-supplied SHA-256 and Git blob pins. The caller must obtain those pins from a trusted repository/tree/export process and retain its evidence. This helper does not establish the remote commit-to-tree chain. **Git mode** reads the exact local commit and blob through read-only Git plumbing, ignores dirty worktree content, rejects symlinks/submodules, and performs no fetch or checkout. The association between a local repository and its declared owner/repository is still caller supplied. A local object hash is not a remote-authentication proof.

## Output and verification

A bundle contains `context-pack.md`, `context-manifest.json`, `context-pack.receipt.json`, and exact selected bytes in `sources/`. The receipt records source paths, revisions, both content hashes, roles, reasons, source payload bytes, final Markdown bytes, deferred IDs, supplied-head comparison and explicit limits. Token count stays `null`; a tokenizer is not installed. The bundle ID is deterministic and excludes local roots and current time.

Build uses a private staging directory and a cooperating writer lock before publishing the new directory. An identical retry succeeds; a different existing bundle is preserved and rejected. An interrupted writer may leave a lock/staging directory that requires inspection. The lock is local and is not a distributed transaction. POSIX permissions restrict newly created output files/directories, but repository access controls and safe output-location selection remain necessary. Output inside a declared public source root is rejected.

`verify` rechecks the complete stored manifest, exact selected source bytes, rendered Markdown, source list, hashes and deterministic receipt. It detects accidental modification relative to the supplied manifest. It is not a signature or tamper-resistant audit: a party able to replace both manifest and sources can generate a different internally valid packet. Trust in a committed manifest must be established independently. Files are never executed. Source fences and role labels aid reading but do not replace the host's instruction hierarchy or resistance to untrusted instructions in evidence.

Per-source limit is 1 MiB. The packet is intended for compact selected context; a large raw archive belongs in the source store and is retrieved separately. Native `SessionStart`/`PreCompact` integration, cross-host restore and fresh-agent behavior remain untested by creating a bundle. A host must actually read the packet, follow relevant routes and record the result separately. Existing DDH checkpoint/resume can reference the generated files through its normal artifact contract; this module creates no competing task registry.

## Tests

```bash
python3 -m unittest discover -s modules/continuous-memory/tests -p test_context_pack.py -v
```

Fixtures are synthetic. Tests exercise deterministic exact-byte recovery, idempotence, explicit deferred reads, source/bundle corruption, missing sources, revision drift reporting, size limits, traversal/symlink rejection, output conflicts and exact Git commit reads. They do not establish the quality of an LLM's continuation or successful integration in any particular host.
