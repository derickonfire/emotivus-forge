# Emotivus Forge 0.564

Forge provides portable, exact project truth and session continuity to AI models. It does not tell capable models how to reason, design, code, or debug.

> **Canonical repository:** `derickonfire/emotivus-forge` is the home of Forge development. New sessions should work out of this repo — see [`CLAUDE.md`](CLAUDE.md) for orientation.

## What 0.564 changes

- Extends **instance-binding to artifact provenance** — parity with the authority-baseline work. A deliverable's recorded lineage (`artifact-provenance-recorded`) is now a signed event, and the scoped Check asserts `CONFIRMED` for it only when that event is **instance-bound** (signed by a key this instance trusts).
- A byte-matching but **unsigned or imported** provenance record stays honest as "current" but is **not** asserted as authenticated provenance (its truth-state is `OBSERVED`, not `CONFIRMED`), with a reason that says so plainly.
- This **closes the last place** the "self-consistent ≠ authentic" class still lived: after 0.562–0.563 (authority) and 0.564 (provenance), an imported package can no longer spoof either authenticated authority or authenticated provenance.
- Proven by a regression that records provenance (instance-bound → `CONFIRMED`), then strips the signature from the recording event and asserts it drops to `self-consistent` and loses `CONFIRMED`.
- Certified suite grows additively to **532 focused public-neutral regressions across 55 deterministic isolated modules**.
- Preserves the four-page website design and active generator.

## Current verification target

**532/532** focused public-neutral regressions across 55 deterministic isolated modules.

This count is package metadata until exact final-byte certification completes. It is not release authorization or proof of efficacy.

## Normal use

Say **Run Forge**. Forge identifies the project state and supplies verified context. The AI model remains responsible for reasoning and development.
