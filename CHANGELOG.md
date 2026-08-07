# Emotivus Forge changelog

## 0.573 — Field usefulness + anti-bloat

- **Fixes three defects a read-only consultation on a real project exposed**, where Forge behaved as a blocker rather than an advisor. Each is regression-locked:
  - **Pending decision fork is advisory, not a blocker.** `resume.py` no longer escalates a pending fork (a choice Forge merely noticed) to a blocker that makes first-contact orientation emit "Stop before changing the project." Only a *contradiction* against a confirmed decision blocks. The same first-contact softening was applied to the self-currency "no explicit objective" path so a cleared objective can't re-trigger the stop.
  - **Objective resolver obeys a document's own staleness banner.** `authority_registry.py` detects a planning doc that disowns itself near the top ("historical/parking context", "superseded by", "does not name the current…") and does not scrape its objective, even when it carries a "next action" heading. The skip is recorded honestly in `rejected_objectives`.
  - **Test/acceptance/gate harnesses are discovered.** `orientation.py` recognizes `check_*`/`*_check`/gate/acceptance/harness files and directories, so a gate-defined project is no longer reported as "tests 0"; the layout states its method and that a non-standard harness can still be missed.
- **Anti-bloat pass on Forge's own self-consistency gates.** Removed the per-chunk 8–20-minute timebox format/range rule, the retired-percentage guards, the exact website-nav-label check, and the same-file goal-status duplication checks from `check_progress_status.py` — ceremony that enforced bookkeeping, not a truthful claim. Kept every check that prevents a real reader-facing misstatement: version consistency, state schema, required paths, download checksums, goal-status vocabulary, and the planning-doc goal rows a reader consults.
- Three new regression tests added, four ceremony tests removed: the certified count stays **546 across 58 modules** and no existing behavior test was altered. Verified end-to-end by re-running the read-only consultation on the real project — right objective, harness discovered, advisory (not blocking) recommended prompt, and zero writes into the target tree.
- G1 COMPLETE, G3 foundation CERTIFIED/CONTINUOUS; G2 remains the one open goal. Release authorization remains **false**.

## 0.572 — Goal 3 (Cross-Model Evolution Kernel) foundation CERTIFIED

- Certifies the **G3 foundation**. The end-to-end replacement round trip passes with real Forge calls (`test_g3_roundtrip`): another instance **migrates** an older package (unknown top-level and nested fields preserved verbatim), **replaces** an obsolete component with a **Forge-verified** invariant, and **emits a compatible continuity package** a **fresh instance consumes** — restoring the eight state files, the preserved unknown field, and the recorded replacement. Exact meaning survives the round trip.
- Every clause of the completion rule is delivered and adversarially tested (the 12-agent field test found + closed two over-assertions in 0.570); the evidence is inventoried in `planning/G3-COMPLETION.md`.
- The roadmap moves **G3 from FOUNDATION_ACTIVE to CONTINUOUS** across all canonical-goal surfaces — the foundation is certified and G3 remains continuous by design. **G1 is COMPLETE, G3's foundation is certified; G2 (one-command session continuity) is the one remaining open goal.**
- Honest boundary: certification is of the evolution *foundation*, not of any specific release. Release authorization remains **false**.
- Certified suite grows additively to **546 focused public-neutral regressions across 58 deterministic isolated modules** (new `test_g3_roundtrip`). P2-01 schema chunk stays active.

## 0.571 — Goal 3: Verified Replacement Invariants (P4-05)

- Continues the cross-model evolution kernel. A component `replace` transition can now declare structured `invariant_checks` — a scoped-Check subject plus its required truth-state — and Forge **verifies** them against the actual Check truth records via `verify_lifecycle_invariants`, wired into `run_scoped_check`.
- Each invariant is reported **preserved** or **violated**; a violation raises a `core.lifecycle-invariant` warning finding. Free-text invariants remain recorded but unverified.
- Delivers the "verify preserved invariants" step of the G3 completion rule: a newer model can replace an obsolete component and have Forge confirm the declared invariants still hold, rather than take the replacement on trust. PRESERVED means the referenced truth still holds — not that the replacement is correct or complete.
- Goal 1 remains certified **COMPLETE**; release authorization remains **false**.
- Certified suite grows additively to **545 focused public-neutral regressions across 57 deterministic isolated modules**. P2-01 schema chunk stays active.

## 0.570 — Goal 3: Field-Test Hardening (lifecycle binding + vendor-neutral free-text)

- A 12-agent adversarial field test of the G3 kernel found two genuine over-assertions of Forge's own ethos; both are closed and regression-locked (`planning/G3-FIELD-TEST-OBSERVED-MISSES.md`).
- **GM-2 — lifecycle instance-binding:** `component-lifecycle-transition` is authority-declared, so it now joins `SIGNED_KINDS` and is signed with the per-instance key. `lifecycle_transition_summary` and the Resume line run `classify_signature` per event and label each transition `instance-bound` vs `self-consistent`; an imported or forged (self-consistent chain) transition is never counted as an authentic in-instance record without the imported label — closing the "self-consistent != authentic" spoof for lifecycle, as already done for authority (0.562) and provenance (0.564).
- **GM-1 — vendor-neutral free-text screening:** `load_session_context` previously guarded only top-level keys, so model directives smuggled into accepted free-text survived. It now screens those values with narrow, high-precision prompt-injection / vendor-directive patterns (ordinary mentions of "system"/"model" are not flagged), and the vendor-neutral truth boundary is softened to state only what the code enforces.
- Goal 1 remains certified **COMPLETE**; release authorization remains **false**.
- Certified suite grows additively to **544 focused public-neutral regressions across 57 deterministic isolated modules**. P2-01 schema chunk stays active.

## 0.569 — Goal 3: Component Lifecycle Records (P4-03)

- Continues the cross-model evolution kernel with **explicit component lifecycle records**. A project authority (or a newer model acting for one) records that a named component was **retained, folded, frozen, retired, or replaced** via `forge adopt --record-lifecycle-transition <contract>`. A `fold`/`replace` names its successor; a `replace` records the **invariants that must be preserved**.
- Each transition is an **append-only, chain-verified ledger event** (`component-lifecycle-transition`), so component evolution across model generations is **auditable**. `lifecycle_transition_summary` gives an audit view, surfaced conditionally in the Resume Brief.
- Delivers the "replace an obsolete component" half of the G3 completion rule with an auditable record. Whether the declared invariants were actually preserved is a separate verification step (kept honest in the truth boundary).
- Goal 1 remains certified **COMPLETE**; release authorization remains **false**.
- Certified suite grows additively to **542 focused public-neutral regressions across 57 deterministic isolated modules** (new `lifecycle` transition functions + `test_lifecycle_transition`). P2-01 schema chunk stays active.

## 0.568 — Goal 3: Vendor-Neutral Continuity (P4-01)

- Continues the cross-model evolution kernel. The continuity kernel is now explicitly **vendor-neutral**: a distilled session digest stores project truth, not model instructions. On intake, `load_session_context` rejects model-instruction and vendor-identity keys — `system_prompt`, `system`, `instructions`, `model_instructions`, `persona`, `prompt`, `prompts`, `tools`, `functions`, `model`, `provider`, `vendor` — alongside the raw-transcript keys it already refused.
- Effect: a **different model can consume the continuity** without inheriting another model's directives. The digest truth boundary states the guarantee explicitly.
- Structural (key-based) screening, consistent with the existing raw-transcript guard — no heuristic content scanning, so legitimate objectives and decisions are never false-flagged.
- Goal 1 remains certified **COMPLETE**; release authorization remains **false**.
- Certified suite grows additively to **537 focused public-neutral regressions across 56 deterministic isolated modules**. P2-01 schema chunk stays active.

## 0.567 — Goal 3: Forward-Compatible Migration (begun)

- Opens the cross-model evolution kernel. Forward migration is now **guaranteed to preserve fields this Forge schema does not recognize** — an older or another vendor's package keeps its unknown top-level **and** nested fields verbatim through migration, locked by a regression so a future refactor cannot silently start dropping data.
- New `core/forward_compat.py` **reports preserved-but-unrecognized** settings fields; the Resume Brief surfaces a `Forward-compat:` line listing them (only when present). Unknown fields are retained verbatim and never interpreted, trusted, or treated as authority, evidence, or lineage.
- This is the first piece of the G3 completion rule (migrate an older package, preserve exact meaning): Forge migrates without losing meaning and reports exactly what it did not understand.
- Goal 1 remains certified **COMPLETE**; release authorization remains **false**.
- Certified suite grows additively to **536 focused public-neutral regressions across 56 deterministic isolated modules** (new `forward_compat` module + `test_forward_compat`). P2-01 schema chunk stays active.

## 0.566 — Goal 1 (Provable Project Truth) certified COMPLETE

