# Observed miss — no instrument reports checks that exist but are not gate-wired

**Type:** observed miss (G1 project-truth) · **Recorded:** 0.575 cycle
**Trial status:** **DELIVERED 0.575** — scored trial passed. Real LineCheck replay at
head `6188585` reported GAPS: 6 of 48 inventoried checks not gate-wired, including
`check_worklist_behavior.php` (the exact reviewer-flagged check) and its five sibling
Phase B–E behaviour checks. Empty-gap and glob-sweep-indeterminate cases covered by
isolated tests. Instrument: `core/gate_coverage.py` + `tools/report_gate_coverage.py`.

## What happened (LineCheck)

Across the LC-004 engagement a behaviour check, `check_worklist_behavior.php`
(76 assertions by the end), was repeatedly described as **"not gate-wired"** —
present and mirrored in the tree, but not invoked by the CI gate. Its PASS
therefore rested on the author's word, not on the gate. The reviewer noted more
than once that "the green gate does not cover several semantic failures," and the
two P0 bugs found on the first Phase B head were precisely in that uncovered
space.

A green gate that silently omits a check reads as "covered" when it is not. That
is a truth gap, not a style issue.

## The miss (the product gap)

Forge has no instrument that enumerates **checks that exist in the tree** versus
**checks the CI configuration actually invokes**, and reports the out-of-band
assertions. Forge already values honest coverage (its own self-test computes the
live count rather than asserting a frozen one, 0.574), but it cannot yet tell an
external project "these N assertions exist and are never run by your gate."

## Candidate instrument (not yet built)

`gate-coverage differ`: given a project's declared gate/CI config and its check
inventory, output the set of check files/assertions that are present but not
invoked, classified (retired / manual-only / genuinely orphaned). Deterministic,
read-only, non-model. Reports a coverage gap; it does not judge whether the
uncovered assertions matter — that remains the reviewer's domain (truth boundary).

## Before it becomes an instrument
Scored trial required: replay against LineCheck (expect it to surface the
not-gate-wired behaviour check) and against a project whose gate is complete
(expect an empty gap), before adding it to the durable core. Risk to watch:
CI-config formats vary; the first cut should be honest about which config shapes
it can and cannot parse rather than silently under-reporting.
