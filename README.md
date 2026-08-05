# Emotivus Forge 0.554

Forge provides portable, exact project truth and session continuity to AI models. It does not tell capable models how to reason, design, code, or debug.

## What 0.554 changes

- Completes roadmap chunk P1-04: consolidates duplicated deterministic plumbing (archive/hash primitives, kit-archive hygiene, the identity build-id read) into the shared truth boundary (`common.py`, `project_identity.py`); genuinely distinct services are kept distinct.
- Completes roadmap chunk P1-05: reduces the capability-activation ceremony to a minimal enabled/reason/scope/evidence record, dropping the `focused_regressions`, `native_advantage`, and `allow_repairs` attestations while preserving every safety gate (containment, budget caps, runtime-proof egress, fingerprint binding).
- Removes ~120 net lines across 15 modules with no behavior change; activates P1-06 (fold-orphaned module removal).
- Keeps the certified suite at 523 focused public-neutral regressions across 54 deterministic isolated modules; no test added or removed.
- Preserves the four-page website design and active generator.

## Current verification target

**523/523** focused public-neutral regressions across 54 deterministic isolated modules.

This count is package metadata until exact final-byte certification completes. It is not release authorization or proof of efficacy.

## Normal use

Say **Run Forge**. Forge identifies the project state and supplies verified context. The AI model remains responsible for reasoning and development.