- Certifies **G1 COMPLETE**. Each dimension of the completion rule — exact identity, authority (import rejection, single- and multi-party instance-binding), lineage, evidence binding (provenance + native evidence), adversarial package rejection, and package authorization — is verified by a passing adversarial regression, inventoried in `planning/G1-COMPLETION.md`.
- **Independent exact-byte verification (P2-09):** the public `RUN-FORGE.zip` passes its full certified suite **533/533 twice, deterministically, from its own independently extracted bytes**.
- Roadmap moves G1 from ACTIVE to **COMPLETE** and marks P2-08 (adversarial trials) and P2-09 (exact-byte verification) satisfied. The near-term queue advances to the G3 continuity kernel and G2 close-out.
- **Honest boundary:** completeness certifies the provable-truth core, not any specific release. Release authorization remains **false**; Forge authenticates a key/instance, not a human identity or review quality. DG-7 was reviewed and did not survive verification (no speculative fix).
- No behavior change; the certified suite is unchanged at **533 focused public-neutral regressions across 55 deterministic isolated modules**. P2-01 schema chunk stays active.

## 0.565 — Native-Evidence Source Binding (DG-8)

- Binds imported native-gate evidence to the exact source tree it was captured against. `import_native_evidence` captures the current tree fingerprint and persists it on `evidence.native_gate.source_tree_fingerprint`; a shared helper `evidence_validity.effective_native_validity` downgrades the reported validity to `stale-source-changed` at the reader surfaces (Resume, self-currency) when the current tree fingerprint differs.
- Effect: evidence captured for tree A no longer reads as `current` for tree B, even under an unchanged native-gate command fingerprint — closing the last recorded G1 observed miss (DG-8).
- **DG-7 (same-version collision) reviewed, not a confirmed gap.** The collision guard in `record_merge_candidate` already keys off differing bytes (`incoming tree != authority tree`) and the declared version; the field-test's suggested fix referenced a non-existent `incoming.declared_version` field. The realistic residual is owner-declaration integrity, not a Forge authenticity spoof. No speculative change made; recorded in `planning/G1-RETEST-0559-OBSERVED-MISSES.md`.
- Proven by a regression: import evidence (bound to the current tree), change the tree, and assert the evidence is reported `stale-source-changed`.
- Certified suite grows additively to **533 focused public-neutral regressions across 55 deterministic isolated modules**. Release authorization remains false; P2-01 schema chunk stays active.

## 0.564 — Provenance Parity (instance-binding for artifact provenance)

- Extends cryptographic instance-binding from authority baselines to **artifact provenance**. `artifact-provenance-recorded` is now a signed ledger event; `evaluate_artifact_provenance` corroborates each active record against its signed event (instance-bound / self-consistent / uncorroborated); and the scoped Check asserts `CONFIRMED` for a deliverable's lineage **only when that recording is instance-bound**.
- A byte-matching but **unsigned or imported** provenance record stays honest as "current" but is not asserted as authenticated provenance — its truth-state is `OBSERVED`, with a reason that says the recording is not instance-bound.
- **Closes the last place** the "self-consistent ≠ authentic" class lived: after authority (0.562–0.563) and provenance (0.564), an imported package can spoof neither authenticated authority nor authenticated provenance.
- Proven by a regression: record provenance (instance-bound → `CONFIRMED`), strip the signature from the recording event, and assert it drops to `self-consistent` and loses `CONFIRMED`.
- Certified suite grows additively to **532 focused public-neutral regressions across 55 deterministic isolated modules**. Release authorization remains false; P2-01 schema chunk stays active.

## 0.563 — Multi-Party Instance-Binding (peer enrollment)

- Completes cryptographic instance-binding across parties. The owner provisions a **shared collaboration secret** into each trusted party's Forge home — `forge adopt --generate-collaboration-secret` creates and stores one; `--enroll-collaboration-secret <PATH_OR_HEX>` enrolls it elsewhere — **out-of-band, never through a project repo**.
- Authorizations signed with the collaboration key are **mutually instance-bound** for every enrolled party. Signing prefers the collaboration key when enrolled (team-trusted by default) and falls back to the per-instance key; verification trusts this instance's own key and the enrolled collaboration key. A party without the secret sees the same authorization as `self-consistent` — honest, but never release-eligible.
- This is the enforceable basis for a cross-model collaboration (e.g. LineCheck): two different-vendor models trust each other's "this was authorized" without either being able to forge it, and no imported package can spoof in-instance authority.
- Proven by a regression running two distinct Forge homes: with the shared secret both reach `instance-bound` and release eligibility; the home without it stays `self-consistent` and not release-eligible until it enrolls the same secret.
- Certified suite grows additively to **531 focused public-neutral regressions across 55 deterministic isolated modules**. Release authorization remains false; P2-01 schema chunk stays active.

## 0.562 — Cryptographic Instance-Binding (begun)

- Turns the honest 0.560 corroboration boundary into an **enforced** one. Authority-baseline authorization events are now signed with a **per-instance key stored outside any project tree** (`core/instance_key.py`, Forge home, `FORGE_HOME`-overridable). The signature is excluded from the ledger canonical hash, so the chain is unchanged; `key_id` is covered by the event hash.
- Corroboration is **tri-state**: `instance-bound` (matching chain-verified event signed by a key this instance trusts — its own), `self-consistent` (a matching event that is unsigned or signed by an imported/foreign key), or `uncorroborated` (no match / broken chain). **Only `instance-bound` confers release eligibility.**
- **Closes the fabricated-ledger residual** from the 0.559 re-test (DG-1..DG-5, `planning/G1-RETEST-0559-OBSERVED-MISSES.md`): an imported package can rebuild a self-consistent chain but cannot produce a signature under the verifying instance's key, so it stays `self-consistent` — honest as "current" yet never release-eligible. A regression strips the signature from a legitimately authorized event and asserts it drops to `self-consistent` and loses release eligibility.
- Honest limits in `TRUTH_BOUNDARY`: authenticates a key/instance, not a human or review quality; a stolen instance secret (machine compromise) defeats it; an unavailable Forge home degrades to unsigned rather than falsely claiming binding.
- **Next increment:** multi-party peer enrollment (the owner-provisioned collaboration secret) so trusted collaborators' authorizations are mutually instance-bound — the enforceable basis for the cross-model LineCheck collaboration.
- Certified suite grows additively to **530 focused public-neutral regressions across 55 deterministic isolated modules**. Release authorization remains false; P2-01 schema chunk stays active.

## 0.561 — Read-Only Consultation Mode

- Adds a genuine **read-only consultation mode**: `run --read-only` and `resume --read-only`. Forge reads the project's real bytes and prior `.forge` state but **writes nothing into the project tree** — the state directory is redirected to a disposable location outside the project (and both repositories) via a single interception (`state_root` / `redirect_state` in `core/paths.py`, honored by every ForgePaths-based read/write and the storage lock), used for the run, then discarded.
- This unblocks bounded, agreement-compliant consultation on a **shared or third-party repository** (e.g. a multi-model collaboration): Forge can advise on continuity, changed-surface scope, stale evidence, or handoff completeness without adopting the project or leaving a `.forge` footprint. The read-only payload is labeled advisory (`read_only: true` with stated limitations) and is never acceptance evidence.
- Normal (persisting) operation is unchanged; `--read-only` simply skips the lock and redirects state.
- Proven by a whole-tree byte-identity regression: the target tree (fresh and adopted) is hashed before and after and asserted identical.
- Certified suite grows **additively** to **529 focused public-neutral regressions across 55 deterministic isolated modules** (new `test_read_only_consult` module; six regressions). Release authorization remains false; P2-01 schema chunk stays active.

## 0.560 — Honest Corroboration Boundary

- A 15-agent adversarial re-test confirmed all five 0.559 Goal-1 fixes **held** (bounded change confidence, inferred-vs-confirmed labels, scoped secrets claim, gated run commands, and imported-baseline corroboration for ordinary tamper/mismatch cases). Three deeper-gate lenses also held (stale-evidence-as-current, NOT_RUN native gate → PASS, snapshot-fingerprint collision).
- **Dominant deeper-gate finding — "self-consistent != authentic":** Forge's ledger/corroboration chain is an unkeyed public SHA-256 chain that travels inside the project's `.forge`, so a fabricated-but-consistent chain (or an imported legacy state) can spoof `authority-baseline-authorized` corroboration and artifact-provenance CONFIRMED. Recorded in `planning/G1-RETEST-0559-OBSERVED-MISSES.md`.
- **0.560 response (bounded, honest):** corroboration wording and the authority `TRUTH_BOUNDARY` now state that the chain is unkeyed and travels with the project — a match proves internal consistency and that an authorization event exists, but is not a signature and cannot prove in-instance authorship. The over-claim "in this instance's ledger" is removed; corroboration carries `binding: unkeyed-self-consistent`.
- **Ship bounded phrasing:** the `candidate-unchanged` requirement reason carries the size+mtime-only, not-byte-verified qualifier when un-hashed files exist (the M-G1-2 phrasing now reaches `ship_claims.py`).
- **Recorded for the next increment (needs design, not a rushed seal):** cryptographic instance-binding (a per-instance key an imported package cannot reproduce) for authority + provenance, migration downgrade of imported `active` baselines, same-version-collision-by-bytes, and native-evidence source binding.
- Additive; certified suite unchanged at 523/54 (regression extended in place); release authorization remains false; P2-01 schema chunk stays active.

