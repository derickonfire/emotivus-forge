# Forge — Forward Roadmap (2029 Horizon)

**Companion to the sealed operational roadmap in `ROADMAP.md`.**
`ROADMAP.md` is the certified 0.552 chunk ledger and stays authoritative for the
active core-reduction phase. This file is the *strategic* layer above it: where
Forge is going over the next three years, and why. The verdict behind it is in
`FORGE-2029-VERDICT.md`.

**Normal invocation:** `Run Forge` · **Planning unit:** one focused 8–20 min chunk
· **Percentages:** retired. Progress is reported as completed outcomes, current
chunk, catches, misses, false positives, and unavailable evidence — never one
averaged number.

---

## The product boundary (non-negotiable)

Forge works **with** models. It supplies exact identity, authority, lineage,
changes, evidence, and portable continuity. The model owns reasoning, design,
coding, debugging, and communication. **Forge must never become a coding agent, a
prompt governor, or a substitute for model intelligence.** Every chunk below is
tested against this line; anything that crosses it is rejected regardless of how
useful it seems.

## The three durable goals (evolved)

| Goal | What it means in 2029 | Completion rule |
|---|---|---|
| **G1 · Provable Project Truth** | The deterministic oracle a hallucinating model can't argue with: exact identity, authority, lineage, evidence — and the refusal to promote `NOT_RUN` to `PASS`. | Adversarial package rejection, exact-byte verification, and authorization all pass from independently verified bytes. Binary COMPLETE. |
| **G2 · One-Command Continuity** | A cold model — *of any vendor* — enters and leaves via `Run Forge` with no workflow commands, no repeated work, no invented authority. | Scored cold-trial acceptance across new / unchanged / changed / conflicting / close / release-candidate states, including a cross-vendor hand-off. Binary COMPLETE. |
| **G3 · Cross-Model Evolution Kernel** | A vendor-neutral store of *truth, not instructions*, that survives model and vendor changes, migrates old packages forward, and preserves unknown fields. | A different model/vendor migrates an older package, preserves exact meaning, replaces an obsolete component, and emits a compatible continuity package. Foundation certifiable, then **continuous by design** — never falsely "complete." |

G1 and G2 reach a binary COMPLETE. G3 is a foundation that then stays alive.

## The four strategic phases

The sealed `ROADMAP.md` runs the near-term chunks (P0 reset → P1 core reduction →
P2 Goal 1 → P3 Goal 2 → P4 Goal 3). This forward view groups the *intent* of that
work into four phases and names the one thing this horizon adds that the sealed
roadmap does not yet: agent-native invocation.

### Phase A — REDUCE (now → 0.553+) · *shed the ceremony*
Goal: make Forge small enough to be trusted and cheap enough to be called.
- Move historical / explanatory docs out of required reading into `reference/`. *(sealed P1-03, active)*
- Fold overlapping release, evidence, rollback, and authority services into the one project-truth boundary. *(P1-04)*
- Replace capability-activation ceremony with a minimal `enabled / reason / scope / evidence` record where safety still requires it. *(P1-05)*
- Remove only modules made unreachable by a completed fold; retire tests that verify removed ceremony, not retained behavior. *(P1-06)*
- Rebuild the public/development boundary and prove no retained behavior or history was lost. *(P1-07)*
- **Exit criterion:** the same guarantees, materially fewer modules and flags, 100% behavior-and-history preservation proven.

### Phase B — INTEGRATE (the future-proofing move) · *make "Run Forge" agent-native*
Goal: turn "Run Forge" from a command a human types into a capability an agent
*calls*. This is the single highest-leverage bet for 2029 relevance and is **new
to this horizon** — it does not yet exist in the sealed roadmap.
- Expose the five public commands as a small, deterministic **agent tool / MCP
  surface** (`forge.run`, `forge.check`, `forge.ship`, …) returning the same
  structured JSON the CLI already produces. The CLI stays; the tool wraps it.
