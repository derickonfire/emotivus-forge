# Exact Surface-to-Evidence Coverage

Forge 0.532 adds a project-owned surface inventory after exact lineage, migration identity, and package-family proof.

## Purpose

A route list, user-flow map, or source file proves only that a surface is declared and present in one exact result artifact. It does not prove that the surface renders, authenticates, writes to a database, works in a browser, works on a device, or survives deployment.

Forge records those distinctions explicitly.

## Contract

Use a separate Adopt operation:

```bash
forge adopt . --record-surface-coverage forge-surface-coverage.json
```

The schema-1 contract binds:

- one active project lineage;
- one current exact package family;
- one result artifact whose normalized tree equals the active lineage;
- release version and build ID;
- route, journey, API, worker, installation, administrative, or other surfaces;
- exact artifact entrypoints or explicit journey steps;
- audiences and bounded scope;
- one project-required evidence tier per surface;
- immutable receipts bound to the same package family and result artifact.

## Evidence tiers

Forge recognizes these distinct tiers:

1. `source-exists`
2. `static-inspected`
3. `database-executed`
4. `authenticated-executed`
5. `browser-tested`
6. `device-tested`
7. `staging-tested`
8. `production-observed`

Only `source-exists` is derived from the exact package tree. Every higher tier requires an explicit receipt.

A higher tier does not silently fill lower tiers. For example, a browser receipt does not automatically prove database execution, authentication, device behavior, staging deployment, or production observation unless separate receipts explicitly cover those tiers.

## Receipts

Each receipt records:

- exact surface IDs;
- one explicit tier;
- `PASS`, `FAIL`, or `BLOCKED`;
- exact package family and result artifact;
- environment and method;
- reviewer;
- observation and expiration time;
- immutable evidence path, SHA-256, and byte length;
- limitations and truth boundary.

Expired receipts become `STALE`. Missing receipts remain `NOT_RUN`. Failed and blocked evidence stays visible.

## Ship boundary

Ship adds `surface-coverage-mapped-candidate` between package-family identity and native verification.

The level passes only when:

- the exact inventory is current; and
- every declared surface has current explicit `PASS` evidence at its project-declared required tier.

Forge does not decide whether the project selected sufficiently strong required tiers. It does not run the database, authenticate users, drive browsers or devices, deploy the application, establish reviewer competence, or discover undeclared surfaces.
