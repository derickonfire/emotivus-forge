# Emotivus Forge 0.559

Forge provides portable, exact project truth and session continuity to AI models. It does not tell capable models how to reason, design, code, or debug.

> **Canonical repository:** `derickonfire/emotivus-forge` is the home of Forge development. New sessions should work out of this repo — see [`CLAUDE.md`](CLAUDE.md) for orientation.

## What 0.559 changes

- Hardens the Goal-1 **provable-truth core** from a 15-agent adversarial field test (the spine, not the on-ramp): every fix subtracts unearned certainty.
- Imported authority baseline is corroborated against a chain-verified authorization event in this instance's ledger, or demoted to `UNCORROBORATED` and quarantined from release — an internally-consistent *imported* baseline is no longer trusted as authority.
- Change detection reports **bounded** confidence (never a bare proven "0 changed") when a file was compared by size and modification time instead of hash, and names the un-hashed paths.
- Derived identity, objective, description, and run/test commands are labeled inferred at the point of assertion: `confirmed` is reserved for owner-recorded identity, a scraped README/`<title>` name is `inferred`, a command line is never taken as a description, and `go run` is only suggested for an observed `main` package.
- The no-objective prompt no longer promises it surfaced *any* hardcoded secrets — screening is stated as bounded, not a completeness guarantee.
- Keeps the certified suite at 523 focused public-neutral regressions across 54 deterministic isolated modules; regressions extended in place, none added or removed.
- Preserves the four-page website design and active generator.

## Current verification target

**523/523** focused public-neutral regressions across 54 deterministic isolated modules.

This count is package metadata until exact final-byte certification completes. It is not release authorization or proof of efficacy.

## Normal use

Say **Run Forge**. Forge identifies the project state and supplies verified context. The AI model remains responsible for reasoning and development.
