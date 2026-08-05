# Tool Ecosystem Acceptance — Neutral Synthetic Fixture

## Purpose

Validate that Forge can adopt a manifest-driven tool ecosystem without copying host files, duplicating subordinate checks, exposing private dataset content, or losing the relationships needed for later impact analysis and debugging.

## Fixture

The permanent fixture is generated inside the neutral regression suite. It contains:

- one authoritative runner;
- Quick and Release profile commands;
- a subordinate check;
- a static JSON rules dataset;
- a failure fixture;
- a generated-state location;
- a nested synthetic product boundary.

All names and contents are synthetic. No private application repository is used as a permanent fixture.

## Required behavior

Forge must:

- discover one host-authoritative ecosystem;
- index its complete declared working set;
- register only canonical profile commands;
- suppress subordinate leaf adoption;
- keep datasets and fixtures in place;
- store only relative paths, sizes, roles, and hashes in the registry;
- invalidate prior command evidence when any declared input changes;
- block before execution when a required input is missing;
- represent the ecosystem through typed Graph nodes and edges;
- record lifecycle changes without copying file content;
- preserve nested products as independent ownership boundaries.

## Confidentiality assertion

The fixture includes a synthetic private marker inside a dataset. Regression tests verify that the marker never appears in:

- the ecosystem registry;
- the lifecycle ledger;
- the Graph;
- Forge distribution artifacts.

The marker affects only the dataset hash, which is sufficient to invalidate stale evidence.

## Governing rule

> Forge adopts metadata, evidence relationships, and orchestration. It does not absorb host ownership, private content, or file layout.
