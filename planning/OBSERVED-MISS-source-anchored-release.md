# Observed miss — accepted-release truth not anchored to the accepted source

**Type:** observed miss (G1 project-truth ground truth) · **Recorded:** 0.575 cycle
**Trial:** Forge advisory observation of the live LineCheck collaboration
(`linecheck-acceptance`, LC-004 Phase E). A real cross-model team (Claude ×
Codex) was iterating a schema bump under an owner-as-sole-merger discipline.

## What happened

Twice (heads `8845c3f`, `872289b`), the LineCheck release was declared **accepted
at schema 73** while its accepted source commit `50bc5a5` had shipped **schema 72**.
The accepted/public surfaces (README-EXPORT, the commercial site pages) were
rewritten to 73 to match. Both exact-head CI runs passed **green**, because
`RELEASE-STATE.json` and the documents all agreed with **each other**. Codex
caught it by reading — "internal agreement is not exact-source acceptance" — and
returned both heads. The corrected head `6188585` split the truth honestly:
accepted stays 72 with its original evidence; 73 is an explicitly unaccepted
candidate.

## The miss (the product gap)

`core/release_facts.py` resolves a bounded set of release facts and compares
**project-declared** document fields to each other inside one package artifact.
That is an *internal-consistency* check. It cannot catch a declaration that has
been moved **ahead of the code the accepted release actually shipped**, because
once every declared surface is rewritten in lockstep, internal consistency is
restored while the claim is false. This is the same "self-consistent ≠ authentic"
family the instance-binding work closed for *authority* and *provenance* — here
it recurs for the **accepted release's schema/version**, which no instrument
anchored to the accepted source.

## Fix delivered (0.575 → branch `claude/g1-source-anchored-release`)

New G1 instrument: `core/source_anchored_release.py` + `tools/bind_release_truth.py`.

- Derives the **true accepted schema from the exact accepted source commit's
  code**, not from whatever RELEASE-STATE currently claims.
- Binds at an exact head: (1) RELEASE-STATE top schema == source-derived truth;
  (2) the candidate is labelled not-accepted with null acceptance evidence;
  (3) no accepted/public surface states a schema other than the accepted value
  (`strict` mode, with a historical-number allowlist; `candidate` mode is the
  precise default); (4) optional byte-identical release-truth invariance vs a
  certified head.
- Honours the core invariant: an unreachable head or missing anchor is
  `NOT_RUN`, never upgraded to a confirmation. Carries an explicit truth boundary
  (facts bound; application logic is out of scope — the model reviewer's domain).

## Validation

- 9 isolated temp-git regressions; full suite green (557), self-test 557/59,
  narrative integrity clean.
- Replayed against real history: **CONFIRMED** at the honest head `6188585`;
  **CONTRADICTED** at `872289b`, the surface check itself naming the four files
  that claim 73 — exactly the reviewer's manual finding, now deterministic.

## Boundary / follow-ups

- Binds data/state/surfaces at a tree; does **not** review resolver logic (which
  is why the reviewer, not Forge, correctly caught a separate fail-closed logic
  gap on a later head — the boundary held).
- Follow-up candidates: fold the release-facts comparison to consult this anchor
  directly; a first-class `forge bind` surface if the standalone tool proves out.
