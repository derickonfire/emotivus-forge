# Working on Emotivus Forge — session orientation

**This repository (`derickonfire/emotivus-forge`) is the canonical home for
Emotivus Forge development.** Work out of this repo. Forge previously lived in
the scratch repo `derickonfire/Llweb` (which was empty at the time and was only
ever a temporary workspace); that history was migrated here in full. Do not
resume Forge work in `Llweb`.

## What Forge is

Forge supplies portable, exact **project truth and session continuity** to AI
models. It is deterministic scaffolding that sits *beside* a capable model — it
does not tell the model how to reason, design, code, or debug. Its single core
invariant: **never upgrade a `NOT_RUN` result to `PASS`.** Verification is only
ever earned, never assumed.

Five public commands sit behind the phrase **"Run Forge"**: Help, Adopt,
Resume, Check, Ship.

**The spine vs. the selling point.** Forge's reason to live is **provable project
truth** (Goal 1): a deterministic oracle a capable-but-wrong model can't argue
with, because model capability never confers knowledge of *this* project's real
state. **Token conservation** — a cold model skipping a repo re-read because the
first-contact Brief is trustworthy (~443× on Flask) — is a real, demonstrable
*selling point* and on-ramp, but it is a **consequence of trustworthy truth, not
the goal.** If a choice ever arises, "impossible to fool" beats "cheap." Do not let
the roadmap drift back toward polishing the on-ramp at the expense of the G1 core.

## How to run it

```bash
python3 forge.py            # Run Forge — orient on the current project
python3 forge.py resume     # session continuity brief
python3 forge.py check      # deterministic status
python3 forge.py ship       # sealing / packaging
```

## How to run the tests

There is no pytest dependency; the suite runs on the stdlib:

```bash
python3 -m unittest discover -s tests -q
```

The certified target is **546 tests across 58 deterministic isolated modules**,
and it must stay green.

## Invariants that keep the suite self-consistent

Forge verifies its own narrative. Several things are cross-checked and will fail
loudly if you touch them carelessly:

- **Frozen counts.** `tests/test_narrative_integrity.py` hardcodes the 546 / 58
  counts. Adding a *new test method* changes the regression count, so a seal that
  adds tests must bump the count across the narrative surfaces in lockstep. Do
  **not** contort tests to dodge this — write the clean test and bump the count.
  (0.573 note: the exact-count claim is itself a lockstep cost that has silently
  drifted across ungated copies before; making it computed rather than
  hand-maintained is a recommended future anti-bloat cut.)
- **Lockstep version.** A version bump must move in lockstep across every
  surface the narrative-integrity check enumerates (docs, manifest, product
  JSON, public package, regenerated site). Bump nothing in isolation.
- **Runtime reachability.** `tools/map_runtime_reachability.py` must classify
  every top-level path. A new top-level file/dir (including a new top-level
  doc like this one) must be registered in `_classify_actual_top_level` or
  `test_runtime_reachability` fails.
- **No literal secrets in engine source.** Secret-screening rules must use
  quantifier/pattern forms only — never a literal example token — or the
  self-screen test `test_forge_source_tree_screens_clean` flags the engine's
  own source.

Run `python3 tools/check_progress_status.py` and the narrative-integrity check
after any change that touches versions, counts, or docs.

## Where the plan lives

- `ROADMAP-2029.md`, `DEVELOPMENT-ROADMAP.md`, `FORGE-2029-VERDICT.md` — the
  strategic direction (why Forge is worth keeping given AI advancement, and the
  three goals: Provable Truth, One-Command Continuity, Cross-Model Evolution
  Kernel).
- `planning/` — per-version objectives, findings, and observed-miss notes,
  including the multi-agent spectrum field-test results that drive the roadmap.

## Git conventions

Develop on branch `claude/forge-future-roadmap-op77i3`. Keep the suite green,
seal versions honestly, and never claim verification that was not run.
