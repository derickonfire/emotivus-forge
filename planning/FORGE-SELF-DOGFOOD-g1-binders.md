# Self-dogfood — the three G1 binders run on Forge itself

**Recorded:** 0.575 cycle · **Discipline:** "impossible to fool on itself" (G1 core).
Ran the three LineCheck-surfaced binders against `derickonfire/emotivus-forge` and
recorded the honest outcome — including where a binder does **not** apply.

## Results

| Binder | On Forge | Outcome |
|---|---|---|
| `gate_diff_monotonicity` | `origin/main..HEAD` scoped to Forge's gate/check scripts | **CONFIRMED** — this branch's edits (added classification entries, new tests, regenerated reports) removed no assertion and introduced no SKIP. Directly applicable; works. |
| `source_anchored_release` | — | **N/A** — Forge has no `RELEASE-STATE.json` accepted-schema-vs-source structure. Forge's release truth is version/manifest/certification consistency, already held by `release_facts` + `narrative_integrity`. Recorded, not forced. |
| `gate_coverage` | inventory `tools/check_*.py` | **Applicability boundary** — see below. |

## What gate-coverage taught (and fixed)

Forge has **no `.github/workflows`**; its gate is the local test suite (`self-test` /
`unittest discover`, a glob sweep — all wired). Its `tools/check_*.py` are thin CLI
wrappers whose logic lives in separately-tested `core/` modules. So the "check file
invoked by name in a gate source" model the differ was built for (LineCheck's
`run_all_checks.sh`) does not describe Forge's architecture.

The differ stayed **honest** — it returned `NOT_RUN`, not false gaps. But the dogfood
exposed two real defects, now fixed:

1. **Over-broad sweep marker.** The glob-sweep guard used a bare prefix (`check_*`),
   which false-matched unrelated string literals (including this repo's own test
   fixtures). Fixed to the full basename-glob and dir-qualified glob
   (`check_*.py`, `tools/check_*.py`). Regression test added.
2. **No stem matching.** Matched checks only by filename-with-extension — missing
   by-module/by-stem references (`from tools.check_foo import`). Added stem matching
   (path / basename / stem), default on. Regression test added.

The truth boundary now states the model explicitly: the differ fits gates that invoke
checks by name or module reference, not architectures where check logic sits behind
thin wrappers over separately-tested modules.

## Net

- One binder (gate-diff monotonicity) verified working on Forge's own gate edits.
- One (source-anchored) honestly scoped out.
- One (gate-coverage) hardened by two fixes and given an explicit applicability
  boundary — and it never emitted a false claim on the architecture mismatch.
- LineCheck regression preserved: gate-coverage still reports the real 6-check gap at
  `6188585`; monotonicity still CONFIRMED on the real schema-pin bump.
