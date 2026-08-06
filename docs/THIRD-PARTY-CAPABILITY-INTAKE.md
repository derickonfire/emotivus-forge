# Third-Party Capability Intake

Forge may reuse mature open-source work when exact provenance, licensing, dependencies, behavior changes, tests, confidentiality, and distribution boundaries are recorded before code is absorbed.

## Record an intake

```bash
forge adopt . \
  --record-third-party-intake research/YESMEM-2.3.5-INTAKE.json \
  --third-party-source /external/review/yesmem-2.3.5.zip
```

The operation must be separate from ordinary Adopt work. The complete upstream archive must remain outside both the project tree and the Forge distribution.

A schema-1 intake binds:

- upstream project and version;
- exact source ZIP SHA-256 and byte length;
- exact reviewed member paths, hashes, and sizes;
- license file identity, SPDX identifier, and copyright declaration;
- dependency closure, including an explicit `none` declaration when appropriate;
- classification as `adapt`, `reimplement`, `design-reference`, or `reject`;
- stage as `reviewed`, `planned`, `implemented`, or `rejected`;
- retained and changed behavior;
- trust-semantic differences;
- security and confidentiality review;
- upstream and Forge-specific tests;
- intended public, development-only, reference-only, or rejected distribution;
- update and retirement procedure.

Forge verifies archive and member bytes at recording time and later checks that the project-owned contract remains unchanged. It also detects the exact upstream archive if it is copied into the project tree.

## Boundaries

A current intake proves exact reviewed provenance and declared adaptation boundaries. It does not provide legal advice, prove correctness or security, discover undeclared dependencies, or authorize release.
