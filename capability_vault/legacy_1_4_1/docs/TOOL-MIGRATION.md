# Existing Tool Ecosystem Adoption

Forge must coexist safely with mature projects that already contain validators, linters, tests, baselines, fixtures, dependency maps, defect ledgers, browser suites, build and release scripts, packagers, CI workflows, deployment logic, generated evidence, or AI-agent instructions.

The safe unit of integration is usually **not one script**. It is a tool ecosystem:

- an authoritative manifest or runner
- canonical lifecycle profiles such as quick, section, and release
- source modules and subordinate checks
- configuration and policy files
- static datasets, allowlists, baselines, and registries
- tests and failure fixtures
- generated reports, caches, resumable state, and release artifacts
- ownership and update rules

Forge adopts the orchestration boundary and indexes the full working set. It does not flatten the ecosystem into Forge, copy its files, or register every internal script as a separate Gate command.

## Audit first

```bash
python3 Emotivus-Forge/forge.py maintain tools . --action audit
```

Forge writes:

- `.forge/reports/tool-inventory.json`
- `.forge/reports/tool-inventory.txt`
- `.forge/reports/tool-ecosystems.json`
- `.forge/reports/tool-ecosystems.txt`
- `.forge/tool-ecosystems/<ecosystem-id>.json`
- `.forge/TOOL-MIGRATION-PLAN.md`

The registry contains paths, roles, command metadata, and fingerprints. It does not contain copied tool source or copied datasets.

## Manifest-backed ecosystem discovery

Forge recognizes a host-authoritative ecosystem when a JSON manifest declares both:

- `canonical_paths`: the files and directories that make the toolchain work
- `commands`: its supported entrypoints or profiles

Example:

```json
{
  "name": "Project Quality Suite",
  "canonical_paths": [
    "tools/",
    "tests/fixtures/",
    "tools/data/",
    "TOOLSET-MANIFEST.json"
  ],
  "commands": {
    "quick": "python3 tools/run_release_checks.py --profile quick",
    "section": "python3 tools/run_release_checks.py --profile section",
    "release": "python3 tools/run_release_checks.py --profile release --fresh"
  },
  "forge": {
    "generated_state": [".release-checks", ".staging-acceptance"]
  }
}
```

Forge expands the declared working set, assigns semantic roles, records bundled products as boundaries, and fingerprints the complete input set. Unsafe paths, missing required inputs, or unparseable commands leave the ecosystem in review status.

## Adopt

```bash
python3 Emotivus-Forge/forge.py maintain tools . --action adopt
```

`absorb` remains accepted as a legacy alias for `adopt`.

Adoption:

1. Registers only canonical automatic profiles.
2. Reuses an equivalent command that the project already configured.
3. Suppresses subordinate scripts already owned by the canonical runner.
4. Leaves source, datasets, fixtures, reports, and directories exactly where they are.
5. Records the host project as authoritative.
6. Binds Gate evidence to the current ecosystem-input fingerprint.
7. Blocks execution when a declared ecosystem input is missing or unsafe.

A change to a baseline, fixture, allowlist, manifest, nested tool module, or other declared input changes the command fingerprint and invalidates cached evidence. This prevents a passing result from surviving a material tool-dataset change.

## Generated state

Generated state is referenced, not imported. Forge records whether known report or state directories exist and may summarize their size, but the producing ecosystem retains ownership and cleanup semantics.

Examples include:

- `.release-checks/`
- `.staging-acceptance/`
- browser reports
- coverage output
- resumable execution state
- package receipts

Forge-owned metadata remains under `.forge/`. Project-tool output remains in its original location.

## Bundled and nested products

A toolset may bundle another complete product, including a prior Forge distribution. Forge records that nested root as one bundled product with its own manifest and fingerprint. It does not scan the nested product's internal modules as host-project checks.

This prevents duplicate execution, host/nested ownership confusion, and accidental mutation of a packaged dependency.

## Standalone candidates

Files outside a manifest-backed ecosystem may still be classified individually:

### Retain

The host file remains authoritative and is not safely executable as a Forge check from static evidence.

### Adopt standalone

A narrow command can be registered when Forge has affirmative CLI evidence and the command is not already owned by an ecosystem.

### Review

The file overlaps Forge but may contain project-specific release, architecture, security, deployment, or defect knowledge. Human comparison is required.

### Replace

Only narrow, high-confidence duplication is eligible for reversible quarantine:

```bash
python3 Emotivus-Forge/forge.py maintain tools . --action remove --confirm-tool-removal
```

Forge moves eligible files to `.forge/legacy-tools/`, preserves relative paths, records SHA-256 hashes, and writes a restore manifest. Adoption never implies replacement.

## Human and AI quality-of-life contract

A successful integration should produce:

- one obvious command per assurance lifecycle
- no duplicate subordinate execution
- no moved or renamed host files
- no copied datasets to drift out of sync
- concise ecosystem summaries for an AI context packet
- explicit ownership and lifecycle metadata
- immediate stale-evidence invalidation when tool inputs change
- actionable missing-input diagnostics
- reversible, inspectable configuration changes

The governing principle is:

> Forge adopts metadata and orchestration, not ownership or file layout.

## Safety rules

- Normal initialization is audit-only.
- Forge never silently deletes, relocates, or rewrites an adopted ecosystem.
- Existing CI remains an outer automation layer and may call Forge.
- A manifest cannot escape the project root.
- Secret and immutable exclusions remain authoritative.
- Overlap is not proof of redundancy.
- Generated output stays owned by its producer.
- Quarantine requires explicit confirmation and remains reversible.
