# Emotivus Forge — Durable Core Roadmap

**Current release:** 0.572  
**Legacy percentage roadmap:** RETIRED  
**Normal invocation:** `Run Forge`  
**Planning unit:** one focused 8–20 minute chunk

## Product boundary

Forge works **with** AI models. It provides exact project identity, authority, lineage, changes, evidence, and portable continuity. The model remains responsible for reasoning, design, coding, debugging, and communication. Forge must not grow into a prompt governor, coding agent, or substitute for model intelligence.

## Outcome goals

| Goal | Status | Completion rule |
|---|---|---|
| G1 · Provable Project Truth | **COMPLETE** | Exact identity, authority, lineage, evidence binding, adversarial package rejection, and package authorization all pass from independently verified bytes. Verified in `planning/G1-COMPLETION.md` (0.566). |
| G2 · One-Command Session Continuity | **ACTIVE** | Cold models can enter and leave representative projects using Run Forge without selecting workflow commands, repeating completed work, or inventing authority. |
| G3 · Cross-Model Evolution Kernel | **CONTINUOUS** | The foundation is complete when another model/vendor can migrate an older package, preserve exact meaning, replace an obsolete component, and emit a compatible continuity package. Foundation certified in `planning/G3-COMPLETION.md` (0.572); now continuous by design. |

G1 and G2 must reach a binary **COMPLETE** state. **G1 is COMPLETE as of 0.566** (`planning/G1-COMPLETION.md`); **G3's foundation is CERTIFIED as of 0.572** (`planning/G3-COMPLETION.md`) and now remains continuous by design. **G2 is the remaining open goal.**

## Reconciliation (as of 0.572)

Development from 0.556 onward became **evidence-driven** — adversarial field tests and
a real cross-model collaboration (LineCheck) surfaced the work, rather than the fixed
per-chunk sequence in the table below. The chunk table is kept as the original
structural plan and history; the sections here reconcile it with what actually shipped
and sequence the near term.

### Delivered 0.556 → 0.572 (evidence-driven)

| Release | Goal | Delivered |
|---|---|---|
| 0.556–0.558 | G1/G2 | Project-intelligence orientation; ranked ecosystem/framework resolver; content-scanned secrets; broader identity/test coverage. |
| 0.559 | G1 | Provable-truth core: imported-baseline corroboration vs a chain-verified event; bounded change confidence on un-hashed files; inferred-vs-confirmed labeling. |
| 0.560 | G1 | Honest corroboration boundary: the unkeyed-chain residual named in `TRUTH_BOUNDARY`; Ship bounded phrasing. |
| 0.561 | G2/G3 | **Read-only consultation mode** (`run --read-only`, `resume --read-only`) — advise on a shared/third-party repo with zero footprint. |
| 0.562 | G1/G3 | **Cryptographic instance-binding** (single instance): signed authority events; tri-state corroboration; only instance-bound is release-eligible. Closes the "self-consistent ≠ authentic" residual for authority. |
| 0.563 | G1/G3 | **Multi-party instance-binding**: an owner-provisioned shared collaboration secret makes authorizations mutually instance-bound across enrolled parties. The enforceable basis for cross-model trust. |
| 0.564 | G1/G3 | **Provenance parity**: instance-binding extended to artifact provenance — a deliverable's lineage is asserted `CONFIRMED` only when its recording event is instance-bound. |
| 0.565 | G1 | **Native-evidence source binding**: imported native evidence is bound to the source tree fingerprint and reported stale once the tree changes. Closes the recorded G1 observed-miss backlog. |
| 0.566 | G1 | **Goal 1 certified COMPLETE**: every completion-rule dimension adversarially verified; public package self-tests 533/55 twice from its own bytes (`planning/G1-COMPLETION.md`). |
| 0.567 | G3 | **Forward-compatible migration**: unknown top-level and nested fields preserved verbatim; Forge reports preserved-but-unrecognized fields (`core/forward_compat.py`). |
| 0.568 | G3 | **Vendor-neutral continuity (P4-01)**: the continuity kernel rejects model-instruction and vendor-identity keys on digest intake — it stores project truth, not model instructions. |
| 0.569 | G3 | **Component lifecycle records (P4-03)**: retain/fold/freeze/retire/replace a named component as an append-only, chain-verified ledger event; a replace names its successor and preserved invariants. |
| 0.570 | G3 | **Field-test hardening**: a 12-agent adversarial test closed two over-assertions — lifecycle transitions are now instance-bound (imported ones labeled self-consistent), and the vendor-neutral digest screens free-text values, not only keys. |
| 0.571 | G3 | **Verified replacement invariants (P4-05)**: a replace can declare structured invariant checks that Forge verifies against the scoped-Check truth records, reporting preserved vs violated. |
| 0.572 | G3 | **G3 foundation CERTIFIED**: the end-to-end replacement round trip passes (migrate -> preserve -> replace with verified invariant -> emit compatible package -> consume); G3 moves to CONTINUOUS (`planning/G3-COMPLETION.md`). |

