# Emotivus Forge 0.572

Forge provides portable, exact project truth and session continuity to AI models. It does not tell capable models how to reason, design, code, or debug.

> **Canonical repository:** `derickonfire/emotivus-forge` is the home of Forge development. New sessions should work out of this repo — see [`CLAUDE.md`](CLAUDE.md) for orientation.

## What 0.572 changes

- **Certifies the Goal-3 (Cross-Model Evolution Kernel) foundation.** The end-to-end replacement round trip passes with real Forge calls (`test_g3_roundtrip`): another instance **migrates** an older package (unknown top-level and nested fields preserved verbatim), **replaces** an obsolete component with a **Forge-verified** invariant, and **emits a compatible continuity package** that a **fresh instance consumes** — restoring all eight state files, the preserved unknown field, and the recorded replacement. Exact meaning survives the round trip.
- Every clause of the G3 completion rule is delivered and adversarially tested (a 12-agent field test found and closed two over-assertions in 0.570); the evidence is inventoried in `planning/G3-COMPLETION.md`.
- The roadmap moves **G3 from FOUNDATION_ACTIVE to CONTINUOUS** — the foundation is certified and G3 now remains continuous by design (new instruments require an observed miss + scored trial). **G1 is COMPLETE, G3's foundation is certified; G2 is the one remaining open goal.**
- Honest boundary: certification is of the evolution *foundation* — not of any specific release. Release authorization remains **false**; Forge preserves and reports unrecognized fields without interpreting them, and verifies declared invariants without claiming a successor is correct.
- Certified suite grows additively to **546 focused public-neutral regressions across 58 deterministic isolated modules** (new `test_g3_roundtrip`).
- Preserves the four-page website design and active generator.

## Current verification target

**546/546** focused public-neutral regressions across 58 deterministic isolated modules.

This count is package metadata until exact final-byte certification completes. It is not release authorization or proof of efficacy.

## Normal use

Say **Run Forge**. Forge identifies the project state and supplies verified context. The AI model remains responsible for reasoning and development.
