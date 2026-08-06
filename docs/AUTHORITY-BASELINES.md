# Authority Baselines and Mutation Quarantine

Forge 0.526 separates two records that must never be conflated:

1. the **observed checkpoint**, used for canonical changed-path accounting; and
2. the **project-authority baseline**, an explicit project-declared acceptance of one exact reviewed snapshot fingerprint.

A passing Check can establish byte stability relative to an observed checkpoint. It cannot establish that the owner or another project authority accepted those bytes.

## Why this exists

Before 0.526, an Adopt refresh could replace the observed checkpoint with the current tree. If unexpected edits were already present, later Checks could report no changes because the altered tree had become the comparison point. Forge could prove continuity from that point forward but could not distinguish owner-approved work from unidentified co-writer work.

Forge 0.526 preserves the prior observed checkpoint during Adopt refreshes and keeps explicit authority in a separate state record.

## Review and authorize

Run Check and copy the complete fingerprint printed as `Review fingerprint`:

```bash
forge check .
```

Then record authorization as a separate Adopt operation:

```bash
forge adopt . \
  --authorize-baseline <64-character-snapshot-sha256> \
  --baseline-authority owner \
  --baseline-authority-source project-declared \
  --baseline-reason "Reviewed the exact current tree and accepted it as the project baseline."
```

Forge recomputes the current snapshot immediately. If any byte or bounded file metadata changed after review, authorization is rejected.

Authorization cannot be combined with unrelated Adopt changes. This prevents a baseline decision from being hidden inside native-gate approval, objective confirmation, contract recording, or another configuration operation.

## Revalidation

A new authority baseline invalidates any earlier candidate checkpoint. Run:

```bash
forge check . --checkpoint
```

Only a later passing checkpoint against the same unchanged exact-strength authority baseline can support `authority-recorded-candidate`.

## Quarantine behavior

When the current tree differs from the authority baseline:

- the authority status becomes `QUARANTINED`;
- all differing paths are reported separately from observed-checkpoint changes;
- scoped Check may still pass within its stated verification boundary;
- `authority-recorded-candidate` and every higher Ship claim remain unavailable;
- advancing the observed checkpoint does not clear the authority quarantine;
- only a new explicit exact-fingerprint authorization can accept the changed tree.

A corrupted authority record is `CONTRADICTED` and blocks authority-bound claims until state integrity is investigated.

## Snapshot strength

An **exact** authority snapshot includes every observed project path and SHA-256 hashes every included file. A **bounded** snapshot has at least one file outside the scan or hash budget. Bounded baselines can preserve a project-declared record, but they cannot support the authority-bound Ship claim.

## Migration

Pre-0.526 snapshots migrate through core state schema 4 as observed-only with a non-authoritative sidecar. Forge never infers project authority from a legacy checkpoint, a passing Check, a native-gate approval, a package signature, or an existing release artifact.

## Truth boundary

Forge binds a project-declared authority record to bounded bytes and metadata. It does not authenticate the named human, prove authorship, identify which process changed a file, or establish that the authority substantively reviewed every behavior. It also does not authorize release.
