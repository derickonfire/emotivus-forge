# Forge Controlled-Core Architecture

Forge uses a small always-available continuity core, lazily loaded services, explicitly activated advanced capabilities, and a cold legacy capability vault.

## Active core

- `core/truth.py` — bounded truth-state vocabulary and verification-tier summaries;
- `core/self_currency.py` — compact validation that Forge's own continuity sources and approvals still match the project;
- `core/project_identity.py` — owner-controlled build, component, contract, baseline, and monotonic identity;
- `core/project_events.py` — authority-confirmed observable events that can close temporary change windows;
- `core/lifecycle.py` — shared fingerprint-bound proposed, active, approval-required, and retired semantics;

- Help and smart startup;
- Progressive Adopt and bounded orientation;
- Project Passport, authority registry, hash-chained Ledger, Resume, and Session Close;
- structured, deduplicated Forge notices;
- strict state integrity, schema migrations, operation locking, rollback, and durable writes;
- supported-knowledge deltas and staleness;
- canonical native quality ecosystem;
- canonical observed-checkpoint reconciliation and surface-scoped Check;
- decision governance and truth-labeled telemetry;
- atomic safety guardrails and event-triggered obligations;
- owner-controlled multi-component identity with compact Resume summaries;
- advanced-capability metadata, recommendations, activation contracts, and fingerprints.

## Command boundary

The CLI contains argument wiring only. Run, Adopt, Resume, Check, Ship, and supporting renderers live in separate command-handler modules. Mutating public commands execute inside one project operation transaction.

## State boundary

The eight top-level `.forge/` files remain the portable continuity unit. Settings migrate explicitly through schema 14, native-tool records through schema 4, and state through schema 3. Identity, project events, confirmed relationships, guardrails, capabilities, field trials, provenance, deployable boundaries, canonical claims, exact native invocations, Release Proof contracts, and portable handoff metadata reuse those files instead of expanding routine context. Malformed state blocks use and remains unchanged. Ledger events are locally hash chained. See `STATE-INTEGRITY.md`.

## Notice boundary

A Forge notice is an interaction receipt, not a replacement for evidence. The AI may append `Forge — <summary>` only when `ai_notice.speak` is true and must not strengthen or fabricate the claim. See `AI-NOTICES.md`.

Run Forge also emits a separate bounded `recommended_prompt`. The notice reports what Forge did; the prompt tells the active AI what to do next. It is capped, copy-ready workflow guidance and cannot override blockers or authority. See `GUIDED-NEXT-PROMPT.md`.

## Lazy services

- native-gate execution and raw evidence retention;
- surface-scoped Check;
- **Forge Doctor**, imported only after an explicit request and current activation contract;
- bounded Ship assessment and cumulative claim ladder.

## Shared contract lifecycle

Project identity, native-gate approvals, capabilities, guardrails, and field trials use shared fingerprint-bound lifecycle meaning: `proposed`, `active`, `approval-required`, or `retired`. Compatibility status names may remain on older records, but a changed or missing authority source cannot silently remain active.

## Capability activation boundary

A recommendation is metadata, not execution. Activation occurs only through Adopt using a project-owned contract with existing evidence, scope, exclusions, budgets, focused regressions, authority, and distinct native value. The contract source is fingerprint-bound. A change or deletion requires renewed approval.

Doctor is diagnose-only. It may observe local environment descriptors and runtime facts. It cannot install, repair, mutate, or claim production equivalence.

## Cold capability vault

The frozen prior source is preserved for migration research and selective future reconnection. Vaulted code is not imported, scanned into host projects, included in Resume, or shipped in the clean public runtime. The active Doctor implementation is clean-room code; it does not import the legacy Doctor or remediation modules.

## Identity and event-obligation boundary

Forge never chooses or increments a host project's version. An authority records one project identity that may contain an immutable build ID, independently versioned present or absent components, contract versions, a baseline, and monotonic derived identifiers. Event obligations remain dormant until their declared project event is authority-confirmed. Once triggered, changed-path coverage still requires explicit authority review and is never treated as feature correctness.

Full identity and event records remain local. Routine Resume output carries only status, build ID, component counts, and actionable exceptions to conserve tokens.

## Evidence and telemetry boundaries

