# Emotivus Forge 0.563

Forge provides portable, exact project truth and session continuity to AI models. It does not tell capable models how to reason, design, code, or debug.

> **Canonical repository:** `derickonfire/emotivus-forge` is the home of Forge development. New sessions should work out of this repo — see [`CLAUDE.md`](CLAUDE.md) for orientation.

## What 0.563 changes

- Completes **multi-party instance-binding** — peer enrollment. The owner provisions a **shared collaboration secret** into each trusted party's Forge home (`forge adopt --generate-collaboration-secret` / `--enroll-collaboration-secret`), **out-of-band, never through a project repo**. Authorizations signed with it are **mutually instance-bound** for every enrolled party.
- A party **without** the secret sees the same authorization as `self-consistent` — honest, but never release-eligible. This is the enforceable basis for a cross-model collaboration: two different-vendor models can trust each other's "this was authorized" without either being able to forge it, and no imported package can spoof in-instance authority.
- Signing prefers the collaboration key when one is enrolled (team-trusted by default), falling back to the per-instance key otherwise; verification trusts this instance's own key and the enrolled collaboration key. The secret stays in the Forge home, outside every project tree.
- Proven by a regression that runs two distinct Forge homes: with the shared secret both reach `instance-bound` and release eligibility; the home without it stays `self-consistent` and not release-eligible until it enrolls the same secret.
- Certified suite grows additively to **531 focused public-neutral regressions across 55 deterministic isolated modules**.
- Preserves the four-page website design and active generator.

## Current verification target

**531/531** focused public-neutral regressions across 55 deterministic isolated modules.

This count is package metadata until exact final-byte certification completes. It is not release authorization or proof of efficacy.

## Normal use

Say **Run Forge**. Forge identifies the project state and supplies verified context. The AI model remains responsible for reasoning and development.
