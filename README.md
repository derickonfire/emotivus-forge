# Emotivus Forge 0.560

Forge provides portable, exact project truth and session continuity to AI models. It does not tell capable models how to reason, design, code, or debug.

> **Canonical repository:** `derickonfire/emotivus-forge` is the home of Forge development. New sessions should work out of this repo — see [`CLAUDE.md`](CLAUDE.md) for orientation.

## What 0.560 changes

- Follows a 15-agent adversarial re-test of 0.559: the five Goal-1 fixes all **held** (bounded change confidence, inferred-vs-confirmed labels, scoped secrets claim, gated run commands, and imported-baseline corroboration for ordinary tamper cases).
- **Honest corroboration boundary:** authority-baseline corroboration now states plainly that its ledger chain is **unkeyed and travels inside the project's `.forge`** — a match proves the chain is internally consistent and an authorization event exists, but is **not** a signature and cannot prove the authorization was performed by this instance rather than imported or fabricated by anyone able to write `.forge`. The prior over-claim "in this instance's ledger" is removed.
- **Ship bounded phrasing:** the Ship `candidate-unchanged` claim carries the size+mtime-only, not-byte-verified qualifier when un-hashed files exist, instead of a bare "no project paths changed."
- Full **cryptographic instance-binding** (a per-instance key an imported package cannot reproduce) is recorded as the flagship next increment in `planning/G1-RETEST-0559-OBSERVED-MISSES.md`, along with provenance corroboration parity, migration downgrade, same-version-collision-by-bytes, and native-evidence source binding.
- Keeps the certified suite at 523 focused public-neutral regressions across 54 deterministic isolated modules; regression extended in place, none added or removed.
- Preserves the four-page website design and active generator.

## Current verification target

**523/523** focused public-neutral regressions across 54 deterministic isolated modules.

This count is package metadata until exact final-byte certification completes. It is not release authorization or proof of efficacy.

## Normal use

Say **Run Forge**. Forge identifies the project state and supplies verified context. The AI model remains responsible for reasoning and development.