- Define a stable machine contract: one structured Brief in, one structured
  hand-off out, transcript fields still rejected and not retained.
- Prove parity: the tool path and the CLI path yield byte-identical truth records.
- **Exit criterion:** a mainstream agent harness can `Run Forge` with no human in
  the loop and receive the exact same governed truth a human would, and cannot use
  the tool to escalate authority, ship, or upgrade `NOT_RUN` to `PASS`.

### Phase C — PROVE (Goals 1 & 2 to COMPLETE) · *earn the trust claim*
Goal: make the trust claim adversarially earned, not asserted.
- Consolidate the project-truth schema and migrate the legacy eight-state form. *(P2-01…04)*
- Bind evidence, browser pixels, and owner authorization to one exact package. *(P2-05…07)*
- Run adversarial wrong-package, same-version-collision, tampering, and stale-evidence trials; declare **G1 COMPLETE** only if every gate passes twice from independent bytes. *(P2-08…09)*
- Ship one deterministic state classifier behind `Run Forge`; route new/unchanged/changed/close/release-candidate states correctly; run the cold trials and the cross-vendor hand-off; declare **G2 COMPLETE** only after the scored gate. *(P3-01…09)*
- **Exit criterion:** G1 and G2 both COMPLETE, on evidence, with the classifier driving one coherent Brief instead of lifecycle ceremony.

### Phase D — FEDERATE (Goal 3, continuous) · *outlive any single model*
Goal: a continuity kernel that a 2029 model, of a vendor that may not exist yet,
can still read, migrate, and extend.
- A vendor-neutral kernel that stores truth rather than model instructions, and
  preserves unknown fields through forward migration. *(P4-01…02)*
- Explicit retain / fold / freeze / retire / replace lifecycle records. *(P4-03)*
- The expansion rule as law: a new instrument requires an *observed miss*, declared
  ground truth, a bounded implementation, and a scored trial — never a hunch. *(P4-04)*
- Let newer models propose simplifications while Forge verifies preserved
  invariants; run a future-model replacement trial against an older sealed package;
  run a second-provider round trip and compare exact preserved truth. *(P4-05…07)*
- **Exit criterion:** the evolution foundation is certified, then G3 stays
  continuous — Forge keeps proving it can be carried forward, and never claims a
  false "done."

## What 0.553 actually is

0.553 is the **first chunk of Phase A executed under the 2029 thesis**, plus the
groundwork this reorganization already laid. Concretely, the sealed roadmap's next
active chunk is **P1-03** (move historical/explanatory docs out of required
reading). Around it, 0.553 should:

1. Land P1-03: introduce `reference/` and relocate explanatory-only docs, updating
   the manifest, reachability map, and self-checks in lockstep.
2. Record the version bump 0.552 → 0.553 consistently across `FORGE-PRODUCT.json`,
   `FORGE-MANIFEST.json`, `CHANGELOG.md`, `PROGRESS-STATUS.md`, `ROADMAP.md`,
   `README.md`, and `CERTIFICATION.md`, and update `check_progress`'s expected
   active chunk. (These are coupled by design — Forge governs its own release.)
3. Fold `F-553-001` (see `planning/0.553-FINDINGS.md`) into the certified record:
   the reachability mapper now classifies version-control metadata.
4. Open the Phase B spike as a *planning* item (agent-native invocation contract)
   without shipping it yet — an observed miss must be recorded first, per the
   expansion rule.

## The one-command future

Everything above collapses back to a single promise. In 2029, on any project, with
any model, a human or an agent says two words —

> **Run Forge.**

— and receives one honest Brief: what is true, who authorized it, what changed,
what the evidence actually shows, and the one exact next action. No ceremony, no
invented certainty, no lost history. That is the whole roadmap.

---

*This forward roadmap sits above the sealed 0.552 record and does not alter it.
The certified base is preserved byte-for-byte; direction is set here, executed
through Forge's own governed chunks.*
