# Workspace Integrity, Artifact Identity, and Build Attestation

Forge 0.549 retains three distinct controls and adds a reproducible campaign around them. They complement one another; none substitutes for the
others.

## Content-addressed workspace integrity

Run Forge records a bounded content fingerprint of the observed workspace while excluding
`.forge`, version-control metadata, dependency caches, and generated cache trees. A successful
`Check --checkpoint` records an exact seal candidate in existing `state.json`. Ship reassesses
current bytes and refuses to treat the candidate as current after content drift.

The fingerprint binds regular-file bytes, normalized relative paths, sizes, and symlink targets.
It does not use modification time as identity. The default bound is 50,000 files and 2 GB.

A current fingerprint does not establish authorship, authority, semantic correctness, or freedom
from changes outside the observed workspace.

## Same-name, same-version artifact collision detection

Forge scans bounded observed ZIP artifacts and compares exact bytes when two artifacts share the
same basename and declared version. Different bytes produce a visible collision. A filename
version that contradicts an internal Forge manifest is also a failure.

Differently named public, development, website, handoff, and changed-files artifacts are not
silently treated as interchangeable merely because their version strings match.

## Stable source selection during package generation

The deterministic package builder fingerprints every selected source file before writing. Each
read must match its selected digest, and the complete source selection is checked again before
the temporary ZIP is published. Mid-build drift blocks publication and removes the temporary
output.

Use `--build-manifest PATH` to emit a deterministic external build manifest containing the exact
package SHA-256, byte length, member count, edition, packaged version, source-selection digest,
selected-file count, and Forge manifest digest.

## Optional external-key build attestation

Forge never signs with or reads a private key. An owner may sign the exact generated build-manifest
bytes with an external RSA PKCS#1 v1.5 SHA-256 key and verify the result with:

```bash
python3 tools/verify_build_attestation.py \
  RUN-FORGE-0.549.zip \
  RUN-FORGE-0.549.build.json \
  owner-public-key.json \
  RUN-FORGE-0.549.build.sig
```

A PASS means the supplied public key verifies the detached signature and the signed manifest binds
the exact observed package. It does not authenticate the human controller of the key, prove that
the declared source caused the package, grant release authorization, or establish release readiness.

Private-key fields are unsupported, and build manifests must explicitly state
`private_key_retained: false` and `release_authorized: false`.

## Project-owned observation exclusions

Ordinary orientation and artifact-collision observation apply the target project's `.forgeignore`
patterns. This keeps declared inactive material outside those bounded observations. It does not remove
files from manifest-selected packages, explicit exact-package contracts, or confidentiality scans.

## Reproducible campaign

Run `python3 tools/run_integrity_campaign.py . --output research/integrity-campaign-0.544.json` from
the development source root. See `INTEGRITY-FIELD-CAMPAIGNS.md` for scenarios and exclusions.

## Portable owner-keyed ceremony

Forge 0.549 retains a deterministic ceremony kit around build-manifest schema 2. The kit binds the exact
package, exact build manifest, standalone verifier, and public-only templates. Preparation precommits
one expected public-key fingerprint; signing remains external; finalization produces a stable receipt
that can be reverified from exact bytes. A PASS does not authenticate the human key controller or
authorize release. See `OWNER-KEYED-BUILD-ATTESTATION.md`.
