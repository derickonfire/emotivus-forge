# Emotivus Forge 0.562

Forge provides portable, exact project truth and session continuity to AI models. It does not tell capable models how to reason, design, code, or debug.

> **Canonical repository:** `derickonfire/emotivus-forge` is the home of Forge development. New sessions should work out of this repo — see [`CLAUDE.md`](CLAUDE.md) for orientation.

## What 0.562 changes

- Begins **cryptographic instance-binding** — the enforced form of the honest 0.560 corroboration boundary. Authority-baseline authorization events are now signed with a **per-instance key stored outside any project tree** (`core/instance_key.py`, in a Forge home overridable by `FORGE_HOME`). The signature travels in the ledger but carries the *signer's* key id, so a verifying instance elevates only signatures from a key it trusts (its own).
- Corroboration is now **tri-state**: `instance-bound` (chain-verified event signed by this instance's key), `self-consistent` (a matching event that is unsigned or from an imported/foreign key), or `uncorroborated` (no match / broken chain). **Only `instance-bound` is release-eligible.**
- This **closes the fabricated-ledger residual** the 0.559 re-test found: an imported package can rebuild a self-consistent chain, but it cannot produce a signature under the victim instance's key, so it stays `self-consistent` — honest as "current" yet never release-eligible. Proven by a regression that strips the signature from a legitimately authorized event and asserts it drops to `self-consistent` and loses release eligibility.
- Honest limits stated in `TRUTH_BOUNDARY`: this authenticates a key/instance, not a human or review quality; a stolen instance secret (full machine compromise) defeats it; when the Forge home is unavailable, signing degrades to unsigned rather than falsely claiming binding. Multi-party peer enrollment (the collaboration secret) is the next increment.
- Certified suite grows additively to **530 focused public-neutral regressions across 55 deterministic isolated modules**.
- Preserves the four-page website design and active generator.

## Current verification target

**530/530** focused public-neutral regressions across 55 deterministic isolated modules.

This count is package metadata until exact final-byte certification completes. It is not release authorization or proof of efficacy.

## Normal use

Say **Run Forge**. Forge identifies the project state and supplies verified context. The AI model remains responsible for reasoning and development.
