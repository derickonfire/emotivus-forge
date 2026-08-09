# Emotivus Forge 0.576 — G1 truth-anchoring binders + the witness truth ledger

- `forge bind` adds three deterministic, advisory, read-only G1 binders: source-anchored release verification (accepted-vs-candidate truth bound to the accepted source commit), a gate-coverage differ (checks present in a tree but not wired into its CI gate are reported NOT_RUN, so a green gate can't imply coverage that never ran), and gate-diff monotonicity (a gate-script change removed no assertion and added no SKIP path). Each verdict maps to a CI exit code.
- `forge ledger` adds an append-only, hash-chained witness truth ledger: claim → ground truth → verdict (CONFIRMED / CONTRADICTED / UNVERIFIABLE / INCOMPLETE), supersede-not-delete with visible verdict flips, and no auto-upgrade of a verdict (UNVERIFIABLE is terminal). Any tamper is caught by the chain hash.
- Delivered from real misses surfaced while observing a live cross-model collaboration. Narrative integrity PASS; self-test green. Release authorization remains false.

## 0.575 — Goal 2: leave a session in one command

- A cold model can now close a session through Run Forge itself: `forge run --close <digest.json>` records the durable Session Close, refreshes continuity, surfaces the exact next action, and optionally exports a portable continuity bundle — no separate close/ship workflow. Entering was already one command; now leaving is too.
- Wiring over the existing scoped-Check and Session-Close machinery, regression-locked end to end. `--close` is rejected with `--read-only`.
- Goal 2 status: enter and leave now work in one command; release-candidate routing and the scored cross-vendor cold-trial gate remain. Release authorization remains false.

## 0.574 — Anti-bloat: the certified count is computed, not hand-copied

- Removes the exact test/module count from numeric lockstep across CERTIFICATION, README, the manifest, and a test — a hand-maintained integer that had already silently drifted in ungated copies. The self-test runner reports the count live from the actual suite (`python3 -m emotivus_forge self-test`), so it is always accurate and needs no maintenance.
- Kept every check that prevents a real reader-facing lie: version consistency, state schema, required paths, and download-checksum binding. Prose now describes the suite qualitatively.
- No runtime behavior change; suite stays green. Release authorization remains false.

## 0.573 — Field usefulness + anti-bloat

- Fixes three defects a read-only consultation on a real project exposed, where Forge behaved as a blocker rather than an advisor: a pending decision fork is now advisory instead of a "stop before changing the project" blocker; the objective resolver obeys a document's own "this file is historical/superseded" banner instead of scraping a stale heading; and test/acceptance/gate harnesses are discovered instead of reported as zero.
- Anti-bloat pass on Forge's own self-consistency gates: removed per-chunk timebox format/range enforcement, retired-percentage guards, the exact website-nav-label check, and same-file goal-status duplication — bookkeeping ceremony, not truthful claims. Every check that prevents a real reader-facing misstatement was kept.
- Three regression tests added, four ceremony tests removed: certified suite unchanged at 546 across 58 modules. Verified end-to-end on the real project (right objective, harness discovered, advisory prompt, zero writes). Release authorization remains false.

## 0.572 — Goal 3 (Cross-Model Evolution Kernel) foundation CERTIFIED

- The end-to-end replacement round trip passes: another instance migrates an older package (unknown fields preserved), replaces an obsolete component with a Forge-verified invariant, and emits a compatible continuity package a fresh instance consumes with exact meaning intact.
- G3 moves from FOUNDATION_ACTIVE to CONTINUOUS; evidence inventoried in planning/G3-COMPLETION.md. Goal 1 is COMPLETE, Goal 3's foundation is certified; Goal 2 is the one remaining open goal.
- Certification is of the evolution foundation, not any specific release. Release authorization remains false. Certified suite grows additively to 546 across 58 modules.


- A component replace can declare structured invariant checks (a scoped-Check subject and its required truth-state); Forge verifies them against the actual Check truth records and reports each preserved or violated (a violation raises a warning; free-text invariants stay recorded but unverified).
- A newer model can now replace an obsolete component and have Forge confirm the declared invariants still hold, rather than take the replacement on trust.
- Goal 1 remains certified COMPLETE; release authorization remains false. Certified suite grows additively to 545 across 57 modules.


- A 12-agent adversarial field test of the G3 continuity kernel found two over-assertions; both are closed and regression-locked.
- Lifecycle transitions are now instance-bound like authority and provenance (an imported or forged transition is labeled self-consistent, never counted as authentic).
- The vendor-neutral session digest now screens free-text values for prompt-injection and vendor directives (not only keys), with the truth boundary softened to what the code enforces.
- Goal 1 remains certified COMPLETE; release authorization remains false. Certified suite grows additively to 544 across 57 modules.


- A project authority can record that a named component was retained, folded, frozen, retired, or replaced, via `forge adopt --record-lifecycle-transition`. A fold/replace names its successor; a replace records the invariants that must be preserved.
- Each transition is an append-only, chain-verified ledger event, so component evolution across model generations is auditable (surfaced in the Resume Brief). Whether invariants were actually preserved is a separate verification step.
- Goal 1 remains certified COMPLETE; release authorization remains false. Certified suite grows additively to 542 across 57 modules.


- The continuity kernel is now explicitly vendor-neutral: a distilled session digest that carries model-instruction or vendor-identity keys (system prompts, instructions, model/provider names) is rejected on intake, so it stores project truth rather than model instructions.
- A different model can consume the continuity without inheriting another model's directives. Structural key-based screening; no heuristic content scanning.
- Goal 1 remains certified COMPLETE; release authorization remains false. Certified suite grows additively to 537 across 56 modules.


- Forward migration is now guaranteed to preserve fields this Forge schema does not recognize: an older or another vendor's package keeps its unknown top-level and nested fields verbatim.
- Forge reports preserved-but-unrecognized settings fields (core/forward_compat.py; surfaced in the Resume Brief) rather than interpreting or dropping them. The first piece of the cross-model evolution kernel.
- Goal 1 remains certified COMPLETE; release authorization remains false. Certified suite grows additively to 536 across 56 modules.


- G1 is certified COMPLETE: every completion-rule dimension (exact identity, authority, lineage, evidence binding, adversarial package rejection, package authorization) is verified by a passing adversarial regression, inventoried in planning/G1-COMPLETION.md.
- Independent exact-byte verification: the public package passes its full certified suite 533/533 twice, deterministically, from its own independently extracted bytes.
- Completeness certifies the provable-truth core, not any specific release; release authorization remains false. Certified suite unchanged at 533 across 55 modules.


- Imported native-gate evidence is now bound to the exact source tree it was captured against; once the tree changes, it is reported stale rather than current, even under an unchanged native-gate command.
- Completes the recorded G1 observed-miss backlog. A second recorded finding (same-version collision) was reviewed and did not survive verification, so no speculative fix was made.
- Certified suite grows additively to 533 across 55 modules; release authorization remains false.


- Instance-binding extended to artifact provenance: a deliverable's recorded lineage is asserted CONFIRMED only when its recording event is signed by a key this instance trusts. A byte-matching but unsigned or imported provenance record is honest as current yet not asserted as authenticated provenance.
- Closes the last place the "self-consistent is not authentic" class lived: after authority (0.562–0.563) and provenance (0.564), an imported package can spoof neither authenticated authority nor authenticated provenance.
- Certified suite grows additively to 532 across 55 modules; release authorization remains false.


- An owner-provisioned shared collaboration secret, held out-of-band in each trusted party's Forge home, makes authorizations mutually instance-bound across enrolled parties. A party without the secret sees the same authorization as self-consistent — never release-eligible.
- The enforceable basis for a cross-model collaboration: two different-vendor models can trust each other's "this was authorized" without either being able to forge it, and no imported package can spoof in-instance authority.
- `forge adopt --generate-collaboration-secret` / `--enroll-collaboration-secret`. Certified suite grows additively to 531 across 55 modules; release authorization remains false.


- Authority-baseline authorizations are now signed with a per-instance key stored outside any project tree. Corroboration is tri-state (instance-bound / self-consistent / uncorroborated) and only instance-bound is release-eligible.
- Closes the fabricated-ledger residual: an imported package can rebuild a self-consistent chain but cannot sign under the verifying instance's key, so it stays self-consistent — honest as "current" yet never release-eligible.
- Honest limits stated. Multi-party peer enrollment is next. Certified suite grows additively to 530 across 55 modules; release authorization remains false.


- Adds a genuine read-only consultation mode: `run --read-only` and `resume --read-only`. Forge reads the project's real bytes and prior state but writes nothing into the project tree — its state directory is redirected to a disposable location outside the project (and both repositories) and discarded after the run.
- Unblocks bounded consultation on a shared or third-party repository without adopting it or leaving a `.forge` footprint. The read-only payload is labeled advisory (`read_only: true`) and is never acceptance evidence.
- Certified suite grows additively to 529 focused public-neutral regressions across 55 deterministic isolated modules; release authorization remains false.


- A 15-agent adversarial re-test confirmed all five 0.559 Goal-1 fixes held. The dominant deeper-gate finding: Forge's ledger corroboration chain is unkeyed and travels inside the project's .forge, so a fabricated-consistent chain can spoof in-instance authorship.
- 0.560 responds honestly and bounded: authority-baseline corroboration and the TRUTH_BOUNDARY now state the ledger chain is unkeyed/self-consistent (not a signature, not proof of in-instance authorship); the over-claim "in this instance's ledger" is removed.
- Ship's candidate-unchanged claim carries the bounded size+mtime-only qualifier when un-hashed files exist. Certified suite unchanged at 523/54; release authorization remains false. Full cryptographic instance-binding is recorded as the next increment.


- Hardens the Goal-1 provable-truth core, driven by a 15-agent adversarial field test that probed where a model could push Forge into asserting beyond its evidence. The spine held: tests never shown as passing, document signals never confer authority, self-metrics never authorization, same-version/different-bytes not conflated.
- Imported authority baseline is corroborated against a chain-verified authorization event in this instance's ledger, or demoted to UNCORROBORATED and quarantined from release.
- Change detection reports bounded confidence (never a bare proven "0 changed") when a file was compared by size and modification time instead of hash, and names the un-hashed paths.
- Derived identity, objective, description, and run/test commands are labeled inferred at the point of assertion; the no-objective prompt no longer promises it surfaced any hardcoded secrets. Certified suite unchanged at 523/54; release authorization remains false.


- Ranked ecosystem resolver: primary-language dispatch across Python/Node/Go/Rust/Java/Ruby/PHP + static/notebook, so polyglot/framework projects get correct run/test/identity.
- Extended identity (pom.xml/gemspec/<title>), broader test discovery and secret coverage (.npmrc/npm tokens). Certified suite unchanged at 523/54; release authorization remains false.

## Prior release — 0.557 — Project-Intelligence Completeness

- Completes the project-intelligence pass of the context digest: objective detection on explicit `## Objective`/`Goal:` headings, a deterministic architecture/layout summary, and broader secret coverage (Stripe/generic live tokens and extensionless credential files).
- Certified suite unchanged at 523/54; release authorization remains false.

## Prior release — 0.556 — Context Digest: Trustworthy First Contact

- Delivers the first-contact context digest (Goal 1 redirection per the observed miss), validated by a 12-project spectrum re-test: mean cold-model usefulness 1.83 -> 2.67/5, blocked-before-value 11/12 -> 0/12.
- Secret screening now catches hardcoded secrets in ordinary source at orientation (a hardcoded API key in app.py now BLOCKs, previously missed).
- Reads description, entry points, and run/test commands from the project; identity falls back through go.mod/Cargo.toml/README; prints a measured Resume-vs-repo token comparison; orients before requiring an objective.
- Certified suite unchanged at 523/54; release authorization remains false.

## Prior release — 0.555 — Core-Reduction Close: Orphan Retirement and Edition Proof

- Completes chunk P1-06: retires the fold-orphaned imports left by the P1-04/P1-05 consolidations; confirms no whole module was orphaned and no ceremony-requirement test needed retiring.
- Completes chunk P1-07: rebuilds and independently proves the public and development editions — the public runtime passes 523/54 from its own extracted bytes — with no lost behavior or history. Closes the core-reduction phase.
- Advances the active chunk to P2-01 (Goal 1). Keeps the certified suite unchanged at 523 focused public-neutral regressions across 54 deterministic isolated modules; release authorization remains false.

## Prior release — 0.554 — Service Fold and Ceremony Reduction

- Completes chunk P1-04: consolidates duplicated deterministic plumbing (archive/hash primitives, kit-archive hygiene, the identity build-id read) into the shared truth boundary; distinct-by-design services kept distinct.
- Completes chunk P1-05: reduces the capability-activation ceremony to a minimal enabled/reason/scope/evidence record, preserving every safety gate.
- Removes ~120 net lines across 15 modules with no behavior change; activates P1-06.
- Keeps the certified suite unchanged at 523 focused public-neutral regressions across 54 deterministic isolated modules; 88 runtime modules, zero unreachable, zero unclassified. Release authorization remains false.

## Prior release — 0.553 — Reorientation and Documentation Reduction

- Repositions Forge as the trust layer for AI-built software while keeping the model-collaboration boundary intact.
- Completes Durable Core chunk P1-03: relocates historical and explanatory-only documents into `docs/history/`, out of required reading, with no lost history.
- Advances the active roadmap chunk to P1-04 (folding overlapping release, evidence, rollback, and authority services).
- Classifies version-control metadata in the reachability map now that Forge lives under version control.
- Refreshes the four-page website copy to the trust-layer positioning while retaining the design system and generator.
- Keeps the certified suite unchanged at 523 focused public-neutral regressions across 54 deterministic isolated modules; no behavior added or removed.

## Prior release — 0.552 — Active Runtime Reachability and Path Classification

- Completes P1-01 and P1-02 of the Durable Core roadmap.
- Inventories all 88 active runtime modules.
- Includes ordinary CLI, standalone evidence tools, and verification entry points in the reachability boundary.
- Observes Run Forge, Help, Adopt, Resume, Check, and Ship in bounded neutral fixtures.
- Classifies every active top-level project path by durable goal, support role, or reference disposition.
- Finds zero currently unclassified or globally unreachable active runtime modules.
- Explicitly forbids deletion based solely on one static graph or bounded command trace.
- Preserves the four-page website and its active generated documentation pipeline.

The next active chunk is P1-03: move historical and explanatory-only documents out of required reading.
