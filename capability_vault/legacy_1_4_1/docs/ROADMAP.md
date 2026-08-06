# Emotivus Forge Roadmap to v1.5

Forge remains organized around **Understand, Change, and Prove**. Validation uses neutral, reproducible assurance scenarios and license-verified unfamiliar projects rather than obsolete snapshots of internal applications.

## Validation-scope decision — effective July 30, 2026

Historical internal applications and their old version snapshots are retired from Forge validation scope.

- No named internal application or historical version is a required fixture, release gate, roadmap blocker, or future retest target.
- Their incident lessons remain only as abstract assurance requirements: executable-surface completeness, observed evidence, target-environment parity, persisted-state upgrade safety, and exact delivery provenance.
- New corrections must be reproduced with neutral fixtures or license-verified unfamiliar projects.
- Product teams may use Forge independently, but their current application releases are not part of Forge certification.

## v1.3.6 — Confidential Tool Continuity · Certified

Purpose: preserve the debugging and assurance value of adopted host tools without allowing private project content to enter Forge source, state registries, Graph records, or public distributions.

Delivered:

- Metadata-only confidentiality contract in configuration schema 10.
- Generic secret, sensitive-path, absolute-host-path, and archive-member scanning.
- Optional external private term and fingerprint denylist supplied without entering Forge state or packages.
- Package-builder confidentiality checks against both the exact source set and completed ZIP.
- Typed tool ecosystem Graph nodes and `owns`, `runs`, `reads`, `contains`, and `generates` relationships.
- Command identity fingerprints instead of raw command arguments.
- Relative project paths and no persisted absolute project root by default.
- Metadata-only ecosystem lifecycle ledger with changed-path evidence invalidation.
- Synthetic neutral acceptance documentation replacing all project-specific acceptance references.
- Six permanent regressions; the suite now declares 167 tests.

Exit evidence:

- 167/167 neutral regressions pass.
- Generic and external private-policy confidentiality scans pass against exact source and distributions.
- All 13 Mirror stages pass.
- Extracted development and public distributions pass their complete self-tests.
- A fresh neutral consumer completes initialization, proof, maintenance, and packaging.

## v1.3.5 — Host Tool Ecosystem Adoption · Certified

Purpose: integrate mature project toolchains as complete host-authoritative working systems rather than collections of independently absorbable scripts.

Delivered:

- Manifest-backed ecosystem discovery using canonical paths and commands.
- Full working-set indexing across tool source, tests, fixtures, baselines, allowlists, registries, configuration, release metadata, and bundled products.
- Canonical profile adoption without copying or relocating host files.
- Suppression of subordinate scripts already owned by an authoritative runner.
- Dynamic ecosystem-input fingerprints that invalidate cached evidence when a dataset, fixture, manifest, or tool module changes.
- Missing or unsafe ecosystem inputs block before command execution.
- Generated state remains producer-owned and is referenced rather than imported.
- Nested complete products are treated as bundled ownership boundaries.
- `adopt` is the preferred command; legacy `absorb` remains compatible.
- Permanent validation is carried by synthetic neutral regressions rather than a named private workspace.

## v1.3.4 — Neutral Acceptance and Exact Handoff Correction · Certified

Purpose: correct the product and reporting defects exposed by the neutral Harbor Operations sandbox and close the additional stale-outer-handoff proof gap found during remediation.

Delivered:

- Explicitly required package files override ordinary deployment exclusions while immutable exclusions and secret protections remain authoritative.
- Excluded parent directories remain traversable only as needed to reach an exact required file; excluded siblings remain excluded.
- Graph emits one semantic executable identity per path and classifies browser assets as supporting source rather than server entrypoints.
- Compact Release Proof reports exact delivery-dimension problems separately from claim blockers, avoiding both empty failure reports and handoff-build deadlocks.
- Registered artifact refresh invalidates any previously built final bundle.
- Final ZIP verification rejects duplicate archive paths, missing declared members, and member bytes whose SHA-256 no longer matches the current declared artifact.
- Four permanent neutral regressions were added; the suite now declares 154 tests.
- The unchanged neutral negative branch remains blocked, while the remediated control reaches full Release Gate and exact-handoff PASS.

Exit evidence:

- 154/154 neutral regressions pass.
- Independent bootstrap passes.
- All 13 Mirror stages pass.
- Extracted development and public distributions pass their complete self-tests.
- A fresh neutral consumer initializes, gates, maintains, and packages successfully.
- No named internal application test is required or performed.

## v1.3.3 — Observed Evidence Attestation Hardening · Certified

Delivered exact `FORGE_SURFACE` observations, producer-bound target-environment and deployment-state evidence, output hashing, `produced_in_run` recording, and rejection of declaration-only or prewritten proof. The neutral suite reached 150 tests and all 13 Mirror stages passed.

## v1.4 — Public Release Candidate

Purpose: make Forge legally distributable, understandable, and supportable outside controlled development.

Entry condition:

- v1.3.6 is Mirror-certified with metadata-only host-tool continuity and retained neutral acceptance.
- No named internal application test is required.

Planned scope:

- Owner-selected public software license and dependency/license inventory.
- Final public-package pruning and zero-configuration startup review.
- One authoritative public Forge page with measured claims, limitations, downloads, checksums, changelog, and upgrade path.
- Public documentation usability and accessibility review.
- Anonymous local diagnostics/export with no automatic source upload.
- Invited-beta protocol and issue-report template.
- Stable compatibility and configuration-migration policy.

Exit criteria:

- Public claims trace to retained evidence.
- A new user can install, understand first contact, run proof, and remove or update Forge without developer assistance.
- No private project content or development residue enters the public package.
- License and redistribution terms are explicit.

## v1.5 — Absolute Hardening and External Validation

Purpose: determine whether Forge is a credible generalized assurance product on unfamiliar real-world codebases.

Required corpus:

- At least 15 license-verified external projects.
- At least six categories: mature web application, weak or legacy application, cross-stack reference implementation, security benchmark, game project, and mobile application.
- Multiple languages, package managers, test layouts, deployment styles, persisted-state models, and assurance maturity levels.
- Neutral synthetic fixtures remain regression controls but do not substitute for the external corpus.

Measured outcomes:

- False-green, false-blocker, and false-warning rates.
- Executable-surface discovery completeness and classification precision.
- Evidence-boundary and target-environment accuracy.
- Upgrade-state and delivery-provenance detection.
- Existing-tool coexistence and duplicate-execution rate.
- Context precision and token reduction.
- Update, rollback, state handoff, package integrity, and Mirror reliability.

Exit criteria:

- No known critical false-green path.
- No unresolved critical blocker false positive.
- Every confirmed Forge defect has a reviewed regression or explicit disposition.
- Public and development archives are Mirror-certified from exact source.
- Documentation accurately states measured strengths and limitations.

Kill criteria:

Forge should cease standalone-product development if it cannot generalize its protections to unfamiliar projects without substantial project-specific implementation.

## Deferred

- Additional public cores or branded subsystems.
- Plugin marketplace or multi-project control plane.
- Automatic product-code repair.
- Hosted source upload.
- Public marketing that equates a green Gate with universal deployability.
