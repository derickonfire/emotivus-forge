# Bounded Exact-Package Release Proof

Forge 0.525 adds a project-owned Release Proof contract beneath `release-ready`. It is an assurance map and receipt validator—not a test runner, reviewer, deployment system, or release authorization mechanism.

## Prerequisite

An exact final-package record must already be active and currently PASS:

```bash
forge adopt . --record-release-package forge-release-package.json
```

The Release Proof contract may then be recorded:

```bash
forge adopt . --record-release-proof forge-release-proof.json
forge ship .
```

## Required domain classification

Every contract must explicitly classify all nine domains:

- security;
- privacy;
- accessibility;
- compatibility;
- installation;
- upgrade;
- rollback;
- runtime;
- deployment.

A domain is either:

- `required` — it names one or more evidence obligations; or
- `not-applicable` — it names no obligations and records a substantive project-owned rationale.

Absence is never interpreted as not applicable.

## Exact-package surfaces

Each declared surface has:

- a stable `surface_id`;
- a bounded kind such as `entrypoint`, `interface`, `artifact`, `installer`, `migration`, `persisted-state`, `documentation`, or `release-channel`;
- a description;
- one or more exact safe ZIP member paths.

Every member must exist in the currently active final package. Every declared surface must be covered by at least one obligation.

## Obligations

Each required obligation defines:

- its assurance domain;
- the exact surface IDs it covers;
- accepted evidence tiers;
- whether an independent reviewer is required;
- the project-owned receipt path.

Supported receipt evidence tiers are `static`, `unit`, `integration`, `entrypoint-execution`, `browser`, `device`, `staging`, `production`, and `manual-review`.

## Receipt binding

A schema-1 receipt must bind its PASS verdict to:

- the Release Proof ID and obligation ID;
- the active release-package ID;
- exact package SHA-256 and byte length;
- current owner-controlled build ID;
- observation and expiry timestamps;
- accepted evidence tier and bounded method description;
- all required surface IDs;
- reviewer authority, role, and independence status;
- one or more evidence artifacts with exact project-relative path, SHA-256, and byte length;
- limitations and an explicit truth boundary.

Missing receipts produce `PARTIAL`. Package mismatch, expired evidence, changed evidence bytes, incomplete surface scope, disallowed evidence tier, unmet independence, changed contract source, or malformed receipts produce `FAIL`.

## Lifecycle

The normalized contract is fingerprint-bound to its project-owned source. A changed or deleted source invalidates the active proof until authority records a renewed contract. Retirement remains explicit:

```bash
forge adopt . \
  --retire-release-proof public-release-proof \
  --release-proof-retirement-reason "The final package was superseded."
```

## Ship claim boundary

A full PASS can support the cumulative `release-proof-validated` Ship level only after all earlier levels pass. It does not make `release-ready` PASS.

A passing result proves only that the project-declared exact-package surfaces are present and that every explicitly required obligation has a current structurally valid package-bound PASS receipt. Forge does not:

- discover undeclared product or release surfaces;
- execute the underlying tests, reviews, deployments, migrations, or rollback drills;
- establish reviewer competence or independence beyond the receipt statement;
- judge substantive methodology or evidence sufficiency outside the declared contract;
- guarantee future evidence validity or remote availability;
- authorize public release.

Final release still requires sufficient real field evidence and a separate owner-controlled authorization bound to the exact final package.
