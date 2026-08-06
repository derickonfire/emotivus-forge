# Emotivus Forge 0.561

Forge provides portable, exact project truth and session continuity to AI models. It does not tell capable models how to reason, design, code, or debug.

> **Canonical repository:** `derickonfire/emotivus-forge` is the home of Forge development. New sessions should work out of this repo — see [`CLAUDE.md`](CLAUDE.md) for orientation.

## What 0.561 changes

- Adds a genuine **read-only consultation mode** — `run --read-only` and `resume --read-only`. Forge reads the project's real bytes and prior state but **writes nothing into the project tree**: its state directory is redirected to a disposable location outside the project (and both repositories), used for the run, then discarded. Verified by a regression that hashes the whole target tree before and after and asserts it is byte-identical.
- This is what lets Forge advise on a **shared or third-party repository** under a strict read-only bound — consult without adopting, and leave no `.forge` footprint. The read-only payload is explicitly labeled advisory (`read_only: true` with stated limitations) and is never acceptance evidence.
- Implemented as one clean interception: a state-directory redirect (`state_root` / `redirect_state`) that every ForgePaths-based read/write and the storage lock resolve through; normal (persisting) operation is unchanged.
- Grows the certified suite additively to **529 focused public-neutral regressions across 55 deterministic isolated modules** (a new read-only-consult module; six regressions added).
- Preserves the four-page website design and active generator.

## Current verification target

**529/529** focused public-neutral regressions across 55 deterministic isolated modules.

This count is package metadata until exact final-byte certification completes. It is not release authorization or proof of efficacy.

## Normal use

Say **Run Forge**. Forge identifies the project state and supplies verified context. The AI model remains responsible for reasoning and development.
