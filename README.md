# Emotivus Forge 0.557

Forge provides portable, exact project truth and session continuity to AI models. It does not tell capable models how to reason, design, code, or debug.

## What 0.557 changes

- Completes the project-intelligence pass of the context digest (objective detection, architecture/layout summary, broader secret coverage), continuing the observed-miss redirection of Goal 1.
- Detects explicit objectives (`## Objective`, `Goal:`) so Forge stops nagging when the objective is written down; adds a deterministic layout summary (top dirs, primary source, packages, tests, central files).
- Broadens secret coverage: Stripe/generic live-token BLOCK rules and content-scanning of extensionless credential files (aws-credentials, .netrc, .pgpass).
- Catches hardcoded secrets in ordinary source at orientation (not only filename-flagged files); the target-user case (a hardcoded API key in app.py) now BLOCKs where it was missed.
- Reads a one-line description, entry points, and run/test commands from the project; falls identity back through go.mod/Cargo.toml/README instead of the directory name.
- Prints a measured Resume-vs-repo token comparison (e.g. Flask ~1k tokens vs ~467k to read the tree); collapses empty governance ceremony; orients before requiring an objective.
- Validated by a 12-project spectrum re-test: mean cold-model usefulness 1.83 -> 2.67/5, blocked-before-value 11/12 -> 0/12.
- Keeps the certified suite at 523 focused public-neutral regressions across 54 deterministic isolated modules; no test added or removed.
- Preserves the four-page website design and active generator.

## Current verification target

**523/523** focused public-neutral regressions across 54 deterministic isolated modules.

This count is package metadata until exact final-byte certification completes. It is not release authorization or proof of efficacy.

## Normal use

Say **Run Forge**. Forge identifies the project state and supplies verified context. The AI model remains responsible for reasoning and development.
