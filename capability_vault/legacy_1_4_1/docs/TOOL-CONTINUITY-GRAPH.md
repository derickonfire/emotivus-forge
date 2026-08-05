# Tool Continuity Graph and Lifecycle Ledger

Forge represents an adopted toolchain as one host-authoritative ecosystem rather than a collection of unrelated scripts.

## Typed Graph model

The Graph adds metadata-only nodes for:

- `tool-ecosystem` — the manifest-backed ownership boundary;
- `tool-input-set` — the complete declared working set;
- `tool-command` — a canonical Quick, Section, or Release command;
- `generated-state` — producer-owned report or resumable-state locations;
- `bundled-product` — a nested product with an independent ownership boundary.

Typed relationships include:

- `owns` — the ecosystem owns the declared input set;
- `runs` — the ecosystem exposes a canonical command;
- `reads` — a command's evidence fingerprint depends on the input set;
- `contains` — an input set contains a project file or an ecosystem contains a bundled product;
- `generates` — a command produces state at a host-owned location.

The Graph stores command fingerprints rather than raw command arguments. It stores relative paths and hashes rather than host file contents.

## Development continuity

The registry lifecycle ledger is written to:

```text
.forge/tool-ecosystems/lifecycle.json
```

It records metadata-only events such as:

- ecosystem discovered;
- ecosystem adopted;
- ecosystem status changed;
- declared inputs changed;
- prior evidence becoming stale until the canonical command runs again.

A changed file is recorded by relative path and before/after ecosystem fingerprint. Its contents are not copied into the lifecycle ledger.

## Debugging value

This allows Forge to answer:

- Which canonical tool command is affected by this changed dataset?
- Which evidence is stale?
- Which generated state belongs to the host runner?
- Is this script a top-level command or an internal subordinate check?
- Is a nested product being mistaken for host tooling?
- What changed between the last known tool ecosystem and the current one?

The human project ledger remains the place for decisions, requirements, defects, limitations, and release records. The tool lifecycle ledger supplies machine-observed continuity without silently creating human decisions.
