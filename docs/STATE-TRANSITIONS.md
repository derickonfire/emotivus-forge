# Persisted-State Coverage, Semantic Validation, and Rollback Evidence

Forge 0.525 can bind project-owned state-transition evidence to an exact candidate while keeping untested combinations explicitly `NOT_RUN`.

## Purpose

A state-transition plan declares the persisted-state paths that matter for a project. Forge verifies that supplied owner or external-CI evidence agrees with the current candidate, baseline, artifact, migration bytes, runtime proof, and bounded state expectations.

Forge does not deploy, migrate, restore, roll back, connect to a database, or run arbitrary project validation code.

## State comparison modes

Each before, expected-after, or restored state remains a project-owned JSON snapshot and may use one of three modes:

- `exact` — the observed snapshot SHA-256 must equal the recorded fixture;
- `semantic` — the observed JSON may differ, but every declared bounded validator must pass;
- `exact-and-semantic` — both the exact digest and semantic validators must pass.

Supported semantic validators are deliberately small and deterministic:

- JSON path exists;
- value equals an expected JSON value;
- value is one of an allowed list;
- array count equals or stays within declared bounds;
- array field values are unique;
- every array item contains required fields;
- no array item contains a forbidden field value.

Snapshots are limited to 2 MB. Forge retains snapshot paths, digests, validator IDs, statuses, and short reasons—not the snapshot contents—in routine results and Resume.

## Coverage requirements

Schema-2 plans may declare coverage requirements that group transition IDs using `all` or `any` semantics.

A plan is:

- `PASS` only when every declared transition and coverage requirement is satisfied;
- `PARTIAL` when some required combinations pass and others remain `NOT_RUN`;
- `NOT_RUN` when no transition evidence was supplied;
- `FAIL` when supplied evidence contradicts the contract.

Missing evidence does not fail the project, but it cannot be compressed into complete coverage.

## Rollback levels

Rollback requirements are distinct:

- `none` — no rollback claim is requested;
- `availability` — an owner or CI receipt confirms a declared rollback method is available;
- `drill` — rollback was exercised, the restored state was checked, and required post-rollback Runtime Proof ran.

Forge reports rollback availability, drill execution, and post-rollback state correctness separately.

## Record the contract

```bash
forge adopt . --record-state-transition state-transition-plan.json
```

Schema-1 plans from 0.519 remain accepted. They are normalized to schema 2 with exact snapshot comparison and `required: true` interpreted as a rollback drill.

The contract source, fixtures, artifact, migrations, project identity, semantic validators, coverage requirements, and rollback level are fingerprint-bound. Any change requires renewed authority.

## Evaluate evidence

```bash
forge check . \
  --run-capability runtime-proof \
  --state-transition-evidence state-transition-evidence.json
```

Forge checks:

1. candidate and baseline binding;
2. target environment and deployment stage;
3. before and expected-after snapshot rules;
4. safe semantic JSON invariants where declared;
5. deployment receipt against the exact recorded artifact bytes;
6. migration testimony against current migration digests;
7. same-Check Runtime Proof at the required tier;
8. coverage completeness across declared transition combinations;
9. rollback availability or drill evidence at the declared level;
10. restored-state correctness and post-rollback Runtime Proof when a drill is required.

No supplied evidence means `NOT_RUN`. A mixed matrix remains `PARTIAL`, not complete.

## Token and privacy boundary

Detailed fixture paths, snapshot and receipt hashes, validator results, migration records, and runtime evidence stay in local structured state and the Ledger. Resume emits compact counts for plans, transitions, coverage requirements, semantic state definitions, rollback availability, rollback drills, and authority attention.

Forge does not retain database contents, response bodies, credentials, large dumps, or raw logs. Projects should use neutral, synthetic, or properly protected bounded snapshots.

## What PASS means

A passing transition confirms only that supplied evidence matches the current authority-recorded contract and bytes.

It does not prove:

- Forge performed any deployment, migration, restoration, or rollback;
- the JSON snapshot captures every important data invariant;
- hidden or sensitive production data is correct;
- concurrency, load, permissions, external integrations, or operational rollback access are safe;
- the semantic validators are complete;
- release readiness or production safety.

Ship remains explicit; persisted-state evidence is only one cumulative layer and cannot independently authorize release.

## Additional bounded semantic validators in 0.525

- `json-array-values-in` requires every declared item field to be one of an allowed set.
- `json-array-references-exist` requires every source reference to resolve against a target array field in the same JSON snapshot.

Both validators fail on missing source or target fields and retain only validator status and short reason in routine output.
