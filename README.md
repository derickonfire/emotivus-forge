# Emotivus Forge 0.568

Forge provides portable, exact project truth and session continuity to AI models. It does not tell capable models how to reason, design, code, or debug.

> **Canonical repository:** `derickonfire/emotivus-forge` is the home of Forge development. New sessions should work out of this repo — see [`CLAUDE.md`](CLAUDE.md) for orientation.

## What 0.568 changes

- Continues **Goal-3 cross-model evolution**: the continuity kernel is now explicitly **vendor-neutral** (P4-01). A distilled session digest stores *project truth*, not model instructions — so on intake Forge rejects model-instruction and vendor-identity keys (`system_prompt`, `system`, `instructions`, `model_instructions`, `persona`, `prompt(s)`, `tools`, `functions`, `model`, `provider`, `vendor`) alongside the raw-transcript keys it already refused.
- Effect: a **different model can consume the continuity** without inheriting another model's directives. The digest's truth boundary now states the vendor-neutrality guarantee explicitly.
- Structural (key-based) screening, consistent with the existing raw-transcript guard — no heuristic content scanning, so no false positives on legitimate objectives or decisions.
- Goal 1 remains certified **COMPLETE**; release authorization remains **false**.
- Certified suite grows additively to **537 focused public-neutral regressions across 56 deterministic isolated modules**.
- Preserves the four-page website design and active generator.

## Current verification target

**537/537** focused public-neutral regressions across 56 deterministic isolated modules.

This count is package metadata until exact final-byte certification completes. It is not release authorization or proof of efficacy.

## Normal use

Say **Run Forge**. Forge identifies the project state and supplies verified context. The AI model remains responsible for reasoning and development.
