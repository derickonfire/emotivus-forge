# Scoped Check

Forge Check uses one canonical observed change source: the difference between the observed checkpoint and the current bounded snapshot. Externally supplied paths are **corroboration-only**. A supplied path that is not observed as changed is rejected with an explanation and cannot create impact, required checks, or a false critical result.

Each Check produces:

- a canonical observed change ID and full snapshot fingerprints;
- affected surfaces and specific impact dimensions;
- a documentation, website, application, or no-change profile;
- required and actually executed checks;
- confidence and exact exclusions;
- targeted evidence invalidation without a universal numerical impact score.

## Authority baseline and quarantine

Check assesses the explicit project-authority baseline separately from canonical changed-path accounting. `NOT_ESTABLISHED` means no authority record exists. `CURRENT` means the current tree matches the stored baseline. `QUARANTINED` means one or more paths differ. `CONTRADICTED` means the stored baseline fingerprint does not match its own snapshot.

Human-readable Check output prints the complete current fingerprint for review. A passing scoped Check does not clear quarantine or create authority. Advancing an observed checkpoint may reduce the ordinary changed-path count to zero while the authority-baseline delta remains visible. See `AUTHORITY-BASELINES.md`.

## Scoped Forge checks

Checks are selected only when relevant:

- unresolved merge markers for changed readable text;
- JSON syntax for changed JSON;
- Python syntax for changed Python;
- local asset references for changed HTML;
- balanced blocks, strings, and comments for changed CSS/SCSS;
- local target existence for changed Markdown/RST/AsciiDoc.

Documentation-only changes do not automatically select the full native suite. Website-only changes run website-scoped Forge verification; the full native suite remains explicit unless the project later declares a scoped native contract.

## Active Ledger assertions

Every active authority-recorded Ledger assertion is re-evaluated during Check. A failed predicate or a changed/missing assertion source blocks PASS and identifies the specific trusted claim that needs attention. Assertions are deterministic project-state predicates only; they cannot execute arbitrary commands and a passing result does not prove semantic correctness. See `LEDGER-ASSERTIONS.md`.

## Check qualification

After an explicitly requested native run, Forge maps each reported check to a current qualification record. A check is `qualified` only when the current check source, qualification source, and every declared known-bad evidence file match their authority-recorded fingerprints. No record is `unqualified`; changed evidence is `stale`. The observed native result remains separate from qualification status. See `CHECK-QUALIFICATION.md`.

## Atomic guardrails

Authority-recorded guardrails are evaluated against the same canonical observed change set. Partial guarded work is a blocker; unrelated changes are not affected. A passing guardrail proves only declared surface coverage, not correctness or completion. See `GUARDRAILS.md`.

## Native authority and evidence order

A `forge-authorized` canonical gate may be requested with `--run-native`. When requested, it executes **before** Forge-specific checks. Owner-only, external-CI, and evidence-import-only gates never execute through Forge.

Matching owner or CI evidence may be supplied with `--import-native-evidence`. The import is bound to the current candidate ID, gate fingerprint, execution authority, and verification tier and appears in the execution order as `project-native-evidence-import`. Direct execution and evidence import are mutually exclusive.

Raw direct output and exact imported evidence are retained under `.forge/evidence/`. Console and Resume output show summaries and references rather than raw logs.

## Evidence validity

Native evidence records retain type and surface metadata. A change invalidates only connected evidence. For example, a CSS change may stale browser evidence while preserving unrelated migration and runtime evidence.

A structured native failure blocks PASS even when the process exits with code `0`.

## Truth-state accounting

Every executed or omitted proof unit carries a truth state and verification tier. A native gate not requested is `NOT_RUN`; an approval or command prerequisite is `BLOCKED_UNATTEMPTED`; a timeout or launch failure after an attempt is `BLOCKED_ATTEMPTED`. Executed checks are `OBSERVED`. One blocker never explains another result. See `TRUTH-STATE.md`.

## Claim boundary

A passing result is **Scoped Check PASS**. It is not project-level or release-level success. Runtime, browser, database, migration, deployment, and release claims remain excluded unless specifically supported by executed evidence.
## Artifact provenance and perimeter

Check evaluates active provenance records independently from native evidence. Stale registered lineage is blocking. Unregistered deliverable-shaped artifacts are warnings that delivery assurance is unavailable. Neither result proves artifact behavior or deployment.



## Deployable boundaries

When a project authority records a deployable-boundary contract, Check classifies every canonical observed changed path. Role overlap blocks. Strict contracts also block unclassified paths. Configured delta ZIPs require current provenance and are compared with the allowed changed paths and owner-declared baseline. See `DEPLOYABLE-BOUNDARY.md`.

## Canonical claims

Check evaluates explicit authority-recorded owner-facing claims against current identity, registered ZIP membership, migration effects, or evidence identity. Forge first confirms the declared statement still exists in its canonical source. It does not infer arbitrary prose meaning. See `CANONICAL-CLAIMS.md`.