## 0.559 — Provable-Truth Core (G1)

- Driven by a 15-agent adversarial field test (`planning/G1-FIELD-TEST-OBSERVED-MISSES.md`) probing where a model could push Forge into asserting beyond its evidence. The spine held — tests never shown as passing, document signals never confer authority, self-metrics never authorization, same-version/different-bytes not conflated — and these fixes close the five certainty leaks it found.
- **Imported authority baseline (critical):** `assess_authority_baseline` now corroborates an `active` baseline against a chain-verified `authority-baseline-authorized` ledger event whose id + fingerprint re-derive; an imported/hand-edited baseline with no such event is demoted to `UNCORROBORATED`, `release_eligible=false`, and quarantined. It corroborates that authorization happened in this instance's tamper-evident history (it does not authenticate a human identity).
- **Change confidence (high):** `compare_snapshots` records paths compared by size+mtime alone (un-hashed) as `unverified`; confidence caps at `bounded` whenever any exist, and the human surfaces print `0 path(s) (bounded: N file(s) … not byte-verified)` instead of a bare proven "0 changed". Authority `CURRENT` over un-hashed files carries the bounded qualifier.
- **Evidence-tier labeling (high):** a scraped README/`<title>` name is `inferred` (manifest-declared `observed`), never `confirmed`; a derived objective renders "derived objective (unconfirmed)" not "confirmed objective"; description and run/test commands render as derived/inferred and not executed; a command line is rejected as a description; `go run` is gated on an observed `main` package.
- **Completeness claim (high):** the no-objective recommended prompt no longer promises "any hardcoded secrets" surfaced; the claim is scoped as bounded, not exhaustive.
- Additive; certified suite unchanged at 523/54 (regressions extended in place); release authorization remains false; P2-01 schema chunk stays active.

## 0.558 — Ecosystem Resolver

- Replaced the hardcoded if/elif language dispatch in `orientation.derive_orientation` with a ranked ecosystem resolver: source-file counts + manifest boost + app-framework boost (manage.py/artisan/config.ru) select the primary language, so polyglot/framework projects (Laravel with a Vite package.json, a Java lib with a docs site) no longer mis-dispatch. Correct run/test/entry across Python, Node, Go, Rust, Java (Maven/Gradle), Ruby (Rake/rack), PHP (composer/Laravel), notebooks, and static sites.
- Identity fallback extended to pom.xml (name/artifactId, parent-stripped), `*.gemspec` name, and `<title>` for static sites. Test discovery now includes root `test.js`, `*.test.js`/`*.spec.js`, `*_test.go` via a shared `_looks_test`. `primary_source_dir` biases toward real source roots (src/app/lib/internal/pkg) over config/vendored dirs. Description hygiene skips license/copyright/SPDX lines and truncates at a word boundary.
- Secret coverage: content-scan `.npmrc`/`.pypirc`/`.dockercfg`/`.git-credentials` and a new `npm-auth-token` BLOCK rule (quantifier form; self-screen stays clean).
- Validated on the spectrum batch-1 failure cases: Laravel run `php artisan serve`, Java identity "Apache Commons CLI" + mvn, Ruby `rake test`, static site named from `<title>`, `.npmrc` token BLOCK. Additive; certified suite unchanged at 523/54; release authorization remains false.

## 0.557 — Project-Intelligence Completeness

- Objective detection: `OBJECTIVE_HEADINGS` gained `objective`/`goal` and the inline regex now recognizes `Objective:`/`Goal:` (and `**bold**`), so an explicit `## Objective` heading resolves to status=explicit — Forge no longer nags when the objective is written down.
- Architecture/layout: a deterministic summary from file paths (top-level dirs + counts, file-type histogram, primary source dir/language with tests excluded, packages, test dir/count), surfaced in the passport, resume, and terminal. Central files are reused from `code_orientation.centrality` (previously computed and discarded) in the passport only, keeping specific paths out of the compact resume.
- Secret coverage: added Stripe `[sr]k_live_` and generic `tok_live_` BLOCK rules (quantifier form so the self-screen stays clean) and content-scanning of extensionless credential files (aws-credentials, credentials, .netrc, .pgpass, .htpasswd). aws-credentials, config.json api_token, and Stripe keys now all BLOCK. Residual: an all-lowercase DB_PASSWORD value is not an individual finding (file still BLOCK via siblings).
- Additive throughout; certified suite unchanged at 523/54; release authorization remains false; P2-01 schema chunk stays active.

## 0.557 — Project-Intelligence Completeness

- Objective detection: `OBJECTIVE_HEADINGS` gained `objective`/`goal` and the inline regex now recognizes `Objective:`/`Goal:` (and `**bold**`), so an explicit `## Objective` heading resolves to status=explicit — Forge no longer nags when the objective is written down.
- Architecture/layout: a deterministic summary from file paths (top-level dirs + counts, file-type histogram, primary source dir/language with tests excluded, packages, test dir/count), surfaced in the passport, resume, and terminal. Central files are reused from `code_orientation.centrality` (previously computed and discarded) in the passport only.
- Secret coverage: added Stripe `[sr]k_live_` and generic `tok_live_` BLOCK rules (quantifier form so the self-screen stays clean) and content-scanning of extensionless credential files (aws-credentials, credentials, .netrc, .pgpass, .htpasswd). aws-credentials, config.json api_token, and Stripe keys now all BLOCK.
- Additive throughout; certified suite unchanged at 523/54; release authorization remains false; P2-01 schema chunk stays active.

## 0.556 — Context Digest: Trustworthy First Contact

- Delivered the first-contact context digest — the observed-miss redirection of Goal 1 toward project intelligence, validated by a 12-project spectrum re-test (mean cold-model usefulness 1.83 -> 2.67/5; blocked-before-value 11/12 -> 0/12).
- Secret screening now content-scans ordinary source at orientation via a bounded full-text pass (not only filename-flagged files). The target-user case — a hardcoded API key in app.py — now returns BLOCK where it was previously missed; values are never retained.
- Added first-contact orientation (`orientation.derive_orientation`): a one-line description, entry points, and run/test commands read from the project; identity now falls back go.mod -> Cargo.toml -> README H1 -> directory.
- Added a measured Resume-vs-repo token-economics line (e.g. Flask ~1k tokens vs ~467k to read the tree); made empty NOT_DECLARED governance lazy in the compact digest; made a missing objective a warning on read-only first contact (a blocker only once there are changes), so Forge orients before blocking.
- The terminal FORGE STARTED block now leads with What it is / How to run / a Secrets BLOCK/REVIEW alert.
- Fixed digest defects the spectrum test surfaced: no more hallucinated entry points (exact relative-path membership), no `cargo run` for library-only crates, and prose descriptions skip badges/kaomoji.
- Additive throughout; certified suite unchanged at 523/54; release authorization remains false. The formal P2-01 schema chunk stays active.

## 0.555 — Core-Reduction Close: Orphan Retirement and Edition Proof

- Completed Durable Core chunk **P1-06**: retired the fold-orphaned imports left by the P1-04/P1-05 consolidations (`stat`, `hashlib`, `ZIP_TIMESTAMP`, `read_json`, and the now-unused `project_identity_record` imports across the release modules; `release_proof` also carried a never-called `_current_build_id` helper). Confirmed no whole module was orphaned (88 reachable, zero unreachable) and no ceremony-requirement test existed to retire. Genuinely pre-existing dead imports were left in scope for a later dedicated pass.
- Completed Durable Core chunk **P1-07**: rebuilt and independently proved the public and development editions. The public `RUN-FORGE.zip` passes the full 523/54 suite from its own extracted bytes and runs `python3 forge.py`; no history was lost (git history, `docs/history/`, and the changelog retain every fold and prior version). This closes the core-reduction phase.
- Advanced the active chunk to **P2-01** (Goal 1: define the minimal project-truth schema).
- Preserved the certified suite unchanged at 523 focused public-neutral regressions across 54 deterministic isolated modules. Release authorization remains false.

## 0.554 — Service Fold and Ceremony Reduction