Explicit native execution retains raw evidence under `.forge/evidence/native-gate/`. Check invalidates only connected evidence. `metrics.jsonl` separates observed local facts, exact provider reports supplied by the operator, and heuristic estimates. None of these boundaries independently creates Release Proof or release authorization.
## Artifact provenance

`core/provenance.py` stores authority-recorded artifact lineage inside the settings state. It calculates exact local digests but never executes generator commands. Scoped Check evaluates source currency, output, inputs, generator source, baseline, and the unregistered delivery perimeter.

## Delivery and claim boundaries

`core/deployable_boundary.py` classifies the canonical observed changed set using project-owned roles and can compare registered delta ZIP members with allowed changed paths and the current owner-declared baseline. `core/canonical_claims.py` evaluates explicit identity, archive-membership, migration-effect, and evidence-identity statements. Both are fingerprint-bound and keep detailed evidence local.



## Exact project lineage and branch quarantine

`core/lineage.py` computes bounded normalized regular-file identities for local trees and ZIP archives, excluding mtimes and ZIP metadata. Project-owned schema-1 lineage contracts bind declared version/build metadata to the exact current tree and, for continuations, an exact parent package and archive tree. Same-version/different-tree history requires an explicit fork or supersession declaration.

Incoming branches are retained as schema-1 merge candidates with exact parent and incoming identities plus parent→incoming and authority→incoming path inventories. Candidate review is non-mutating: Forge does not apply files, choose conflicts, advance Check, alter the authority baseline, or authorize the resulting tree.

## Confirmed relationships

`core/relationships.py` stores project-owned relationship sets inside settings schema 21. Check traverses only current recorded relationships to expand impact, surfaces, and required checks. Related paths remain distinct from canonical observed changed paths, and the legacy Graph remains inactive.

## Runtime-state matrix

`core/runtime_matrix.py` records project-owned candidate/environment/prior-state/migration scenarios inside settings schema 21. Scoped Check compares structured owner or CI evidence with current identity and same-Check Runtime Proof results. It performs no deployment or migration action.

## Persisted-state transition boundary

`core/state_transitions.py` stores project-owned transition plans inside settings schema 21. `core/semantic_state.py` evaluates only a bounded deterministic JSON validator vocabulary. Scoped Check compares owner or external-CI snapshots and receipts with current identity, baseline, exact artifact bytes, migration digests, explicit coverage requirements, and same-Check Runtime Proof. Rollback availability, an executed drill, and restored-state correctness remain separate. The modules perform no deployment, migration, restoration, rollback, database connection, arbitrary code execution, or hidden-data inspection.

## Release Proof boundary

`core/release_proof.py` stores project-owned schema-1 assurance maps inside settings schema 21. It requires one currently PASS exact final-package record, explicit classification of all nine release domains, exact ZIP-member surfaces, complete obligation coverage, and current receipts bound to package identity, validity, reviewer requirements, surface scope, and evidence artifacts.

Release Proof performs no tests, reviews, deployments, migrations, restorations, rollback drills, or arbitrary evidence interpretation. It cannot discover undeclared surfaces, establish reviewer competence, authorize release, or make `release-ready` PASS.


### Authority baseline boundary


`core/cold_session_validation.py` stores project-owned schema-2 matched-trial campaigns inside settings schema 21. It binds a separately hashed Forge runtime and exact host release package to current human-reviewed pair receipts, shared task and baseline artifacts, provider/model settings fingerprints, session isolation declarations, receipt age, and bounded coverage thresholds. Controlled fixtures remain diagnostic and do not count toward real Ship coverage.

`core/release_authorization.py` stores one active project-owned schema-1 exact-package authorization inside settings schema 21. It binds the current exact final package to package digest, byte length, build ID, named channels, explicit decision, authority source, validity, rationale, conditions, and source fingerprint. Changed source, package drift, build drift, expiry, or retirement invalidates the claim. Forge validates the contract but does not authenticate the declaring person, establish legal authority, or guarantee future channel state.

`core/authority_baseline.py` separates the movable observed checkpoint from a separately authorized project-tree baseline. Adopt refreshes preserve the checkpoint; exact-fingerprint authorization is a separate transaction; later changes remain quarantined against the authority snapshot even if Check advances the observed checkpoint. Pre-0.526 state migrates as observed-only. The module binds project-declared authority to snapshot bytes and metadata but does not authenticate identity, prove authorship, or authorize release.

### Migration identity

