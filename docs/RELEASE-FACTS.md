# Authoritative Release Facts

Forge 0.533 adds a project-owned, exact-package release-fact contract.

## Purpose

Human-facing release documents often repeat version, schema, build, package, test, and evidence statements. Those copies can drift even when the underlying package is correct. Forge therefore separates:

1. **Canonical fact source** — a bounded value resolved from current project state or an explicit project-owned literal.
2. **Exact packaged document** — a UTF-8 document inside one exact package-family result artifact.
3. **Visible assertion** — the text between project-declared prefix and suffix anchors.
4. **Truth result** — current, stale, contradicted, or not declared.

## Supported canonical sources

- Active lineage ID, version, build ID, and normalized tree SHA-256
- Active migration catalog ID, status, count, maximum sequence, and unresolved collision count
- Active package-family ID, exact result artifact identity, artifact count, ZIP SHA-256, byte length, and normalized tree SHA-256
- Active surface inventory ID, status, coverage status, surface count, complete count, and gap count
- Current native evidence status, validity, and regression count
- Running Forge version, settings schema, and core-state schema
- Explicit project-owned literal values

## Visible document checks

A document assertion declares:

- exact packaged document path;
- fact ID;
- non-empty prefix and suffix;
- exact required occurrence count;
- optional forbidden legacy literals.

Forge extracts every occurrence between the anchors. The assertion passes only when the occurrence count is exact and every visible value equals the canonical rendered value.

## Lifecycle

Recording and retirement are separate Adopt operations:

```text
forge adopt . --record-release-facts forge-release-facts.json
forge adopt . --retire-release-facts release-facts-001 \
  --release-facts-reason "The exact release package was superseded by a newer build."
```

The contract becomes stale or contradicted when its source changes, resolved facts change, exact package bytes drift, a document disappears, an anchor count changes, or a visible value no longer matches.

## Ship boundary

`release-facts-current-candidate` follows `native-verified-candidate` and precedes runtime proof. This permits canonical documents to include current native totals without creating a circular Ship dependency.

## Truth boundary

Forge checks only declared facts and declared visible fields inside one exact package artifact. It does not understand arbitrary prose, discover every stale statement, prove substantive correctness, authenticate the authority, or decide that the chosen facts are sufficient.
