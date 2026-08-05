# Exact Final-Package and Public-Review Certification

Forge includes three cumulative exact-package certification levels beneath release readiness:

1. **final-package-bound** — one exact ZIP, the current owner-controlled build identity, and registered artifact provenance agree;
2. **confidentiality-screened** — the exact ZIP completes a bounded confidentiality and contamination scan without findings;
3. **public-release-reviewed** — every project-required review receipt is current for the same exact ZIP and build ID.

Record the project-owned contract through Adopt:

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --record-release-package forge-release-package.json
```

Then inspect the cumulative claim ladder:

```bash
python3 Emotivus-Forge/forge.py ship .
```

## Exact final-package binding

The recorded package is bound to:

- the owner-declared project `build_id`;
- the current ZIP SHA-256 and byte size;
- one active artifact-provenance record for the same path and exact bytes;
- the fingerprint of the project-owned release-package contract.

Changing the package, project identity, provenance, or contract invalidates the claim. Forge does not infer which artifact is final.

## Bounded confidentiality scan

The scanner checks the exact ZIP for:

- absolute, empty, or traversal entry names;
- encrypted and symlink entries;
- sensitive live paths such as `.env`, private keys, credentials, database dumps, and owner-declared path patterns;
- private-key material markers;
- non-placeholder secret assignments;
- owner-declared literal contamination terms.

Owner-declared literal values are read from the project-owned contract only while scanning. Forge stores their labels and SHA-256 hashes, not the literal values. Archive contents and secret values are not copied into Forge state.

A scan that reaches its entry or text-byte budget is `PARTIAL`, never PASS.

## Public-review receipts

Supported receipt categories are:

- security;
- privacy;
- accessibility;
- compatibility;
- installation;
- upgrade;
- rollback.

Each receipt must bind to the exact final-package SHA-256, current build ID, named review authority, timestamp, and exact evidence-file digest. Forge verifies those relationships; it does not perform the review or validate its methodology.

## Truth boundary

A passing confidentiality screen cannot prove that every possible secret or confidential fact is absent. A current review receipt cannot prove that the review was competent or complete. Signing, release-channel integrity, bounded Release Proof, sufficient real field evidence, and separate exact-package owner authorization remain outside these three claims.
