# Observed miss — no instrument certifies a gate-script change is monotonic

**Type:** observed miss (G1 project-truth) · **Recorded:** 0.575 cycle
**Trial status:** **DELIVERED 0.575** — scored trial passed. Instrument:
`core/gate_diff_monotonicity.py` + `tools/bind_gate_diff_monotonicity.py`.
Real LineCheck replays: the schema-pin bump `8d578b9..8845c3f` → CONFIRMED
(assertions 4312→4380, +68, none removed; SKIP 10→10); the LC-004 merge
`dcb7dbb^..dcb7dbb` scoped to checks → CONFIRMED (new behaviour checks additive).
The LC-004 replay first exposed a real design flaw — new check files carry honest
"SKIP if no DB" guards, which a crude aggregate miscounted as a new SKIP path; the
delivered version measures assertion-loss and new-SKIP **per existing (modified)
file** and treats added checks as additive. Contradiction cases (removed assertion,
new SKIP in an existing check, deleted check) covered by isolated tests.

## What happened (LineCheck)

Twice during LC-004, a change edited the project's own **gate/check scripts**, and
the only thing standing between "legitimate maintenance" and "silently weakened
gate" was a human reading the diff:

1. **Schema-pin bump.** `LC_SCHEMA_VERSION` moved 72→73, updating a string-pinned
   literal in ~12 controlled checks in one commit. Legitimate monotonic
   maintenance — but nothing *verified* that only the literal changed and no
   assertion was removed, no threshold lowered, no SKIP introduced.
2. **Probe-hardening (deferred).** A fail-closed change to the CI smoke-suite
   `php -m` probe was proposed; the reviewer had to reason by hand that it removed
   no assertion and added no SKIP path before it could land.

In both cases the judgement was correct, but it was *model judgement*, reproduced
by hand. A green gate after a gate-script edit proves nothing about whether the
edit weakened the gate.

## The miss (the product gap)

Forge can now bind release-truth (`source_anchored_release`), but it has no
instrument that, given a diff to gate/check scripts, deterministically certifies
the change is **monotonic**: no assertion line removed, no PASS threshold lowered,
no new SKIP path, only whitelisted literals changed. This is the "self-consistent
≠ authentic" family applied to the *gate itself* — a gate can be edited into
agreement with a weaker reality.

## Candidate instrument (not yet built)

`gate-diff monotonicity` binder: input a diff (or two refs) over declared
gate/check paths; output CONFIRMED (only allowlisted literals changed) /
CONTRADICTED (an assertion removed, threshold lowered, or SKIP introduced) /
NOT_RUN (paths unreachable). Pairs with a declare-before-land checkpoint. Same
truth-boundary discipline: binds the diff's shape, not the semantics of what the
checks assert.

## Before it becomes an instrument
Scored trial required: replay against the real LineCheck schema-pin commit
(expect CONFIRMED) and a synthetic assertion-removal (expect CONTRADICTED), plus
at least one Forge-internal gate edit, before adding it to the durable core.
