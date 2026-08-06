# Forge — Development Roadmap

*How the next releases actually get built.* This is the executable companion to the
strategic `ROADMAP-2029.md` and the sealed chunk ledger in `ROADMAP.md`. It names
concrete milestones, the files each one touches, and the gate that closes it.

Ground rules discovered from the codebase, treated as law here:

- **Forge governs its own releases.** A version bump is one coherent, self-checked
  operation across seven coupled surfaces: `FORGE-PRODUCT.json`,
  `FORGE-MANIFEST.json`, `CHANGELOG.md`, `PROGRESS-STATUS.md`, `ROADMAP.md`,
  `README.md`, `CERTIFICATION.md`, plus `emotivus_forge/__init__.py` and the
  `check_progress` active-chunk expectation. `narrative_integrity` +
  `check_progress` fail loudly if any drift.
- **Folds precede deletions.** No module is removed until a fold makes it
  unreachable *and* behavior + history are proven preserved. Reachability alone is
  never deletion authority (F-552-004).
- **New instruments require an observed miss.** An expansion needs a recorded miss,
  declared ground truth, a bounded implementation, and a scored trial — never a
  hunch (the expansion rule).
- **The refusal is inviolable.** Nothing may let `NOT_RUN` become `PASS` or infer
  authority/readiness from lower evidence. Every milestone's gate re-checks this.
- **Definition of done, every milestone:** full suite green (currently 523/523
  across 54 modules), `narrative_integrity` PASS, `check_progress` PASS, live
  `python3 forge.py` Brief coherent, release authorization still `false` until the
  goal gate that earns it.

---

## The development loop (per milestone)

1. **Record the miss / objective** in `planning/<version>-OBJECTIVE.md`.
2. **Build the smallest bounded change** behind the existing public surface.
3. **Add focused regressions** in `tests/` (one isolated module per concern).
4. **Fold, then remove** — never remove first.
5. **Bump the version in lockstep** across the seven surfaces + `__init__` +
   `check_progress`, and regenerate the site from `build_site.py`.
6. **Re-verify** the full green gate above, and record `planning/<version>-FINDINGS.md`.
7. **Seal** the release; update `CHANGELOG.md` and the `docs-site` release notes.

---

## Actual trajectory vs. the plan (0.558 correction)

The milestone sequence below is the *original* plan. Reality diverged, and this
roadmap records it honestly rather than pretending it went to script:

- **M0–M2 (0.553–0.555) landed** roughly as planned: reorient, fold overlapping
  services, reduce and re-boundary. Phase A is complete.
