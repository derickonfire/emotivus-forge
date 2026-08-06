# Forge Confidentiality Boundary

Forge is a public, project-neutral assurance application. It may inspect a host project to build evidence, but it must not absorb private source, datasets, fixtures, credentials, customer information, or proprietary test content into the Forge product.

## Default model

Forge uses a **metadata-only** integration boundary:

- host files remain in the host project;
- adopted ecosystem registries store relative paths, roles, sizes, and cryptographic hashes;
- generated-state locations are referenced without copying their contents;
- Graph nodes record typed relationships without source snippets or raw command arguments;
- absolute host paths are omitted from persisted Graph output by default;
- external confidentiality policies are supplied by command line or environment and are never packaged with Forge.

## What Forge may retain

Forge may retain project-local evidence needed for continuity:

- relative file paths;
- file sizes and SHA-256 fingerprints;
- tool ownership and lifecycle state;
- command identity fingerprints;
- PASS, FAIL, SKIP, and NOT_RUN evidence;
- affected-surface identifiers;
- generated artifact hashes;
- user-authored project plans and ledger records.

These records remain inside the host project's `.forge/` state. They are not part of Forge's public distribution.

## What Forge must not copy automatically

- application source files;
- production databases or database dumps;
- credentials, private keys, tokens, or environment files;
- customer, employee, biometric, payment, or other regulated data;
- private fixtures, baselines, allowlists, or proprietary test datasets;
- external denylist policies used during private certification;
- host-generated reports whose lifecycle belongs to another tool.

## Confidentiality proof

Run the generic scan:

```bash
python3 Emotivus-Forge/forge.py prove confidentiality .
```

A project owner may provide an external private denylist:

```bash
python3 Emotivus-Forge/forge.py prove confidentiality . --policy /secure/path/private-policy.json
```

Or set the environment variable used by Forge:

```bash
FORGE_PRIVATE_POLICY=/secure/path/private-policy.json \
python3 Emotivus-Forge/forge.py prove confidentiality .
```

The external policy can identify forbidden terms, exact file hashes, normalized text hashes, and path patterns. Findings contain only rule identifiers and affected paths; Forge does not echo the private values.

## Distribution enforcement

Forge's distribution builder scans:

1. the exact manifest-expanded source set;
2. embedded ZIP members in that source set;
3. the completed development or public archive.

A confidentiality finding blocks package creation. The optional private policy is read during the build but is never included in the archive.

## Security boundary

A clean confidentiality scan proves only that the configured contamination and secret rules did not find a match. It does not prove that arbitrary host code is secure or that every form of confidential information can be recognized automatically. Project owners should use a private fingerprint corpus when certifying Forge around sensitive repositories.
