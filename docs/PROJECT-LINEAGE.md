# Exact Project Lineage and Merge-Candidate Quarantine

Forge 0.530 preserves the 0.529 lineage contract and adds a separate migration-identity gate. Forge records project ancestry without treating observation as authority.

## Exact tree identity

Forge hashes a canonical list of regular project files containing normalized relative path, byte length, and SHA-256. File mtimes and ZIP metadata are excluded. `.forge`, the Forge distribution, and explicitly registered lineage control inputs are excluded.

## Lineage contract

A project-owned schema-1 lineage contract declares:

- lineage ID and project-declared authority;
- declared version and build ID;
- relationship: `initial`, `continuation`, `fork`, or `supersession`;
- exact current tree SHA-256 and file count;
- for non-initial work, exact parent ZIP identity and exact parent archive-tree identity;
- any explicit same-version collision declaration;
- a durable truth boundary.

Record it as a separate operation:

```text
forge adopt . --record-lineage examples/forge-lineage.example.json
```

## Same-version collisions

When an existing active or historical lineage uses the same declared version for another exact tree, Forge refuses silent continuation. The new contract must explicitly declare a `fork` or `supersession`, state why, and identify every colliding lineage record.

## Merge candidates

An incoming branch is recorded from an exact parent ZIP and exact incoming ZIP:

```text
forge adopt . --record-merge-candidate examples/forge-merge-candidate.example.json
```

Forge compares parent→incoming and authority→incoming trees, reporting added, modified, deleted, and unique-digest renamed paths. An unmatched parent remains quarantined.

A later separate review may mark it `approved-for-reconciliation` or `rejected`:

```text
forge adopt . --resolve-merge-candidate candidate-id=approved-for-reconciliation \
  --merge-candidate-reason "Reviewed ancestry and selected manual reconciliation only."
```

Approval does not apply files, choose conflict resolutions, change the observed checkpoint, alter the authority baseline, record a new lineage, or authorize the reconciled result.

## Truth boundary

Forge proves equality or inequality of supplied package and normalized tree bytes. It does not prove authorship, legal ownership, semantic compatibility, migration execution, merge correctness, or feature quality. Exact migration identity is recorded separately; see `MIGRATION-IDENTITY.md`.