- **0.556–0.558 did not build M4's G1 proof.** That budget went to the *on-ramp*
  instead — the context digest, the trustworthy first-contact Brief, description
  and layout hygiene, and the ranked ecosystem resolver (the "project
  intelligence" redirect, driven by an observed miss and multi-agent field tests).
  This work is sound and stays. But it advanced **G2 approachability and the
  token-conservation selling point, not the hard core of G1.**
- **Consequence:** the `M4 · Prove Goal 1` work is still owed in full. `P2-01`
  remains merely *active*; no adversarial gate has been earned; release
  authorization is honestly still `false`.

**Re-prioritized next milestone — the G1 provable-truth core moves to the front.**
Before it starts, run a G1-aimed field test (record where a model can push Forge
into asserting something it hasn't proven) so the build begins from recorded
observed misses, per the expansion rule. Token conservation is not a milestone; it
is a demonstrable byproduct of trustworthy truth and stays as on-ramp, not spine.

## Milestone sequence

### M0 · 0.553 — Reorient (this cycle) · **staged**
- **Goal:** inherit and re-point Forge for the 2029 horizon without breaking truth.
- **Done here:** certified 0.552 base adopted and re-verified; 2029 verdict +
  forward roadmap added; lineage recorded; `F-553-001` (VCS metadata
  classification) landed; website copy re-pointed to the trust-layer model with
  design retained.
- **Remaining to close 0.553:** perform the lockstep 0.552→0.553 version bump and
  land sealed chunk **P1-03** (relocate explanatory-only docs into `reference/`,
  updating the manifest, reachability map, and self-checks together).
- **Gate:** green gate + `check_progress` active chunk advances from `P1-03` to
  `P1-04`.

### M1 · 0.554 — Fold the overlapping services (Phase A core)
- **Goal:** collapse duplication so Forge is small enough to trust and cheap enough
  to call. Sealed chunks **P1-04 … P1-05**.
- **Build:** fold overlapping release / evidence / rollback / authority services
  into the one project-truth boundary; replace capability-activation ceremony with
  a uniform `enabled / reason / scope / evidence` record where safety still needs
  it. Collapse the dozens of `adopt --record-*/--retire-*` flags behind that record.
- **Files:** `emotivus_forge/core/{release_*,evidence_*,authority_*,capabilities}.py`,
  `emotivus_forge/commands/adopt.py`, `emotivus_forge/cli.py`; retire ceremony-only
  tests, keep behavior tests.
- **Gate:** same guarantees, materially fewer flags/modules, every folded behavior
  still covered by a retained regression.

### M2 · 0.555 — Reduce and re-boundary (Phase A close)
- **Goal:** sealed chunks **P1-06 … P1-07**. Remove only modules made unreachable
  by a completed fold; rebuild the public/development boundary; prove no retained
  behavior or history was lost.
- **Build:** run the reachability map after folds; delete now-dead modules with an
  explicit fold citation each; regenerate public vs development editions.
- **Gate:** reachability shows the removed modules were fold-orphaned (not merely
  unobserved); diff of behavior tests is subtraction-of-ceremony only; history
  preserved in `reference/`.

### M3 · 0.556 — Agent-native invocation spike (Phase B) · *the future-proofing bet*
- **Goal:** turn "Run Forge" into a capability agents **call**, per the recorded
  miss `F-553-003`.
- **Build:** a thin, deterministic agent/MCP surface (`forge.run`, `forge.check`,
  `forge.ship`, `forge.adopt`, `forge.resume`) that wraps the existing `--json`
  command paths and returns the *same* structured payloads. CLI stays primary; the
  tool is a wrapper, not a fork.
- **Files:** new `emotivus_forge/agent/` (server + contract), reuse of
  `commands/public.py` payloads; new `tests/test_agent_surface.py`.
- **Gate (parity + safety):** the tool path and CLI path yield byte-identical truth
  records; the tool **cannot** ship, escalate authority, or upgrade `NOT_RUN` to
  `PASS`; transcript fields still rejected and not retained. Ship a scored
  cold-agent trial as the evidence, not a claim.

### M4 · 0.557–0.558 — Prove Goal 1 (Phase C)
- **Goal:** make Provable Project Truth adversarially earned. Sealed chunks
  **P2-01 … P2-09**.
- **Build:** consolidate the project-truth schema and migrate the legacy eight-state
  form; bind evidence, browser pixels, and owner authorization to one exact
  package; run wrong-package / same-version-collision / tampering / stale-evidence
  trials.
- **Gate:** **G1 → COMPLETE** only if every adversarial gate passes twice from
  independent bytes. This is the first milestone allowed to change a goal to a
  binary COMPLETE.

### M5 · 0.559–0.560 — Prove Goal 2 (Phase C close)
- **Goal:** one-command continuity, scored. Sealed chunks **P3-01 … P3-09**.
- **Build:** one deterministic state classifier behind Run Forge routing new /
  unchanged / changed / close / release-candidate states into a single coherent
  Brief; detect session-close and release-candidate intent without auto-shipping.
- **Gate:** **G2 → COMPLETE** only after the scored cold-trial acceptance,
  including one cross-vendor hand-off (a model of a different vendor enters, works,
  and hands off with zero invented authority).

### M6 · 0.561–0.562 — Federate (Phase D, then continuous)
- **Goal:** an evolution kernel that outlives any single model. Sealed chunks
  **P4-01 … P4-08**.
- **Build:** a vendor-neutral kernel storing truth (not model instructions) with
  forward-migration that preserves unknown fields; explicit
  retain/fold/freeze/retire/replace lifecycle records; a future-model replacement
  trial against an older sealed package; a second-provider round trip.
- **Gate:** the foundation is **certified**, then **G3 stays continuous** — Forge
  keeps proving it can be carried forward and never claims a false "done."

---

## What "finished" means

Forge is finished when a person or an agent, on any project, with any model, says
two words — **Run Forge** — and gets one honest Brief: what is true, who authorized
it, what changed, what the evidence shows, and the one exact next action; when G1
and G2 are COMPLETE on adversarial evidence; and when G3 has a certified foundation
that a model newer than this one can carry forward. Not a bigger tool. A smaller,
harder-to-fool one.

The test of "finished" is the spine, not the selling point: a model must be
**unable to make Forge assert something it hasn't proven**. Cheap first contact
(token conservation) is how models are drawn to use it; being impossible to fool is
why they should trust it. If we ever have to choose, the second wins.

*The certified 0.552 base is preserved; every milestone advances through Forge's
own governed release loop.*
