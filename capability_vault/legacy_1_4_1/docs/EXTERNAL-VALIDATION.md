# External Validation Plan

Forge v1.5 will be hardened against a curated corpus of public open-source projects. The purpose is not to collect favorable screenshots or run Forge indiscriminately on popular repositories. The purpose is to measure detection accuracy, coexistence, evidence integrity, context efficiency, and adoption safety across unfamiliar software.

## Source pools

### GitHub and other public forges

Use maintained public repositories with an explicit open-source license, a reproducible tag or commit, and enough documentation to establish the project's intended environment and native assurance system.

### RealWorld implementations

RealWorld provides the same full-stack application specification implemented in multiple front-end and back-end technologies. This is valuable for comparing Forge behavior across stacks while holding product requirements relatively constant.

### Software Heritage

Software Heritage is a durable universal archive of publicly available source code and development history. It is useful for provenance, persistent references, archived releases, and projects no longer reliably available from their original forge.

### OWASP benchmark applications

OWASP Benchmark projects contain known vulnerable and non-vulnerable cases designed to evaluate security-testing accuracy. They are useful for proving that Forge coordinates evidence honestly and does not confuse intentionally vulnerable fixtures with ordinary production applications.

## Corpus construction

The final v1.5 corpus should include at least 15 projects across at least six categories:

1. PHP or traditional server-rendered web applications.
2. Node.js or TypeScript full-stack applications.
3. Python applications and services.
4. JVM or another compiled application stack.
5. Games or interactive applications.
6. Mobile applications or cross-platform clients.
7. Mixed-stack or monorepo systems where appropriate.
8. Legacy or unconventional layouts.
9. Deliberately vulnerable security benchmarks.

The corpus must include mature projects with strong native assurance and less structured projects. Forge must prove both that it can coexist with sophisticated tooling and that it can provide useful first structure where little exists.

## Repository selection rules

- Explicit open-source license verified before download.
- Exact tag, commit, source URL, and retrieval date recorded.
- No repository selected solely because Forge already performs well on it.
- No untrusted installation or build script executed outside an isolated environment.
- Static inspection precedes dependency installation or service startup.
- Network, credentials, databases, containers, and external services are declared before use.
- Security findings in real projects are handled responsibly and are not published casually.
- Project code remains unmodified during first-contact measurement.

## Test sequence

For each project:

1. Record provenance, license, version, expected stack, and native instructions.
2. Run Forge detection without correction.
3. Initialize in audit-only mode.
4. Measure workspace classification, runtime requirements, project identity, tools, tests, and package-manager detection.
5. Run Doctor, Brief, Graph, and Quick Gate.
6. Compare Forge's inventory with the project's documented and actual assurance system.
7. Register only reviewed native commands.
8. Run Section and Release proof where the environment legitimately supports them.
9. Export and re-adopt Forge State.
10. Record false positives, false negatives, missed tools, evidence gaps, time, context size, and required operator intervention.
11. Convert confirmed Forge defects into reviewed regressions before counting the project as complete.

## Primary measures

- Time to first truthful Brief.
- Time to first green Quick Gate.
- Correct stack, version, package-manager, workspace, and environment detection.
- Application-source versus tool-classification precision.
- Native assurance tools found, retained, and correctly registered.
- Required checks that skipped, errored, or failed without being mislabeled.
- Package exclusions, secret safety, path hygiene, and artifact identity.
- Context packet size, relevance, freshness, and missing critical context.
- Ability to resume from portable state on a clean machine.
- Human and AI ability to understand generated instructions without development-team knowledge.

## Reporting discipline

Each field result must distinguish:

- Forge capability confirmed.
- Host-project defect discovered.
- Forge defect discovered.
- Environmental limitation.
- Expected limitation.
- Suggested improvement not yet accepted.

Public website claims may use a field result only when the underlying report and scope are retained. Project-specific evidence must not be represented as universal proof.

## v1.3.2 corrective acceptance record

Before broad v1.5 corpus work, v1.3.1 was exercised on a newly constructed unrelated PHP 8.4/cPanel-style project with unconventional surface paths and no project-specific Forge corrections. Forge correctly blocked unsupported release dimensions but missed a scheduled job and CLI, mistyped a webhook, and treated a support bootstrap as a page. v1.3.2 converts that result into neutral regressions and semantic surface rules.

The corrected inventory contains six unique obligations: two APIs, one browser page, one webhook, one scheduled job, and one CLI. The fixture's support bootstrap is excluded, its configured operations-document claim is flagged, and its Release Proof remains FAIL until current typed evidence is supplied.

This acceptance record is a single corrective data point. It must not be counted as the broad unfamiliar-project validation required for v1.5.
## v1.3.3 post-certification systemic audit

After v1.3.2 certification, the release-proof implementation was audited directly against the retained two-failure recovery specification. The audit did not use either concealed mini application. It constructed minimal neutral cases to ask whether declaration could still substitute for observation.

Two false-proof paths were confirmed:

- A passing command with execution evidence type and `all:browser-page` declared scope could cover every page without reporting any executed page.
- A prewritten PASS JSON file could be referenced as environment or deployment-state evidence without proving that the current verifier produced it.

v1.3.3 turns both findings into permanent regressions and changes the evidence boundary. Exact surface observations must appear in current producer evidence, and referenced evidence files must be created or refreshed by a named current registered Gate producer with a Forge-recorded output hash.

## v1.3.4 neutral sandbox acceptance

The unchanged Harbor Operations scenario was rerun against v1.3.4. The negative branch remained blocked with seven uncovered executable obligations, failed target-environment and prior-state evidence, stale generated-artifact provenance, and an explicit missing-final-bundle problem. The remediated branch reached 7/7 recurring coverage, passed the Release Gate, built the exact final handoff, and passed byte-level member verification.

The run also confirmed that Graph contains one semantic webhook identity and treats `assets/app.js` as supporting source. Refreshing an inner artifact invalidates an earlier final bundle, preventing stale outer handoffs from remaining green.

Named internal applications and obsolete product snapshots are no longer required fixtures or future retest targets. Broad validation continues through neutral fixtures and the license-verified v1.5 external corpus.
## v1.3.5 host-tool ecosystem acceptance

A neutral manifest-driven tool ecosystem is evaluated without modifying its toolchain. Forge indexes one host-authoritative ecosystem, suppresses subordinate leaf adoption, adds no duplicate canonical commands, and preserves all host files byte-for-byte. A controlled dataset mutation changes the adopted Gate command hash, proving that tool data and fixtures participate in evidence freshness.

