# Migration Semantic Identity and Reconciliation

Forge 0.530 prevents a migration sequence number from standing in for migration identity.

## Why this exists

Two branches can both record migration `52` while assigning it different SQL, schema effects, or meaning. A database ledger that stores only `52` cannot identify which body actually ran. Forge therefore treats sequence presence as incomplete testimony rather than proof.

## Project-owned catalog

Record one schema-1 catalog for each exact active project lineage:

```text
forge adopt . --record-migration-catalog forge-migration-catalog.json
```

A tracked catalog binds:

- one exact recorded lineage;
- migration engine;
- exact source tree or exact ZIP identity;
- sequence label;
- stable semantic ID;
- project-relative source path;
- exact migration body SHA-256 and byte length;
- durable description;
- optional applied-ledger observation;
- optional append-after-highest reconciliation declarations.

Forge verifies that every declared migration path and digest exists in the exact lineage tree. Changed catalog, source, package, tree, evidence, or migration bytes make the record stale or contradicted.

## Explicit no-migrations mode

Forge does not infer that a project has no persisted migration surface from filenames. A lineage without migrations must record an explicit project-owned declaration:

```text
forge adopt . --record-migration-catalog forge-no-migrations.json
```

The declaration requires a durable reason and remains bound to the exact lineage tree.

## Applied-ledger truth states

Optional project-owned evidence may report which migrations were applied. Forge classifies each catalog entry as:

- `applied-and-matching` — sequence, semantic ID, and body digest all match;
- `number-present-body-unknown` — only the sequence is known;
- `number-collision` — the observed identity conflicts with the catalog;
- `not-applied` — no applied entry was supplied.

A sequence-only legacy ledger remains **body unknown** and cannot satisfy `migration-history-identified-candidate`.

## Cross-lineage collisions

Forge compares every active or retained catalog for the same migration engine. It detects:

- one sequence with different semantic IDs or body digests;
- one semantic ID with different body digests.

An unresolved collision produces `RECONCILIATION_REQUIRED` and blocks higher Ship claims.

## Reconciliation

Historical migration bodies are not rewritten. The active lineage must append a new migration after the highest known sequence and explicitly identify the colliding lineages and sequences it reconciles.

A reconciliation declaration proves only that the exact new migration bytes and declared relationship are recorded. Runtime-state, upgrade, rollback, and deployment evidence must separately establish what happened to representative databases.

## Retirement

Replacement is explicit and separate:

```text
forge adopt . \
  --retire-migration-catalog current-catalog-id \
  --migration-catalog-reason "Replaced after the project adopted a reconciled lineage catalog." \
  --migration-catalog-authority owner
```

Only one migration catalog may be active for one lineage.

## Ship boundary

`migration-history-identified-candidate` requires:

- one current exact project lineage;
- one current exact migration catalog or explicit no-migrations declaration for that lineage;
- no unresolved cross-lineage collision;
- no contradicted or body-unknown applied observation.

It does not prove that migrations executed, that the database matches the intended schema, that upgrades are safe, or that rollback works.
