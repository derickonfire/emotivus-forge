# Reproducible Continuity Benchmark

This is a **measuring instrument, not evidence.** It defines how a continuity comparison
must be set up so its results could be believed, and refuses to produce a comparison that
would not be.

## Seven enforced conditions

1. **Immutable tasks.** A task's identity is the SHA-256 of its canonical content. Change any
   field and it is a different task, never an edited one.
2. **Exact parents.** Every run names the exact package it ran against, by full SHA-256.
3. **Paired arms.** A comparison needs a `forge` arm and a `control` arm.
4. **Declared provider and model identity.** Runs on different models never pair — that
   comparison measures the models, not Forge.
5. **Isolated workspaces.** Two runs sharing a workspace path are reported as a collision.
6. **Exact token and cost records.** Provider-reported integers only. There is no estimate
   path; `token_source: heuristic-*` is rejected outright.
7. **Human review.** A run is recorded but **inadmissible** until a named reviewer accepts it.

## Status values

| Status | Meaning |
|---|---|
| `NOT_RUN` | No admissible runs. **Not** a tie, not a pass, not neutral. |
| `INCOMPLETE` | Admissible runs exist but no task has both arms matched on every controlled variable. |
| `PAIRED` | At least one task has both arms with identical task, parent, provider, and model. |

A suite with zero recorded runs reports `NOT_RUN`. Reporting a tie for a comparison that
never happened would be the single most damaging thing a benchmark could do.

## Declared suites are plans

`define_suite` produces a sealed, content-addressed plan carrying `execution_status:
NOT_RUN`, `sessions_recorded: 0`, and `declared_not_executed: true`. A target of 100 or 1,000
sessions describes **intent, never achievement**.

## What the harness does not do

- It does not execute sessions. It has no provider client and no network.
- It does not persist state. A regression asserts the module writes nothing; records go
  wherever the caller puts them, never into `.forge`.
- It does not estimate. Anything it cannot measure exactly, it refuses.

## Truth boundary

A defined benchmark proves nothing until runs are recorded, reviewed, and paired. As of this
build, **zero real sessions have been executed**. The instrument exists; the evidence does not.

## Portable exact-runtime packet

Forge 0.549 can package the immutable task, exact public runtime, isolated Forge/control templates,
and standalone finalizer into one deterministic kit. Building the packet does not execute either arm.
See `PORTABLE-EVIDENCE-KITS.md`. Exact provider-reported tokens and named accepted review remain
mandatory; null templates are rejected rather than treated as zero usage.