**Standing:** **G1 is COMPLETE (0.566)** and **G3's foundation is CERTIFIED / CONTINUOUS (0.572)** — see `planning/G1-COMPLETION.md`, `planning/G3-COMPLETION.md`. **G2 is the one remaining open goal.** The dominant G1 finding ("self-consistent ≠ authentic") is closed for
**both authority and provenance** (single- and multi-party) — an imported package can
spoof neither authenticated authority nor authenticated provenance. G3 has real substance
now — cross-vendor trust is enforceable, not just prose. G2 gained the zero-footprint
consult path.

### Near-term sequenced queue (supersedes the stale per-chunk targets)

1. **G2 close-out** — the remaining open goal. Cross-vendor cold-entry/exit handoff
   acceptance (new/unchanged/changed/conflicting/close/release-candidate cold trials),
   toward declaring G2 COMPLETE.

2. **Gate-diff monotonicity** *(candidate — miss recorded, instrument not built)* —
   certify that a change to a project's gate/check scripts removed no assertion,
   lowered no threshold, and introduced no SKIP path. LineCheck surfaced the miss
   twice (`planning/OBSERVED-MISS-gate-diff-monotonicity.md`). Needs a scored trial
   (real schema-pin commit → CONFIRMED, synthetic assertion-removal → CONTRADICTED)
   before it enters the durable core.

3. **Gate-coverage differ** *(DELIVERED 0.575)* — reports the checks that exist in a
   tree but are not invoked by its CI gate, so a green gate can't read as "covered"
   while silently omitting assertions; detects glob/loop invocation and returns
   NOT_RUN rather than false gaps. `core/gate_coverage.py` +
   `tools/report_gate_coverage.py`. Scored trial passed: replayed against LineCheck
   `6188585`, surfaced `check_worklist_behavior.php` + 5 sibling behaviour checks as
   not-gate-wired (`planning/OBSERVED-MISS-gate-coverage-differ.md`).

   *(2 is a LineCheck-surfaced G1 candidate folded here per the "miss + trial before
   instrument" rule; 3 was delivered this cycle. Both follow the delivered
   source-anchored release verification (0.575) in the same truth-anchoring family —
   authority, provenance, native-evidence, release-schema, and now gate coverage are
   the anchored G1 truth surfaces.)*

*G3 foundation CERTIFIED (0.572) and now CONTINUOUS — the end-to-end round trip passes
(`planning/G3-COMPLETION.md`); new G3 instruments require an observed miss + scored trial.*

*Done: the full recorded G1 observed-miss backlog — native-evidence source binding (0.565),
provenance parity (0.564), single- and multi-party instance-binding (0.562–0.563), read-only
consult (0.561). DG-7 was reviewed and did not survive verification (no speculative fix).*

### LineCheck collaboration (live validation track)

Forge participates in the Claude × ChatGPT collaboration on `linecheck-acceptance` under a
strict, advisory, read-only bound (see `exchange/`). This is Forge's real-world G2/G3
validation: read-only consult (0.561) and instance-binding (0.562–0.563) are the two
capabilities it contributes. The collaboration is a source of observed misses, not a driver
of scope creep. Forge never gates LineCheck.

