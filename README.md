# Emotivus Forge 0.575

Forge provides portable, exact project truth and session continuity to AI models. It does not tell capable models how to reason, design, code, or debug.

> **Canonical repository:** `derickonfire/emotivus-forge` is the home of Forge development. New sessions should work out of this repo — see [`CLAUDE.md`](CLAUDE.md) for orientation.

## What 0.575 changes

- **Goal 2: leave a session in one command.** A cold model can now close a session through Run Forge itself — `forge run --close <digest.json>` — instead of switching to a separate close/ship workflow. The digest is the model's compact end-of-session record (session type, summary, completed work, exact next action, optional continuity-export path); Forge runs the scoped Check, records the durable Session Close, refreshes continuity, surfaces the exact next action, and optionally exports a portable continuity bundle. Entering was already one command; now leaving is too. This reuses the existing scoped-Check and Session-Close machinery — wiring, not a new subsystem — and is regression-locked end to end. Release-candidate routing and the scored cross-vendor cold-trial gate remain before G2 can be declared complete.

## What 0.574 changed

- **Completes the anti-bloat pass.** The exact test/module count is no longer copied across CERTIFICATION, README, the manifest, and a test in numeric lockstep — a hand-maintained integer that had already silently drifted in ungated copies. The live count is reported by the self-test runner straight from the actual suite; prose describes the suite qualitatively. The narrative-integrity check still verifies version, schema, required-path, and download-checksum relationships.

## What 0.573 changed

- **Field-usefulness fixes.** A genuine read-only consultation on a real project surfaced three defects where Forge behaved as a blocker rather than an advisor; all three are fixed and regression-locked:
  - A **pending decision fork is now advisory**, not a blocker — first-contact orientation no longer tells the agent to "stop before changing the project" over a choice Forge merely noticed. Only a *contradiction* against a confirmed decision blocks.
  - The **objective resolver obeys a document's own staleness banner.** A planning file that says "this file is historical/superseded; continue from X" is no longer scraped for an objective, even when it carries a "next action" heading — Forge reads the plain-English banner a human obeys.
  - **Test/acceptance/gate harnesses are discovered.** A project whose checks are a `check_*`/gate/acceptance suite is no longer reported as having zero tests; the layout also states its method and flags that a non-standard harness can still be missed.
- **Anti-bloat pass.** Internal self-consistency gates that enforced bookkeeping ceremony rather than a truthful claim were removed — per-chunk timebox format/range, retired-percentage guards, exact website-nav labels, and same-file goal-status duplication. Every check that prevents a real reader-facing misstatement (version consistency, schemas, required paths, download checksums, goal-status vocabulary, and the planning-doc goal rows a reader consults) was kept.
- Three new regression tests were added and four ceremony tests removed, so the certified count is unchanged and no existing behavior test was altered. **G1 is COMPLETE, G3's foundation is certified/CONTINUOUS; G2 is the one remaining open goal.** Release authorization remains **false**.
- Preserves the four-page website design and active generator.

## Current verification target

A comprehensive suite of focused, public-neutral regressions across deterministic, isolated modules, run from the package's own extracted bytes. Run `python3 -m emotivus_forge self-test` for the live count and per-module results.

Passing is package metadata until exact final-byte certification completes. It is not release authorization or proof of efficacy.

## Normal use

Say **Run Forge**. Forge identifies the project state and supplies verified context. The AI model remains responsible for reasoning and development.
