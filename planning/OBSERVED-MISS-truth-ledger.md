# Observed miss → G-track instrument: a durable claim→ground-truth→verdict ledger

## The miss (from the field, this watch)

Acting as the read-only "man with the binoculars" over the LineCheck collaboration,
the witness role produced exactly one kind of durable output: a running record of
*claims* made across the collaboration (governance docs, bus messages, checkpoints)
each bound to independently-verifiable *ground truth* (git objects, file bytes, run
IDs) with a *verdict* — CONFIRMED / CONTRADICTED / UNVERIFIABLE / INCOMPLETE.

That record had to be kept **by hand in a scratchpad markdown file**. Forge already
ships an append-only, hash-chained **event ledger** (`core/ledger.py`) and a
deterministic **ledger-assertions** capability (`core/ledger_assertions.py`), but:

- the event ledger records *Forge's own lifecycle events*, not third-party claims and
  their verdicts against ground truth;
- ledger-assertions record *obligations to re-check* ("this rule must hold"), not a
  *witness history* of "this claim was made, here is what the ground truth showed."

So there was no first-class Forge artifact for the witness verdict history. The most
valuable output of a truth-observer had no home in the tool whose entire thesis is
*portable, exact project truth*.

## Why it matters (North Star)

Forge's durable value is maintaining a **truthful, evolving model of a subject across
sessions**. A witness ledger is the substrate for that: trust accrues, drift becomes
visible (a verdict that flips over time), and — critically — the record is
**append-only and supersede-not-delete**, so nothing is silently rewritten. This
generalizes beyond a git project to any subject (the person / "second brain" track),
where the same honesty invariants apply and *only* the ground-truth binding differs.

## The honesty invariants (carried from Forge's founding rule)

1. **Append-only.** Entries are never mutated or deleted. A changed verdict is a new,
   linked entry that **supersedes** the prior one; the superseded entry stays readable.
2. **No auto-upgrade.** There is no code path that changes an entry's verdict. In
   particular UNVERIFIABLE is a first-class terminal verdict — it never silently
   becomes CONFIRMED (the ledger analog of "never upgrade NOT_RUN to PASS").
3. **Hash-chained.** Every entry carries the canonical hash of the prior entry, so any
   tamper (including an edited verdict) is detectable, exactly like the event ledger.
4. **Provenance-stamped.** Each entry records where the claim was made (source), how it
   was checked (method / reproduce), the ground truth observed, and who recorded it.
5. **Drift is visible, not erased.** A supersession chain preserves the full history; a
   verdict flip along a chain is reported, not hidden.

## Scored trial (before shipping the instrument)

The instrument is accepted only if it can reproduce, as tool output, the shape of the
hand-kept ledger from this watch — the E1–E6 entries (divergence claims CONFIRMED, a
self-reported `.pyc` defect CONFIRMED, the AUTHORITY-INDEX SHA-256 EXACT match, the
reconcile heads, the blob-identity claim) — including a genuine supersession (the
cycle-7 stale-ref near-miss, where an initial reading was later superseded by the
force-fetched truth) and its verdict flip surfaced by `current_view`.

## Instrument delivered (this increment)

- `core/truth_ledger.py` — append-only, hash-chained claim ledger with supersede-not-
  delete, verdict validation, chain verification, and a current-view fold that surfaces
  supersession lineage and verdict flips.
- `forge ledger {append,supersede,verify,show}` — the command surface.

Boundary (stated, not hidden): the ledger records *witness verdicts and their
provenance*. It does not itself re-derive ground truth (that is the binder track, R3/R8)
— an entry is only as sound as the method that produced its verdict. `verify` proves
chain integrity, not that any single verdict was correct.