- Completed Durable Core chunk **P1-04**: consolidated duplicated deterministic plumbing into the shared truth boundary — the archive/hash primitives and kit-archive hygiene into `core/common.py`, and the active build-id read into `core/project_identity.current_build_id`. Routed the four evidence modules, three release modules, and four integrity modules through them. The genuinely distinct services (receipt evaluators, kit verifiers' identity logic) were evaluated and correctly left distinct-by-design.
- Completed Durable Core chunk **P1-05**: reduced the capability-activation ceremony to a minimal enabled/reason/scope/evidence record. Dropped the `focused_regressions`, `native_advantage`, and `allow_repairs` attestations and made `authority`/`scope` optional, while preserving every enforced safety gate (path/evidence containment, budget caps, runtime-proof egress allowlist, and fingerprint binding). The no-repair / no-credential guarantee is structural in the services, not a contract field.
- Removed ~120 net lines across 15 modules with no behavior change. Advanced the active chunk to **P1-06** (remove only modules made unreachable by completed folds).
- Preserved the certified suite unchanged at 523 focused public-neutral regressions across 54 deterministic isolated modules; runtime inventory holds at 88 modules with zero unreachable and zero unclassified. Release authorization remains false.

## 0.553 — Reorientation and Documentation Reduction

- Repositioned Forge as the trust layer for AI-built software (verdict in `FORGE-2029-VERDICT.md`), keeping the model-collaboration boundary intact.
- Added the forward `ROADMAP-2029.md` and executable `DEVELOPMENT-ROADMAP.md` above the sealed chunk ledger, and recorded the agent-native invocation miss (`F-553-003`) under the expansion rule.
- Classified version-control metadata (`.git/`, `.github/`, `.gitignore`, `.gitattributes`) in the runtime reachability mapper now that Forge lives under version control (`F-553-001`).
- Completed Durable Core chunk **P1-03**: relocated historical and explanatory-only documents into `docs/history/`, out of required reading, with no lost history. Advanced the active chunk to **P1-04**.
- Refreshed the four-page website copy to the trust-layer positioning while retaining the design system, logo, palette, and generator.
- Preserved the certified regression suite unchanged at 523 focused public-neutral regressions across 54 deterministic isolated modules; no behavior added or removed.

## 0.552 — Active Runtime Reachability and Path Classification

- Completed Durable Core chunks P1-01 and P1-02.
- Added deterministic static import mapping across ordinary CLI, standalone tools, and verification roots.
- Added bounded command-path traces for Run Forge, Help, Adopt, Resume, Check, and Ship.
- Classified all 88 runtime modules and every active top-level path.
- Recorded zero globally unreachable active modules and prohibited deletion based on incomplete reachability alone.
- Added six focused regressions, bringing the declared suite to 523 tests across 54 modules.
- Preserved the four-page generated website and model-collaboration boundary.

## 0.551 — Durable Core Roadmap Reset

Retired the percentage roadmap, established three outcome goals, reduced the generated website to four pages, added timeboxed roadmap chunks and a durable-core inventory, and clarified that Forge supplies verified context rather than model instructions.

# Changelog

## 0.549 — Authority-Gated Aggregate Check Truth

- Corrected the reproduced case where a clean unbaselined tree received top-level `Scoped Check PASS`.
- Added aggregate `NOT_RUN` while preserving clean component observations and keeping actual defects as `FAIL`.
- Added exact resolving artifact and command guidance for separate fingerprint-bound baseline authorization and follow-up checkpointing.
- Prevented unbaselined Check from advancing checkpoints or satisfying Ship's `last-check-pass` requirement.
- Migrated portable writer and six-scenario integrity campaigns to the explicit `NOT_RUN → authority → PASS checkpoint → DRIFTED refusal` lifecycle.
- Preserved and audited `FORGE-FINAL-RECOMMENDATION.md` as testimony, disproving stale status claims and declining unsupported safety-contract deletion.
- Expanded focused public-neutral regressions from 510 to 515 across 53 isolated modules.
- Relabeled the seven-axis 89% as implementation-and-instrument coverage, not efficacy; an admissible defect scoreboard remains `NOT_RUN`.
- Updated the axes to 90 / 98 / 97 / 88 / 99 / 63 / 88 — 623 / 7 = 89.0%.

## 0.548 — Exact Browser Viewport Evidence

- Added bounded exact-website ZIP verification and extraction with duplicate, unsafe-path, symlink, encryption, CRC, member-count, member-size, and expanded-size refusal.
- Added optional external Playwright execution against an operator-supplied Chromium-family executable; neither dependency is bundled.
- Added network-isolated package routing for exact route HTML and package-relative resources while blocking external requests.
- Added content-addressed DOM, PNG, console, page-exception, request-failure, resource, color-scheme, viewport, and horizontal-overflow evidence.
- Added deterministic browser-evidence bundles and exact later verification against the website package digest and strict false authority/readiness flags.
- Executed a real local Linux campaign across six routes at 1440×900 light and 390×844 dark without claiming physical devices, accessibility, production origin, independence, owner authorization, or release readiness.
- Expanded focused public-neutral regressions from 502 to 510 across 52 isolated modules.
- Advanced the seven-axis roadmap to 90 / 98 / 96 / 88 / 99 / 63 / 88 — 622 / 7 = 88.9%, reported as 89%.

## 0.547 — Portable Evidence Return and Bounded Adjudication

- Added deterministic exact-kit-bound return archives for owner-attestation, independent-writer, and matched-handoff workflows.
- Added strict inbound archive budgets, hygiene, payload allowlists, exact payload identities, and private-key-material refusal.
- Added source-owned recomputation of signature, drift, raw Ship refusal, immutable-task, exact-token, accepted-review, workspace-isolation, and paired-arm semantics.
- Added content-addressed review receipts and `FIRST_SEEN`, `DUPLICATE_EXACT`, and `CONFLICTING_SUBMISSION` lifecycle classification.
- Normalized new portable public-key fingerprints to the Forge core canonical profile while retaining bounded sealed-0.546 compatibility.
- Preserved false reviewer/owner authentication, false independence, false release authorization, and false release readiness.
- Expanded focused public-neutral regressions from 496 to 502 across 51 isolated modules.
- Advanced the seven-axis roadmap to 90 / 98 / 96 / 88 / 99 / 62 / 87 — 620 / 7 = 88.6%, reported as 89%.

## 0.546 — Portable Owner-Keyed Build Attestation Ceremony

- Added build-manifest schema 2 with exact packaged Forge-manifest digest, byte-length, version, and edition verification.
- Added deterministic exact-package owner-attestation ceremony kits with fixed payload identities and self-verification.
- Added public-key fingerprint precommitment before external signing.
- Added standalone prepare, finalize, and receipt-reverification workflows using public material and detached signatures only.
- Added structured `NOT_RUN` for absent signatures and structured refusal for altered keys, packages, manifests, signatures, receipts, and kit payloads.
- Preserved false release authorization, unauthenticated human identity, no private-key custody, five public commands, eight state files, settings schema 21, and core schema 5.
- Expanded focused public-neutral regressions from 485 to 496 across 50 isolated modules.
- Advanced the seven-axis roadmap to 90 / 98 / 96 / 88 / 99 / 61 / 84 — 616 / 7 = 88.0%.

## 0.545 — Portable Evidence Execution Kits

- Added deterministic public-neutral evidence kits bound to one exact public runtime by version, SHA-256, byte length, and member count.
- Added fixed-timestamp archive construction, exact payload manifests, immutable benchmark-task identity, archive hygiene checks, source-drift refusal, and extracted-kit self-verification.
- Added a standalone three-invocation controller/writer/reviewer protocol preserving a random challenge, checkpoint-bound target bytes, exact before/after hashes, process and operating-system metadata, and exact-runtime Ship refusal.
- Kept operator independence explicitly unauthenticated and local success classified only as a reviewed candidate.
- Added sealed Forge/control benchmark packets with distinct workspaces, exact task/runtime/provider/model identity, null token templates, and named accepted-review requirements.
- Added finalization through Forge's existing benchmark instrument, refusing missing or estimated tokens, changed identities, incorrect arms, shared workspaces, or absent accepted review.
- Preserved `NOT_RUN`, `independent_evidence_claimed: false`, `release_authorized: false`, and `private_key_retained: false` in every newly built kit.
- Expanded focused public-neutral regressions from 478 to 485 across 49 modules.
- Advanced the continuity-first roadmap to 90 / 98 / 96 / 88 / 99 / 61 / 82 — 614 / 7 = 87.7%, reported as 88%.

## 0.544 — Integrity Field Campaigns and Self-Hosting Boundaries

- Added one deterministic six-scenario public-neutral campaign covering post-checkpoint external mutation, actual pre-publication package-source drift, rival same-version artifacts, filename/manifest disagreement, explicit quarantine recovery, and project-owned ignore behavior.
- Made artifact-collision observation honor the same `.forgeignore` contract as ordinary project orientation.
- Added a Forge self-development exclusion contract for synthetic examples, the cold capability vault, generated downloads, deployment output, release checks, and the nested public runtime without changing manifest-selected package membership.
- Required an active authority-backed requirement before high-impact decision-fork detection may create a pending fork.
- Corrected the self-host startup and handoff contract so development source and exact public runtime remain distinct.
- Exposed deterministic package construction as a callable boundary with a Python-only pre-publication observation callback; the CLI retains no mutation bypass.
- Preserved settings schema 21, core state schema 5, five public commands, eight top-level state files, and separate false release authorization.
- Expanded focused public-neutral regressions from 475 to 478 across 48 isolated modules.
- Advanced roadmap axes to 90 / 98 / 96 / 88 / 99 / 58 / 77, averaging 86.6% and reported as 87%.

## 0.543 — Workspace Integrity and Exact Build Identity

- Added content-addressed workspace observations and exact passing checkpoint seal candidates inside existing core state.
- Made Ship refuse candidates after post-checkpoint content drift without relying on modification times.
- Added bounded same-basename, same-version ZIP collision detection using exact bytes and packaged-manifest identity.
- Hardened deterministic packaging so every selected read matches a pre-build digest and the source selection is rechecked before output publication.
- Added structural narrative-integrity certification across version, regression/module counts, schemas, required paths, roadmap arithmetic, website checksums, release notes, and embedded runtime version.
- Added deterministic build manifests and optional external RSA detached-signature verification with public keys only; private key retention and release authorization remain false.
- Completed the provenance-gated YesMem 2.3.5 report-only secret-pattern adaptation with Apache-2.0 attribution and deliberate rejection of noisy email, phone, public-IP, and arbitrary long-hex defaults.
- Completed a bounded proxy-observation audit; no additional false blocker was found.
- Recorded the first real handoff consumption attempt as inadmissible and `NOT_RUN` because exact provider token counts, named human review, and a matched control arm are absent.
- Advanced core state from schema 4 to 5 while preserving settings schema 21, five public commands, eight top-level state files, and no daemon or proxy.
- Expanded focused public-neutral regressions from 444 to 475 across 47 isolated modules.
- Reopened the lineage axis from 100% to 96% under owner-authorized scope; axes are 90 / 96 / 96 / 88 / 99 / 58 / 76, averaging 86.1% and reported as 86%.

## 0.542 — Second-Interpreter Field Evidence and Doctor Runtime Correction

- Executed the full regression suite under a second Python version, 3.11.15, alongside 3.12.3. This is the first cross-version evidence in the project's history, and the first certification run on more than one interpreter.
- Found a real product defect that single-version certification could not surface: the doctor capability resolved `python3` on PATH and ignored the interpreter Forge was running under, so a correctly pinned project inside a virtual environment or pyenv shim drew a false blocker.
- Corrected doctor to observe the running interpreter first and PATH `python3` second, to pass when either satisfies the declared pin, and to record which runtime satisfied it.
- Kept the real failure intact: a pin matching no observed runtime still raises a blocker, and the message now lists every runtime considered.
- Added 4 regressions covering runtime resolution, false-blocker avoidance, genuine-mismatch blocking, and satisfaction attribution.
- Expanded focused public-neutral regressions from 440 to 444 across 44 modules, passing on both 3.11.15 and 3.12.3 on all four execution surfaces.
- Built under a workspace-fingerprint guard after a concurrent writer was detected corrupting an earlier attempt.
- Roadmap: real-world comparative validation 55% to 58% for genuine cross-version evidence; approximate overall 86% to 87%.

## 0.541 — Reproducible Continuity Benchmark

- Added `emotivus_forge/core/continuity_benchmark.py` as a measuring instrument for continuity comparisons.
- Made benchmark tasks immutable and content-addressed: any field change produces a different task, never an edited one.
- Required exact parent package digests, declared provider and model identity, and isolated workspaces per run.
- Required provider-reported exact token counts and rejected heuristic estimates outright rather than averaging guesses into a result.
- Made runs inadmissible until a named human reviewer accepts them.
- Refused to pair runs differing in task, parent, provider, or model, because that comparison measures the environment rather than Forge.
- Reported zero admissible runs as NOT_RUN and never as a tie, a pass, or a neutral result.
- Made declared stress suites carry execution_status NOT_RUN, sessions_recorded 0, and declared_not_executed true, so intent is never read as achievement.
- Persisted nothing: the harness writes no state and adds no ninth state file, no sixth public command, and no daemon.
- Expanded focused public-neutral regressions from 415 to 440 across 44 modules.
- Roadmap: real-world comparative validation 50% to 55% for the instrument only; zero sessions have been executed. Approximate overall remains 86%.

## 0.540 — Non-Authoritative Code Orientation

- Added `emotivus_forge/core/code_orientation.py` with three inference views: active zones, file centrality, and change coupling.
- Marked every record `authority: none` and `evidence_tier: inferred`, and declared four explicit refusals: orientation never advances a baseline, qualifies a Check, authorizes a release, or becomes a governed fact.
- Derived active zones and coupling from recorded ledger history only; an absent ledger reports an explicit knowledge gap rather than a false zero.
- Refused filesystem timestamps as an activity signal, with a regression asserting the module never reads mtime, ctime, or atime.
- Flagged ambiguous file stems instead of silently crediting either owner, and excluded self-references from centrality.
- Skipped sweeping events above sixty paths so a broad refactor cannot couple everything with everything.
- Exposed the result through `orient_project` without adding a sixth public command, a ninth state file, or any persistence.
- Expanded focused public-neutral regressions from 395 to 415 across 43 modules.
- Roadmap: change intelligence and scoped verification 94% to 96%; approximate overall 85% to 86%.

## 0.539 — Optional Five-Command Session Adapters

- Added `emotivus_forge/core/session_adapters.py` with three lifecycle events: `session_start` may invoke Run Forge, `milestone` may invoke Check, `session_end` may guide Session Close.
- Shipped every adapter off by default; the global switch dominates every per-event switch, and an invalid configuration resolves inactive rather than partially applying.
- Rejected authority delegation in code rather than documentation: baseline advancement, change approval, merge, release authorization, state mutation, prompt rewriting, and continuous running are validation errors.
- Refused a sixth public command and a ninth state file; adapters persist nothing and emit a declarative host-invoked one-shot contract.
- Advanced settings schema from 20 to 21 with an automatic migration that adds the block switched off.
- Corrected a latent defect where a second hardcoded schema registry in `core/storage.py` capped settings at 20; both bounds now derive from the constants, and a regression asserts they track.
- Expanded focused public-neutral regressions from 375 to 395 across 42 modules.
- Roadmap: integration, interoperability and token efficiency 72% to 76%; approximate overall remains 85%.

## 0.538 — Tiered Confidentiality and Secret Screening

- Added `emotivus_forge/core/secret_screening.py` classifying every confidentiality finding as BLOCK, REVIEW, or INFORMATIONAL.
- Added Forge-native shape rules for private-key blocks, cloud access-key identifiers, inline connection-string credentials, bearer headers, JSON Web Tokens, and provider access-token shapes.
- Escalated high-entropy secret assignments inside live sensitive files to BLOCK; kept ordinary-file literals at REVIEW.
- Downgraded declared synthetic fixture paths to INFORMATIONAL with a visible `downgraded_from` reason rather than a silent exemption.
- Guaranteed that no finding retains a matched value and that screening never edits scanned bytes.
- Advanced `CONFIDENTIALITY-POLICY.json` to schema 2 with tiered term and path lists, still shipping empty denylists by design.
- Gated distribution builds on BLOCK, reported REVIEW inline, and added `--fail-on-review` for strict mode.
- Added name-segment and value-plausibility precision rules so metric counters and dict keys are not reported as credentials.
- Expanded focused public-neutral regressions from 344 to 372 across 41 modules.
- Roadmap: exact-package release truth and authorization 98% to 99%; approximate overall remains 85%.

## 0.537 — Certification Findings Correction

- Normalized the seven test modules that imported `support` directly so all forty modules import `tests.support`; the suite now reproduces 344/344 under plain `unittest discover` with no `PYTHONPATH` prerequisite.
- Replaced four private-project evidence filenames in `docs/LINEAGE-SAFETY-AMENDMENT.md` with neutral descriptors, applying that document's own lesson that field failures become neutral fixtures only after proprietary details are removed.
- No behavior, schema, command, or state-file change. Settings schema remains 20, core state schema 4, five public commands, eight top-level state files.
- Regression count unchanged at 344 across 40 focused modules; roadmap percentages unchanged from 0.536.

## 0.536 — Run Forge Active Pass and Session Reconciliation

- Restored Run Forge as a bounded active project-intelligence pass followed by passive sidecar mode.
- Added optional transient `forge-session-context/1` review while rejecting raw transcript fields.
- Added request and AI-claim alignment against changed and checked paths with an explicit non-semantic truth boundary.
- Added one structured Forge Brief.
- Made successful Session Close regenerate compact Resume automatically.
- Preserved settings schema 20, core state schema 4, five public commands, and eight top-level state files.
- Advanced the continuity-first roadmap to 90%, 100%, 94%, 88%, 98%, 50%, and 72% — approximately 85% overall.
- Expanded focused public-neutral regressions from 338 to 344.

## 0.535 — Third-Party Intake and Traceable Retrieval

- Added exact external third-party source-archive and reviewed-member identity.
- Added license, attribution, dependency, adaptation, test, distribution, update, and retirement records.
- Added detection for prohibited full-source absorption into a project tree.
- Recorded a bounded YesMem 2.3.5 intake while keeping the archive external and unexecuted.
- Added Forge-native traceable retrieval across governed facts, open gaps, Session Close records, and recent Ledger events.
- Added normalized technical-token similarity, authority-aware deduplication, Reciprocal Rank Fusion, never-fade blockers, and bounded support traces.
- Added optional Resume queries without adding a sixth public command.
- Advanced settings schema from 19 to 20 while retaining core state schema 4 and eight top-level state files.
- Advanced the continuity-first roadmap to 84%, 100%, 94%, 88%, 98%, 50%, and 66% — approximately 83% overall.
- Expanded focused public-neutral regressions from 325 to 338.

## 0.534 — Governed Continuity

- Added one active project-owned continuity register with stable fact and gap identities.
- Added owner-declared, project-evidenced, developer-recorded, agent-inferred, and automatically extracted trust levels.
- Added exact project-file, Ledger-event, and contract-declaration support references with support-drift detection.
- Added explicit open and resolved knowledge gaps with priority, blocking scope, required evidence, owner, resolution, and evidence.
- Prevented lower-trust replacement and silent disappearance of current facts or open gaps.
- Added a compact non-authoritative session sidecar inside existing core state.
- Integrated governed continuity through Adopt, Resume, Check, Ledger, Ship, state migration, and storage integrity.
- Advanced settings schema from 18 to 19 and core state schema from 3 to 4 without adding a ninth state file.
- Rebased the continuity-first roadmap to 78%, 100%, 94%, 88%, 98%, 50%, and 58% — approximately 81% overall.
- Expanded focused public-neutral regressions from 314 to 325.

## 0.533 — Authoritative Exact-Package Release Facts

- Added project-owned release-fact contracts bound to one exact lineage, build, package family, and result artifact.
- Added bounded fact sources for lineage, migration identity, package identity, surface coverage, native evidence, Forge schemas, and explicit literals.
- Added visible exact-package document assertions with prefix/suffix extraction and exact occurrence counts.
- Added forbidden legacy literal detection and current, stale, contradicted, not-declared, and retired lifecycle states.
- Added cumulative `release-facts-current-candidate` after native verification and before runtime proof.
- Advanced settings schema from 17 to 18 without adding a ninth top-level state file.
- Updated canonical progress to 100%, 100%, 100%, 50%, 88%, and 98% — approximately 89% overall.
- Expanded focused public-neutral regressions from 307 to 314.

## 0.532 — Exact Surface-to-Evidence Coverage

- Added project-owned exact surface inventories bound to one active lineage, package family, result artifact, release version, and build ID.
- Added route, journey, API, worker, installation, administrative, and other surface types with exact artifact entrypoints or explicit journey steps.
- Added distinct source, static, database, authenticated, browser, device, staging, and production evidence tiers.
- Prevented higher-tier receipts from silently proving lower or adjacent tiers.
- Added immutable evidence-file identity, reviewer, environment, method, expiry, limitations, and exact package binding.
- Preserved PASS, FAIL, BLOCKED, STALE, and NOT_RUN coverage states per surface.
- Integrated compact surface coverage into Adopt, Passport, Resume, Check, Ledger events, and Ship.
- Added cumulative `surface-coverage-mapped-candidate` between package-family identity and native verification.
- Advanced settings to schema 17 without adding a ninth top-level state file.
- Updated canonical progress to 100%, 100%, 99%, 50%, 88%, and 95% — approximately 89% overall.
- Expanded focused public-neutral regressions from 300 to 307.

## 0.531 — Exact Package Family and Delta Applicability

- Added project-owned package-family contracts bound to one active lineage, release version, and build ID.
- Bound each artifact to exact ZIP SHA-256, byte length, normalized tree digest, file count, role, and strip prefix.
- Verified exact child ZIP bytes declared inside outer bundles rather than trusting filenames or stale outer manifests.
- Added deterministic changed-files applicability proof against one exact parent and one exact result artifact.
- Required exact added, modified, deleted, and byte-preserving renamed path declarations plus exact overlay payload bytes.
- Reconstructed the result tree from the parent, deletions, renames, and changed payload and rejected any mismatch.
- Integrated compact package-family state into Adopt, Passport, Resume, Check, Ledger events, and Ship.
- Added cumulative `package-family-identified-candidate` between migration history and native verification.
- Advanced settings to schema 16 without adding a ninth top-level state file.
- Updated canonical progress to 100%, 100%, 97%, 50%, 88%, and 93% — approximately 88% overall.
- Expanded focused public-neutral regressions from 295 to 300.

## 0.530 — Migration Semantic Identity and Reconciliation

- Added exact migration catalogs bound to one active project lineage and exact source tree or ZIP.
- Bound sequence labels to stable semantic IDs, source paths, body SHA-256 digests, byte lengths, engines, and descriptions.
- Added explicit no-migrations declarations instead of filename inference.
- Added applied-ledger states for exact match, sequence-only body uncertainty, direct collision, and not-applied testimony.
- Detected same-number/different-body and same-semantic-ID/different-body histories across lineages.
- Required append-after-highest reconciliation rather than rewriting historical migration bodies.
- Added cumulative `migration-history-identified-candidate` before native verification.
- Advanced settings to schema 15 without adding a ninth top-level state file.
- Updated canonical progress to 100%, 100%, 94%, 50%, 88%, and 90% — approximately 87% overall.
- Expanded focused public-neutral regressions from 288 to 295.

## 0.529 — Exact Project Lineage and Merge-Candidate Quarantine

- Added bounded mtime-independent normalized directory and ZIP tree identities.
- Bound continuation lineage to exact current tree and optional exact parent package/tree identity.
- Required explicit fork or supersession declarations for same-version/different-tree history.
- Added non-mutating merge-candidate quarantine with three-way path inventories and unique-digest rename detection.
- Integrated lineage state into Adopt, Passport, Resume, Check, Ledger events, and Ship.
- Added cumulative `lineage-identified-candidate` before native verification.
- Advanced settings to schema 14 without adding a ninth top-level state file.
- Expanded progress consistency to every duplicate overall percentage field.
- Updated canonical progress to 100%, 100%, 92%, 50%, 82%, and 88% — approximately 85% overall.
- Expanded focused public-neutral regressions from 278 to 288.

## 0.528 — Matched Cold-Session Protocol v2

- Replaced new schema-1 cold-session recordings with schema 2 while preserving legacy records as visible upgrade-required state.
- Separated exact Forge-runtime identity from exact host-release-package identity.
- Bound each counted pair to both digests and byte lengths, immutable task and host-baseline files, provider/model/settings fingerprint, distinct sessions, arm order, reviewer class, and observation time.
- Required explicit same-provider/model/settings/task, isolated-session, exact-runtime, and control-no-Forge declarations.
- Excluded controlled fixtures from human pair, model, task, baseline, scenario, and performance-threshold coverage.
- Added optional external-review minimums, distinct task/baseline coverage, and maximum receipt age.
- Invalidated campaigns after runtime/package drift, expired receipts, changed evidence, or incomplete matched-arm controls.
- Expanded compact Resume and Ship reporting while retaining detailed pair evidence locally.
- Raised cold-session comparative validation from 35% to 50% and the canonical roadmap average from 85% to 87%.
- Preserved settings schema 13, core state schema 3, eight top-level state files, and five public commands.
- Expanded focused public-neutral regressions from 270 to 278.

## 0.527 — Exact-Package Release Authorization and Progress Continuity

- Added a separate project-owned schema-1 authorization for one exact final package and named publication channels.
- Bound authorization to package SHA-256, byte length, build ID, authority source, decision, rationale, conditions, and expiration.
- Added lifecycle invalidation for changed authorization sources, package drift, build drift, expiry, and retirement.
- Required authorization recording to be a separate Adopt operation and prohibited record-and-retire combinations in one operation.
- Added cumulative `owner-release-authorized` before `release-ready`.
- Allowed `release-ready` to PASS only when every cumulative project-declared claim is current, while preserving explicit limitations around identity, competence, universal correctness, and future channel state.
- Advanced settings to schema 13 without adding a ninth top-level state file.
- Restored the six-axis progress report as a canonical tested artifact at 100%, 100%, 95%, 35%, 88%, and 90% — approximately 85% overall.
- Added an automated progress-consistency gate across product metadata, roadmap, planning summary, and packaged status report.
- Removed duplicate CLI parser construction and corrected release-authorization operation hygiene.
- Expanded focused public-neutral regressions from 257 to 270.

## 0.526 — Authority-Bound Baselines and Mutation Quarantine

- Separated canonical observed checkpoints from explicit project-authority baselines.
- Prevented Adopt refreshes from silently advancing an existing observed checkpoint.
- Added separate exact-fingerprint baseline authorization with durable authority, source, and review rationale.
- Kept unexpected mutations quarantined from authority claims after passing scoped Checks and later observed checkpoints.
- Invalidated earlier candidate checkpoints whenever a new authority baseline is recorded and required a fresh passing `Check --checkpoint`.
- Migrated pre-0.526 snapshots as observed-only without inferred authority.
- Added cumulative `authority-recorded-candidate` between `checkpointed-candidate` and `native-verified-candidate`.
- Exposed the complete review fingerprint in human-readable Check output.
- Advanced core state to schema 3 while preserving settings schema 12 and eight top-level state files.
- Expanded focused public-neutral regressions from 247 to 257.
- Kept human identity authentication, file authorship, substantive review quality, sufficient real field evidence, exact-package release authorization, and `release-ready` outside Forge’s claims.

## 0.525 — Bounded Exact-Package Release Proof

- Added project-owned schema-1 Release Proof assurance maps beneath release readiness.
- Required explicit classification of security, privacy, accessibility, compatibility, installation, upgrade, rollback, runtime, and deployment.
- Bound declared release surfaces to exact safe members present in the active final ZIP.
- Required every declared surface to be covered by one or more assurance obligations.
- Added schema-1 receipts bound to exact package digest, bytes, build ID, validity, evidence tier, reviewer requirements, surface scope, and immutable evidence artifacts.
- Preserved missing evidence as `PARTIAL` and treated package mismatch, expiry, drift, malformed receipts, incomplete scope, or unmet independence as `FAIL`.
- Added cumulative `release-proof-validated` before `cold-session-validated`.
- Advanced settings to schema 12 without adding a ninth state file.
- Expanded focused public-neutral regressions from 234 to 247.
- Kept sufficient real field evidence, exact-package owner authorization, and `release-ready` blocked.

## 0.524 — Independent Remote Channel Verification

- Added authority-approved credential-free HTTPS remote verification contracts.
- Restricted live remote retrieval to explicit Ship assessment; Help, Adopt, Resume, and Check remain network-silent.
- Added bounded streamed artifact retrieval with timeout, size budget, exact byte-length, and SHA-256 comparison.
- Constrained redirects to approved HTTPS origins and retained no response body.
- Distinguished remote contradiction from attempted and unattempted blockage.
- Added cumulative `remote-channel-verified` before `cold-session-validated`.
- Corrected documentation to the actual settings schema 11.
- Expanded focused public-neutral regressions from 226 to 234.
- Kept bounded Release Proof and `release-ready` blocked.

## 0.523 — Cross-Model Presentation and Signed Distribution

- Added project-owned cross-model presentation profiles with compact Resume and guided-prompt transfer.
- Added dependency-free RSA PKCS#1 v1.5 SHA-256 verification for exact package and channel-manifest bytes.
- Added signed release-channel manifests and publication receipts bound to exact package and identity.
- Added bounded matched cold-session pair validation tied to the exact Forge runtime.
- Expanded the Ship claim ladder while keeping remote-channel proof, Release Proof, and release-ready blocked.
- Advanced settings to schema 11 without adding a ninth state file.

## 0.522 — Exact Final Package, Confidentiality, and Public Reviews

- Added cumulative `final-package-bound`, `confidentiality-screened`, and `public-release-reviewed` Ship levels.
- Bound one exact ZIP to current owner build identity and current artifact provenance.
- Added bounded archive traversal, encryption, symlink, sensitive-path, private-key, secret-assignment, and owner-declared contamination-term checks.
- Kept owner-declared literal values and scanned archive contents out of Forge state.
- Added exact package/evidence-bound receipts for security, privacy, accessibility, compatibility, installation, upgrade, and rollback reviews.
- Advanced settings schema to 10 while preserving eight top-level state files.
- Expanded focused public-neutral regressions from 205 to 215.
- Updated the standing roadmap to 100%, 100%, 90%, 20%, 88%, and 58%, approximately 76% overall.

## 0.521 — Bounded Ship Claim Levels

- Added cumulative continuity-ready, checkpointed-candidate, native-verified-candidate, runtime-content-verified, persisted-state-assured, and release-ready levels.
- Kept release-ready structurally blocked while exposing the highest lower claim current evidence supports.
- Invalidated checkpointed and higher claims after project changes.
- Required current native evidence plus current known-bad qualification evidence for native verification.
- Required current content-aware HTTP evidence for runtime-content verification.
- Required complete declared transition and rollback evidence for persisted-state assurance.
- Added bounded array allowed-value and cross-collection reference-integrity semantic validators.
- Updated the standing roadmap to 100%, 100%, 90%, 20%, 88%, and 45%, approximately 74% overall.
- Expanded focused regressions from 198 to 205.

## 0.520 — Persisted-State Coverage and Semantic Validation

- Added schema-2 persisted-state transition contracts while retaining schema-1 compatibility.
- Added exact, semantic, and exact-and-semantic state comparison modes.
- Added bounded deterministic JSON validators for paths, values, allowed values, array counts, uniqueness, required fields, and forbidden values.
- Added explicit `all` and `any` coverage requirements across declared transition IDs.
- Made mixed matrices `PARTIAL` and preserved untested transitions as `NOT_RUN`.
- Separated rollback availability, rollback drill execution, and post-rollback state correctness.
- Capped semantic snapshots at 2 MB and kept contents out of routine Forge output.
- Preserved settings schema 9, the five-command interface, eight-file state, and blocked Ship boundary.
- Updated the standing roadmap to 100%, 100%, 90%, 20%, 85%, and 35%, approximately 72% overall.
- Expanded focused public-neutral regressions from 191 to 198.

## 0.519 — Persisted-State Transitions and Bounded Rollback Evidence

- Added authority-recorded state-transition contracts bound to the exact project candidate, baseline, target environment, deployment stage, and verification tier.
- Bound before-state and expected-after-state fixtures, deployment artifact bytes, migration bytes, and same-Check Runtime Proof recipes.
- Added structured owner or external-CI deployment receipts and state-transition testimony.
- Added optional required rollback evidence with restored-state fixtures, rollback receipts, and post-rollback runtime recipes.
- Preserved absent evidence as `NOT_RUN`; stale artifacts, mismatched states, missing required rollback, or changed contracts block Check.
- Kept snapshot contents, receipts, and detailed evidence local while Resume reports compact counts and exceptions.
- Advanced settings schema to 9 while preserving the five-command interface and eight-file state model.
- Updated the standing roadmap to 100%, 100%, 90%, 20%, 75%, and 30% respectively.
- Expanded focused public-neutral regressions from 183 to 191.
- Preserved the blocked Ship boundary: Forge does not deploy, migrate, restore, roll back, inspect semantic data correctness, or certify release readiness.

## 0.518 — Native Invocation Fidelity and Portable Handoff

- Added project-owned exact native invocation contracts for argv, working directory, safe environment, timeout, verification tier, and expected coverage.
- Bound Forge-authorized approval and imported owner/CI evidence to the normalized invocation fingerprint.
- Made zero-exit but incomplete native coverage fail instead of appearing green.
- Added separate private continuity companion export after Session Close, optionally bound to the exact development package.
- Added integrity-checked import into an unadopted project.
- Excluded raw logs, response bodies, credentials, project source, and deployable files from the continuity companion.
- Published the standing six-part roadmap with rough percentages.
- Preserved the five-command interface, settings schema 8, eight-file state model, blocked Ship boundary, and compact Resume.
- Expanded focused public-neutral regressions from 173 to 183.

## 0.517 — Guided Continuation Prompt

- Added one structured, copy-ready next-step prompt to Run Forge output.
- Derived guidance from the confirmed objective, exact next action, blockers, pending decision authority, and continuity state.
- Added explicit stop-before-code behavior for blockers and unconfirmed objectives.
- Preserved authorized native checks, unverified boundaries, and Session Close in the recommended workflow.
- Capped the prompt at 680 characters while retaining detailed evidence locally.
- Preserved the five-command interface, settings schema 8, eight-file state model, and blocked Ship boundary.
- Expanded focused public-neutral regressions from 168 to 173.

## 0.516 — Runtime State and Deployment Matrix

- Added authority-recorded runtime-state matrix contracts.
- Bound scenarios to exact candidate identity fields, baseline, target environment, deployment stage, prior persisted-state identity, and migration-file digests.
- Required structured owner or external-CI testimony plus same-Check Runtime Proof recipes at the declared verification tier.
- Preserved absent evidence as `NOT_RUN` and contradictory evidence as a scoped-Check blocker.
- Required renewed authority after project identity, matrix source, or migration-byte changes.
- Kept database content, credentials, response bodies, and detailed scenario evidence out of routine Resume context.
- Advanced settings schema to 8 and focused regressions from 159 to 168.

## 0.515 — Content-Aware Runtime Proof

- Added a clean-room, contract-gated GET-only Runtime Proof service.
- Required exact origins, status, content type, minimum bytes, required markers, forbidden markers, timeout, and response budgets.
- Rejected liveness-only recipes, credentials, sensitive headers, and cross-origin redirects.
- Discarded response bodies and retained only bounded metadata, digest, truth state, tier, and exclusions.
- Added recipe fingerprint reactivation and compact Resume summaries.
- Expanded focused neutral regressions from 150 to 159.

## 0.514 — Objective Recovery and Native Execution Authority

- Reject redirect-only and truncated objective fragments.
- Follow explicit project-local authority links to the first unfinished ordered roadmap item.
- Add Forge-authorized, owner-only, external-CI, and evidence-import-only native modes.
- Import fingerprint-bound structured owner or CI evidence without claiming Forge execution.
- Represent first adoption as continuity not yet established.
- Prioritize attention by blocker and warning severity.
- Preserve the five-command interface, eight-file state, and compact Resume.
- Expand focused regressions to 150.


## 0.513 — Confirmed Relationship-Aware Change

- Added project-owned confirmed relationship sets for entrypoint includes, imports, behavior bindings, resource consumers, decision-to-path links, migration effects, and test coverage.
- Scoped Check expands affected surfaces, impact dimensions, and required checks only through current authority-recorded relationships.
- Related paths remain distinct from authoritative changed paths.
- Added directional propagation, missing-endpoint blocking, contract-currency lifecycle, compact Resume counts, settings schema 7, neutral documentation, and nine focused regressions.
- Ship remains blocked; relationship records do not prove runtime reachability, behavioral correctness, complete dependency coverage, or deletion safety.

## 0.510 — Active Ledger Assertions and Check Qualification

- Added authority-recorded deterministic Ledger assertions for decisions, resolved defects, guardrails, release rules, and project rules.
- Added path, file-content, JSON-value, and ZIP-membership predicates without arbitrary command execution.
- Regressed trusted claims now reopen as scoped-Check blockers.
- Added fingerprint-bound check qualification using current detector source and immutable known-bad evidence.
- Native checks now remain explicitly qualified, unqualified, or stale separately from their observed result.
- Added compact assertion and qualification Resume summaries to conserve tokens.
- Advanced settings schema to 4 while preserving the eight-file first-contact state.
- Expanded focused public-neutral regressions from 98 to 110.

## 0.509 — Project Identity, Expiring Guardrails, and Shared Lifecycle

- Added one owner-controlled multi-component identity registry with immutable build ID, release train, nullable absent components, component contract versions, baseline, and monotonic values.
- Rejected monotonic identifier rollback after authority records a value.
- Added an optional exact identity-literal scan bounded by project-owned paths, exceptions, and file limits.
- Added `event-obligation` guardrails that remain dormant until an authority-confirmed project event closes a temporary change window.
- Missing obligated surfaces block Check after event closure; complete declared path coverage still requires authority review before retirement.
- Added project-event confirmation through Adopt with project-owned evidence.
- Normalized fingerprint-bound lifecycle meaning across identity, capabilities, guardrails, field trials, and native-gate approval.
- Migrated settings to schema 3 without adding a ninth top-level Forge state file.
- Kept full component, monotonic, event, and lifecycle detail local while Resume exposes only a compact identity and obligation summary.
- Expanded focused active-core regressions from 88 to 98.

## 0.508 — Truth-State Semantics and Forge Self-Currency

- Added bounded `OBSERVED`, `CONFIRMED`, `INFERRED`, `UNKNOWN`, `NOT_RUN`, `BLOCKED_ATTEMPTED`, `BLOCKED_UNATTEMPTED`, `STALE`, and `CONTRADICTED` truth states.
- Added static, sandbox, headless, emulator, development-device, staging, and production verification tiers.
- Native gates that were not requested remain `NOT_RUN`; missing approval or commands are blocked without an attempt; launch failures and timeouts are blocked after an attempt.
- Structured native markers can declare a verification tier, retained with attempted state and raw evidence references.
- Added Forge self-currency checks for objective sources, running Forge version, native-gate source, fingerprint-bound approval, and evidence freshness.
- Kept absent optional native tooling visible but non-noisy.
- Added compact Resume truth summaries and Session Close preservation of unresolved evidence.
- Preserved the five-command interface, eight-file state, token-conservative layered Resume, state integrity, Doctor, guardrails, and blocked Ship.
- Expanded focused active-core regressions from 80 to 88.

## 0.507 — Forge Presence and State Integrity

- Added structured `ai_notice` output with stable IDs, four levels, three visibility modes, exact summaries, and repeat suppression.
- Human CLI output now appends at most one concise `Forge — …` interaction receipt when Forge learns, checks, preserves, warns, or blocks meaningfully.
- Malformed JSON state now blocks operation and remains unchanged; JSONL recovery preserves valid object records and reports damaged line numbers.
- Added cross-platform project operation locking and rollback across all eight top-level continuity files.
- Added synchronized durable JSON, text, and JSONL writes.
- Added explicit schema-1 to schema-2 settings/state migrations and typed state-shape validation.
- Added hash-chained Ledger events and tamper detection.
- Added knowledge deltas and support staleness to Passport and Resume.
- Split CLI handlers and decomposed the monolithic regression suite by subsystem.
- Added subprocess CLI, corruption, rollback, schema, notice, Ledger-integrity, `.forgeignore`, symlink, and Session Close preflight regressions.
- Added project-owned `.forgeignore`, skipped symlinked source paths, and added Session Close internal-consistency preflight.
- Preserved the five-command interface, eight-file first-contact state, contract-gated Doctor, Atomic Safety Guardrails, field-validation infrastructure, and blocked Ship.
- Expanded focused active-core regressions from 62 to 80.

## 0.506 — Field Validation Infrastructure

- Added project-owned schema-1 field-trial contracts with authority, rationale, project profile, model labels, scenarios, ground-truth paths, measures, minimum observations, and truth boundary.
- Added field-trial recording and retirement through Adopt without adding a command or top-level state file.
- Added human- or controlled-fixture field observations linked to explicit Session Close events.
- Added project-local objective/authority correct rates, score and timing summaries, native-evidence-ingestion outcomes, and Doctor/guardrail confusion matrices.
- Rejects duplicate observation IDs, undeclared models or scenarios, retired trials, and changed or missing trial contracts.
- Resume now reports active field-trial samples and keeps their findings explicitly local and non-causal.
- Preserved Atomic Safety Guardrails, Doctor, decision, telemetry, native-gate, continuity, scoped-Check, and blocked-Ship behavior.
- Expanded focused active-core regressions from 55 to 62.

## 0.505 — Atomic Safety Guardrails

- Added project-owned schema-1 atomic guardrail contracts with authority, rationale, evidence paths, trigger paths, required surfaces, unsafe partial-state explanation, and exact verification boundary.
- Added explicit guardrail recording and retirement through Adopt without adding a public command.
- Added automatic guardrail evaluation during ordinary Check against the authoritative adopted-snapshot change set.
- Partial guarded work now blocks PASS and names the missing required surfaces.
- Unrelated changes remain unaffected.
- A complete declared surface set may pass atomicity while remaining explicitly excluded from feature-correctness or completion claims.
- Changed or missing guardrail contracts require renewed authority before related work continues.
- Resume now carries active guardrails and their safety boundaries across AI sessions.
- Preserved Doctor, decision, telemetry, native-gate, continuity, scoped-Check, and blocked-Ship behavior.
- Expanded focused active-core regressions from 50 to 55.

## 0.503 — Interaction and Token Telemetry

- Added truth-labeled local telemetry for observed facts, exact provider reports, and heuristic estimates.
- Added exact provider input/output token capture through Session Close with required provider identity.
- Added observed retry, correction, and assistant-output character counts.
- Added current continuity-record and evidence-record reuse counts to Resume.
- Added first-Adopt initialization overhead and conservative efficiency summaries.
- Added matched `with-forge` and `without-forge` benchmark arms.
- Required at least three matched exact-provider pairs before an in-sample break-even finding.
- Added explicit small one-off task warnings when overhead may exceed benefit.
- Prohibited workspace-byte or character estimates from being presented as actual provider-token savings.
- Preserved the five-command interface, eight-file first-contact state, decision governance, authoritative scoped Check, and blocked Ship boundary.
- Expanded focused active-core regressions from 36 to 44.

## 0.502 — Decision Forks and Cross-Model Consistency

- Added bounded pre-implementation detection for date-only versus exact-time deadline requirements.
- Added constraint, option, implication, recommendation, evidence, and required-authority output.
- Added owner-authorized fork resolution through Adopt without adding a sixth public command.
- Persisted accepted and rejected options, rationale, authority, and evidence in the append-only Ledger.
- Added model-neutral governing decision context to layered Resume packets.
- Added contradiction warnings when changed work appears to violate a confirmed decision.
- Added a neutral regression fixture derived from the deadline-precision architectural fork.
- Preserved the five-command interface, eight-file first-contact state, authoritative scoped Check, and blocked Ship boundary.
- Expanded focused active-core regressions from 30 to 36.

## 0.501 — Authoritative Change Ledger and Scoped Check

- Made adopted-snapshot reconciliation the sole authoritative source of changed paths.
- Changed externally supplied paths to corroboration-only evidence.
- Added stable change IDs, baseline/current fingerprints, surface classification, impact dimensions, and required-check plans.
- Added documentation, website, application, and no-change Check profiles.
- Added HTML local-asset, CSS structure, and Markdown local-link checks.
- Reordered explicit native verification before Forge-specific checks.
- Added per-record evidence validity and targeted invalidation by affected surface.
- Persisted the current authoritative change record inside existing State and append-only Ledger files.
- Preserved the five-command interface, eight-file first-contact model, durable Session Close, and blocked Ship boundary.
- Expanded focused active-core regressions from 23 to 30.
