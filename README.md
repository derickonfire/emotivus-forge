# Emotivus Forge 0.565

Forge provides portable, exact project truth and session continuity to AI models. It does not tell capable models how to reason, design, code, or debug.

> **Canonical repository:** `derickonfire/emotivus-forge` is the home of Forge development. New sessions should work out of this repo — see [`CLAUDE.md`](CLAUDE.md) for orientation.

## What 0.565 changes

- **Binds imported native-gate evidence to its source tree** (DG-8). Evidence now records the exact project tree fingerprint it was captured against; once the tree changes, readers report it `stale-source-changed` rather than `current` — even under an unchanged native-gate command. Evidence captured for tree A no longer counts for tree B.
- Enforced through one shared helper (`evidence_validity.effective_native_validity`) at the surfaces that report native validity (Resume, self-currency), with the fingerprint captured at import and persisted on the evidence record.
- **Completes the recorded G1 observed-miss backlog.** The remaining finding (same-version collision, DG-7) was **reviewed and did not survive verification** — the collision guard already keys off differing bytes and the declared version, and the suggested fix targeted a field that does not exist in the model. No speculative change was made; the determination is recorded in `planning/G1-RETEST-0559-OBSERVED-MISSES.md`.
- Certified suite grows additively to **533 focused public-neutral regressions across 55 deterministic isolated modules**.
- Preserves the four-page website design and active generator.

## Current verification target

**533/533** focused public-neutral regressions across 55 deterministic isolated modules.

This count is package metadata until exact final-byte certification completes. It is not release authorization or proof of efficacy.

## Normal use

Say **Run Forge**. Forge identifies the project state and supplies verified context. The AI model remains responsible for reasoning and development.
