# Emotivus Forge 0.570

Forge provides portable, exact project truth and session continuity to AI models. It does not tell capable models how to reason, design, code, or debug.

> **Canonical repository:** `derickonfire/emotivus-forge` is the home of Forge development. New sessions should work out of this repo — see [`CLAUDE.md`](CLAUDE.md) for orientation.

## What 0.570 changes

- Hardens the **Goal-3 continuity kernel** against two over-assertions a 12-agent adversarial field test found (`planning/G3-FIELD-TEST-OBSERVED-MISSES.md`) — both genuine violations of Forge's own ethos, both now closed and regression-locked.
- **GM-2 — lifecycle instance-binding:** `component-lifecycle-transition` is authority-declared, so it is now signed and instance-bound like authority and provenance. `lifecycle_transition_summary` and the Resume line label each transition `instance-bound` vs `self-consistent`; an imported or unsigned (forged self-consistent chain) transition is **never counted as an authentic in-instance record** without the imported label.
- **GM-1 — vendor-neutral free-text screening:** the session digest previously screened only top-level keys, so model directives smuggled into accepted free-text (objective, decisions, …) survived. Forge now screens those values with narrow, high-precision prompt-injection / vendor-directive patterns (ordinary mentions of "system"/"model" are **not** flagged), and the truth boundary is softened to state only what the code enforces.
- Goal 1 remains certified **COMPLETE**; release authorization remains **false**.
- Certified suite grows additively to **544 focused public-neutral regressions across 57 deterministic isolated modules**.
- Preserves the four-page website design and active generator.

## Current verification target

**544/544** focused public-neutral regressions across 57 deterministic isolated modules.

This count is package metadata until exact final-byte certification completes. It is not release authorization or proof of efficacy.

## Normal use

Say **Run Forge**. Forge identifies the project state and supplies verified context. The AI model remains responsible for reasoning and development.
