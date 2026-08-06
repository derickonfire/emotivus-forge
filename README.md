# Emotivus Forge 0.566

Forge provides portable, exact project truth and session continuity to AI models. It does not tell capable models how to reason, design, code, or debug.

> **Canonical repository:** `derickonfire/emotivus-forge` is the home of Forge development. New sessions should work out of this repo — see [`CLAUDE.md`](CLAUDE.md) for orientation.

## What 0.566 changes

- **Certifies Goal 1 (Provable Project Truth) COMPLETE.** Each dimension of the G1 completion rule — exact identity, authority, lineage, evidence binding, adversarial package rejection, and package authorization — is verified by a passing adversarial regression, inventoried in `planning/G1-COMPLETION.md`.
- **Independent exact-byte verification:** the public `RUN-FORGE.zip` passes its full certified suite **533/533 twice, deterministically, from its own independently extracted bytes** (P2-09).
- The roadmap moves G1 from ACTIVE to **COMPLETE** and marks the adversarial-trial (P2-08) and exact-byte-verification (P2-09) chunks satisfied. G2 and G3 remain the open goals; G3's foundation is materially advanced by the instance-binding delivered under G1.
- **Honest boundary:** completeness certifies the provable-truth *core*. Release authorization remains **false** — it does not claim any specific release is authorized or efficacious; Forge authenticates a key/instance, not a human or review quality.
- No behavior change and no test added or removed: the certified suite stays at **533 focused public-neutral regressions across 55 deterministic isolated modules**.
- Preserves the four-page website design and active generator.

## Current verification target

**533/533** focused public-neutral regressions across 55 deterministic isolated modules.

This count is package metadata until exact final-byte certification completes. It is not release authorization or proof of efficacy.

## Normal use

Say **Run Forge**. Forge identifies the project state and supplies verified context. The AI model remains responsible for reasoning and development.