**Observed miss → G1 instrument (0.575).** The LC-004 Phase E schema bump twice declared
the release *accepted* at a schema its accepted source never shipped, with the public
surfaces rewritten to match — a lie every internal-consistency gate passed **green**
(`planning/OBSERVED-MISS-source-anchored-release.md`). `release_facts` compares declared
fields to each other; it cannot anchor to the accepted source. New G1 instrument
**source-anchored release verification** (`core/source_anchored_release.py`,
`tools/bind_release_truth.py`) derives the true accepted schema from the exact accepted
source commit's code and binds the declared release-state and public surfaces to it,
`NOT_RUN` when the anchor is unreachable. Validated against real history (CONFIRMED at the
honest head, CONTRADICTED at the false one). Branch `claude/g1-source-anchored-release`;
owner sealing pending. The single flag Forge raised across the engagement was this exact
boundary — the roadmap thesis (bind fragile fact-shaped claims a green gate can't, then
graduate the check) in one concrete case.

## Roadmap chunks

*Original structural plan and history. The per-chunk **Target** versions predate the
evidence-driven track above and are no longer the live sequence; see the near-term queue.*


| Chunk | Phase | Timebox | Target | Status | Work |
|---|---|---:|---|---|---|
| P0-01 | Reset | 8–12 min | 0.551 | **COMPLETE** | Seal 0.549 as the last legacy-roadmap authority and preserve its exact artifacts. |
| P0-02 | Reset | 8–10 min | 0.551 | **COMPLETE** | Classify the incomplete 0.550 outputs as experimental and never promote them as a certified release. |
| P0-03 | Reset | 10–15 min | 0.551 | **COMPLETE** | Retire the seven-axis percentage roadmap and replace it with three outcome goals. |
| P0-04 | Reset | 8–12 min | 0.551 | **COMPLETE** | Write the AI-collaboration boundary: provide verified context; do not prescribe model reasoning. |
| P0-05 | Reset | 15–20 min | 0.551 | **COMPLETE** | Reduce the public website to four pages while preserving its design assets and generator. |
| P0-06 | Reset | 12–18 min | 0.551 | **COMPLETE** | Create the durable-core inventory and classify active, folded, frozen, reference, and removable surfaces. |
| P0-07 | Reset | 15–20 min | 0.551 | **COMPLETE** | Synchronize product metadata, tests, release notes, website, and continuity records. |
| P0-08 | Reset | 15–20 min | 0.551 | **COMPLETE** | Certify and seal the complete 0.551 delivery from exact final bytes. |
| P1-01 | Core reduction | 12–18 min | 0.552 | **COMPLETE** | Generate an import and command reachability map for the active runtime. |
| P1-02 | Core reduction | 10–15 min | 0.552 | **COMPLETE** | Map every active top-level path to G1, G2, G3, web documentation, testing, packaging, or migration. |
| P1-03 | Core reduction | 15–20 min | 0.553 | **COMPLETE** | Move historical and explanatory-only documents from active docs into reference/history (`docs/history/`). |
| P1-04 | Core reduction | 15–20 min | 0.554 | **COMPLETE** | Fold overlapping release, evidence, rollback, and authority services into the project-truth boundary (deterministic plumbing + kit hygiene folded; distinct-by-design services kept). |
| P1-05 | Core reduction | 12–18 min | 0.554 | **COMPLETE** | Replace capability activation ceremony with a minimal enabled/reason/scope/evidence record where safety still requires it. |
| P1-06 | Core reduction | 15–20 min | 0.555 | **COMPLETE** | Remove only modules made unreachable by completed folds, and retire tests that verify removed ceremony rather than retained behavior (fold-orphaned imports retired; no module orphaned; no ceremony test existed). |
| P1-07 | Core reduction | 15–20 min | 0.555 | **COMPLETE** | Rebuild public/development boundaries and prove no retained behavior or history was lost (public edition passes 523/54 from its own bytes; git + docs/history preserve all history). |
| P2-01 | Goal 1 | 15–20 min | 0.556 | **ACTIVE** | Define the minimal project-truth schema and migration from the legacy eight-state representation. |
| P2-02 | Goal 1 | 12–18 min | 0.553 | **QUEUED** | Consolidate file, tree, package, edition, and embedded-runtime identity. |
| P2-03 | Goal 1 | 12–18 min | 0.553 | **QUEUED** | Consolidate owner authority, exact baseline, and NOT_RUN-before-authority semantics. |
| P2-04 | Goal 1 | 15–20 min | 0.553 | **QUEUED** | Consolidate parent, fork, supersession, collision, and quarantine lineage. |
| P2-05 | Goal 1 | 15–20 min | 0.554 | **QUEUED** | Consolidate exact evidence binding, returned receipt intake, and conflict lifecycle. |
| P2-06 | Goal 1 | 12–18 min | 0.554 | **QUEUED** | Retain browser pixels, DOM, overflow, and resource identity as package-bound evidence. |
| P2-07 | Goal 1 | 15–20 min | 0.554 | **QUEUED** | Bind owner authorization to one exact package while keeping human identity and legal authority explicit. |
| P2-08 | Goal 1 | 15–20 min | 0.566 | **COMPLETE** | Adversarial wrong-package, same-version collision, tampering, and stale-evidence trials pass; coverage inventoried in `planning/G1-COMPLETION.md`. |
| P2-09 | Goal 1 | 15–20 min | 0.566 | **COMPLETE** | Public package passes 533/55 twice deterministically from its own extracted bytes; G1 declared COMPLETE. |
| P3-01 | Goal 2 | 15–20 min | 0.556 | **QUEUED** | Implement one deterministic state classifier behind Run Forge. |
| P3-02 | Goal 2 | 12–18 min | 0.556 | **QUEUED** | Route new projects to adopt-and-orient without requiring the user to know Adopt. |
| P3-03 | Goal 2 | 8–12 min | 0.556 | **QUEUED** | Route unchanged projects to compact Resume only. |
| P3-04 | Goal 2 | 12–18 min | 0.557 | **QUEUED** | Route changed projects to scoped checks plus refreshed continuity. |
| P3-05 | Goal 2 | 15–20 min | 0.557 | **QUEUED** | Detect session-close intent and produce the handoff, continuity export, and exact next action. |
| P3-06 | Goal 2 | 12–18 min | 0.557 | **QUEUED** | Detect release candidates without automatically shipping or authorizing them. |
| P3-07 | Goal 2 | 12–18 min | 0.558 | **QUEUED** | Replace verbose recommended prompts with structured state and one resolving question only when ambiguity is real. |
| P3-08 | Goal 2 | 15–20 min | 0.558 | **QUEUED** | Run new, unchanged, changed, conflicting, close, and release-candidate cold trials. |
| P3-09 | Goal 2 | 15–20 min | 0.559 | **QUEUED** | Run one cross-vendor handoff and declare G2 COMPLETE only after the scored acceptance gate. |
| P4-01 | Goal 3 | 15–20 min | 0.560 | **QUEUED** | Define a vendor-neutral continuity kernel that stores truth rather than model instructions. |
| P4-02 | Goal 3 | 12–18 min | 0.560 | **QUEUED** | Preserve unknown fields and historical meaning through forward migrations. |
| P4-03 | Goal 3 | 12–18 min | 0.560 | **QUEUED** | Create explicit retain, fold, freeze, retire, and replace lifecycle records. |
| P4-04 | Goal 3 | 10–15 min | 0.561 | **QUEUED** | Require an observed miss and scored trial before adding any new instrument. |
| P4-05 | Goal 3 | 12–18 min | 0.561 | **QUEUED** | Allow newer models to propose simplifications while Forge verifies preserved invariants. |
| P4-06 | Goal 3 | 15–20 min | 0.561 | **QUEUED** | Run a future-model replacement trial against an older sealed Forge package. |
| P4-07 | Goal 3 | 15–20 min | 0.562 | **QUEUED** | Run a second-provider continuity round trip and compare exact preserved truth. |
| P4-08 | Goal 3 | 15–20 min | 0.562 | **QUEUED** | Certify the evolution foundation, then keep G3 continuous rather than falsely complete. |

## Reachability finding from 0.552

- 88 active runtime modules were inventoried.
- 88 are reachable when ordinary CLI, standalone evidence tools, and verification entry points are considered together.
- All six public/no-argument command paths were observed in bounded neutral fixtures.
- Every active top-level path has a declared goal, support role, or reference disposition.
- Static absence from one command path is not deletion authority. P1-03 reduces required documentation first; later module removal must follow completed folds and exact behavior verification.

## Expansion rule

A new active instrument requires an observed miss, declared ground truth, a bounded implementation, and a scored trial. A newer model may simplify or replace assistance-oriented code, but it must preserve exact historical truth, evidence identity, and migration meaning.

## Website rule

The public website has exactly four generated pages: **Home**, **Run Forge**, **Project Truth**, and **Continuity & Evidence**. Downloads remain files, not additional pages. Release history, roadmap status, trust boundaries, documentation, and checksums are consolidated into the four-page information architecture.