`core/migration_identity.py` stores schema-1 exact migration catalogs inside settings schema 21. Catalogs bind one active lineage to an exact project tree or ZIP, sequence labels, stable semantic IDs, source paths, body digests, optional applied-ledger testimony, and append-after-highest reconciliation declarations. Cross-lineage sequence and semantic-body collisions block Ship before native verification. The module performs no migration, database inspection, upgrade, or rollback.


## Package-family applicability

`core/package_family.py` stores schema-1 exact package-family contracts inside settings schema 21. It binds exact ZIP and normalized tree identities, verifies declared embedded outer-bundle members byte-for-byte, and reconstructs declared changed-files results from one exact parent. It performs no application execution, semantic merge, deployment, or upgrade.

`core/surface_coverage.py` stores schema-1 exact surface inventories inside settings schema 21. It binds declared routes, journeys, APIs, workers, installation, administrative, and other surfaces to one exact result artifact; validates exact entrypoints and journey references; and maps immutable scoped receipts to explicit non-inferred evidence tiers. It does not run databases, authenticate users, drive browsers or devices, deploy applications, discover undeclared surfaces, establish reviewer competence, or choose sufficient project requirements.


`core/release_facts.py` stores schema-1 exact-package fact sets inside settings schema 21. It resolves bounded values from current lineage, migration, package-family, surface, native-evidence, and Forge-schema state or explicit project literals, then checks declared visible fields inside one exact result artifact. It does not parse arbitrary prose, authenticate authority, prove substantive truth, or discover undeclared stale statements.

## Governed continuity register

`core/continuity_register.py` stores one active project-owned schema-1 continuity register inside settings schema 21. Facts have stable identities, trust levels, rationale, impact, exact support references, and truth boundaries. Knowledge gaps have explicit status, priority, blocking scopes, required evidence, owner, resolution, and evidence. Lower-trust records cannot silently replace higher-trust facts, and an open gap cannot disappear without resolution or explicit retirement.

The register contract is lineage-excluded control metadata. Project files cited as evidence remain part of exact tree identity and are separately fingerprinted, so changed support can make both lineage and continuity stale. Forge does not ingest raw conversation history, authenticate the declarer, or prove the substantive correctness of remembered facts. Retrieval is handled separately and never changes authority.

## Bounded session sidecar

`core/sidecar.py` writes compact observational session status inside core state schema 5. It records mode, operation, current scope, authority status, unexpected mutations, and the latest Check or Ship state. It does not monitor the chat, watch the filesystem continuously, invoke Forge in the background, or change authority.

## Third-party capability intake

`core/third_party_intake.py` stores schema-1 exact upstream intake records inside settings schema 21. It verifies one external source ZIP, exact reviewed members, license identity, declared dependencies, adaptation classification, behavior changes, tests, distribution boundary, update process, and retirement. It can detect prohibited full-source absorption into the project tree. It does not execute upstream code, determine legal compatibility, prove security, or authorize release.

## Traceable bounded retrieval

`core/bounded_retrieval.py` reads current governed facts, open gaps, Session Close records, and recent Ledger events. It combines stable-key matching, normalized technical-token similarity, authority-aware deduplication, Reciprocal Rank Fusion, never-fade blockers, and one-hop support traces under a hard result budget. Relevance, authority, and support validity remain separate; retrieval does not mutate state or project authority.

## External evidence intake boundary

`core/external_evidence.py` reviews deterministic return bundles from the owner-attestation and
portable evidence kits. It verifies the exact original kit, archive hygiene, payload allowlists,
payload hashes and sizes, private-key exclusion, workflow-specific semantics, and prior receipt
identity. It emits a content-addressed technical review receipt. This is an intake and adjudication
boundary, not an upload service, key store, provider API, identity service, independent-auditor
registry, release authorization path, or evidence database.

## Browser evidence boundary

`core/browser_evidence.py` verifies one exact website ZIP, safely extracts it, and drives an operator-supplied Chromium-family executable through an optional external Playwright installation. Exact route HTML and package-relative resources come only from the extracted ZIP; external requests are blocked. The module records browser/driver identity, rendered DOM and PNG bytes, console/page/request failures, color-scheme and viewport metrics, horizontal overflow, and one content-addressed receipt. It is not an HTTP server test, physical-device lab, accessibility audit, manual visual review, production monitor, independent reviewer, or release authority.
