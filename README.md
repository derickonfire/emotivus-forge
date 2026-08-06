# Emotivus Forge 0.569

Forge provides portable, exact project truth and session continuity to AI models. It does not tell capable models how to reason, design, code, or debug.

> **Canonical repository:** `derickonfire/emotivus-forge` is the home of Forge development. New sessions should work out of this repo — see [`CLAUDE.md`](CLAUDE.md) for orientation.

## What 0.569 changes

- Continues **Goal-3 cross-model evolution** with **explicit component lifecycle records** (P4-03). A project authority (or a newer model acting for one) records that a named component was **retained, folded, frozen, retired, or replaced** — a `fold`/`replace` names its successor, and a `replace` records the **invariants that must be preserved** — via `forge adopt --record-lifecycle-transition <contract>`.
- Each transition is an **append-only, chain-verified ledger event** (`component-lifecycle-transition`), so component evolution across model generations is **auditable**. The Resume Brief surfaces a `Component lifecycle:` line summarizing recorded transitions (only when present).
- This delivers the "replace an obsolete component" half of the G3 completion rule with an auditable record; whether the declared invariants were actually preserved is a separate verification step (kept honest in the truth boundary).
- Goal 1 remains certified **COMPLETE**; release authorization remains **false**.
- Certified suite grows additively to **542 focused public-neutral regressions across 57 deterministic isolated modules** (new `test_lifecycle_transition`).
- Preserves the four-page website design and active generator.

## Current verification target

**542/542** focused public-neutral regressions across 57 deterministic isolated modules.

This count is package metadata until exact final-byte certification completes. It is not release authorization or proof of efficacy.

## Normal use

Say **Run Forge**. Forge identifies the project state and supplies verified context. The AI model remains responsible for reasoning and development.
