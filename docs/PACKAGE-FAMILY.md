# Exact Package Family and Changed-Files Applicability

Forge 0.531 adds a project-owned package-family contract after exact lineage and migration identity.

## What the contract binds

Each family is bound to one active lineage, declared release version, and build ID. Every artifact records:

- stable artifact ID and role;
- exact ZIP SHA-256 and byte length;
- normalized archive-tree SHA-256, file count, and strip prefix.

At least one artifact must normalize to the exact active-lineage tree.

## Outer bundles

A declared outer bundle must itself be an exact family artifact. Each declared embedded member is read from the outer ZIP and compared byte-for-byte with its separately recorded child artifact. Verifying inner artifacts does not authenticate a repackaged outer archive unless that exact outer archive is also recorded.

## Changed-files reconstruction

A delta binds one exact parent artifact, one exact changed-files ZIP, and one exact result artifact. The contract declares added, modified, deleted, and byte-preserving renamed paths. Forge requires the delta payload to contain exactly the result bytes needed for additions, modifications, and rename destinations, then reconstructs the final normalized tree from the parent.

A delta fails when:

- the wrong parent artifact is supplied;
- changed-path declarations differ from the exact parent/result comparison;
- payload paths are missing or extra;
- payload bytes differ from the result artifact;
- a claimed rename changes bytes;
- the reconstructed tree differs from the exact result tree.

## Truth boundary

Forge proves package bytes, normalized tree equality, declared family membership, embedded-member equality, and deterministic delta reconstruction. It does not execute the application, choose semantic conflict resolutions, prove that an undeclared artifact belongs to the family, or establish installation, upgrade, deployment, or rollback safety.
