# Observed miss — the selling point drifted in front of the spine

**Recorded:** during the 0.558 cycle, in the canonical `emotivus-forge` repo.
**Class:** roadmap/priority miss (not a code defect).

## What happened

Across releases 0.554–0.558 the real build budget went to the *on-ramp*:
reduction, the context digest, the trustworthy first-contact Brief, description
and layout hygiene, and the ranked ecosystem resolver. In conversation this
hardened into calling token conservation "the product." The milestone map
(`DEVELOPMENT-ROADMAP.md`, M4) had slotted 0.557–0.558 as **Prove Goal 1**; that
work was not done. `P2-01` is still merely *active*.

## Why it's a miss

Forge was **saved, not killed**, for one durable reason: rising model capability
never confers knowledge of a *specific* project's ground truth, and as models
become autonomous agents the cost of a confidently-wrong assertion about that
truth goes up. The thing that survives AI advancement is a deterministic oracle of
**provable project truth** that never upgrades `NOT_RUN` to `PASS` (**Goal 1** —
the spine). Token conservation is downstream of that: a Brief only saves work if it
can be *trusted*. Framing the selling point as the goal quietly de-prioritized the
one property that makes Forge un-killable in three years.

## Ground truth being asserted

- The reason-to-live is G1 provable truth; token conservation is a consequence and
  a selling point, never the goal.
- The on-ramp work (0.554–0.558) is sound and is retained — it is not reverted.
- The correction is a re-prioritization, not a rewrite: the G1 provable-truth core
  moves to the front of the build order.

## Correction (bounded)

1. Re-center the strategic and development roadmaps and `CLAUDE.md` on the spine
   (done in this cycle — prose only, no version bump, suite kept green).
2. Next real build = the **G1 provable-truth core**: adversarial package
   rejection, exact-byte verification, authorization only from independently
   verified bytes.
3. Before that build, run a **G1-aimed field test** — *where can a model push
   Forge into asserting something it hasn't proven?* — and record the observed
   misses first, per the expansion rule. (Held pending explicit GO to fire agents.)

## Guardrail for future sessions

If a cycle's work advances approachability, orientation, or cost-savings but not
the G1 core, name that honestly and do not describe it as advancing the reason to
live. Cheap is the on-ramp; impossible-to-fool is the point.
