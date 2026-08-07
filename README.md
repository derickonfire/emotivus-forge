# Emotivus Forge 0.571

Forge provides portable, exact project truth and session continuity to AI models. It does not tell capable models how to reason, design, code, or debug.

> **Canonical repository:** `derickonfire/emotivus-forge` is the home of Forge development. New sessions should work out of this repo — see [`CLAUDE.md`](CLAUDE.md) for orientation.

## What 0.571 changes

- Continues **Goal-3** with **verified replacement invariants** (P4-05). A component `replace` transition can now declare structured `invariant_checks` — a scoped-Check subject plus its required truth-state — and Forge **verifies** them against the actual Check truth records, reporting each invariant **preserved** or **violated** (a violation raises a warning finding; free-text invariants stay recorded but unverified).
- This delivers the "verify preserved invariants" step: a newer model can replace an obsolete component and have Forge **confirm the declared invariants still hold**, rather than take the replacement on trust. `verify_lifecycle_invariants` runs inside the scoped Check and surfaces in its payload.
- Honest boundary: PRESERVED means the referenced truth still holds, not that the replacement is correct or complete; only structured, Forge-observable invariants are verified.
- Goal 1 remains certified **COMPLETE**; release authorization remains **false**.
- Certified suite grows additively to **545 focused public-neutral regressions across 57 deterministic isolated modules**.
- Preserves the four-page website design and active generator.

## Current verification target

**545/545** focused public-neutral regressions across 57 deterministic isolated modules.

This count is package metadata until exact final-byte certification completes. It is not release authorization or proof of efficacy.

## Normal use

Say **Run Forge**. Forge identifies the project state and supplies verified context. The AI model remains responsible for reasoning and development.
