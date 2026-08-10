# Observed miss — the truth ledger recorded unbound assertions as CONFIRMED

**Type:** observed miss (G1 project-truth) · **Recorded:** 0.576→next cycle
**Trial status:** **DELIVERED this cycle** — scored trial passed (see below).
Instrument: `core/truth_ledger.py` schema 2 (CONFIRMED/ATTESTED provenance split,
constructor + verify-time enforcement, binder emission bridge).

## What happened (LineCheck, reported by the watched party itself)

The LineCheck Independent Reviewer — a peer AI session, the *subject* the
North-Star roadmap was written from watching — filed a blunt field note against
Forge 0.576 (`planning/FIELD-NOTE-linecheck-reviewer-on-adopting-forge.md`)
after using `forge ledger` live for nine real review verdicts. Its central
finding:

> I was able to `forge ledger append --verdict CONFIRMED` with a *hand-asserted*
> verdict and no binder actually re-deriving anything. So a hash-chained
> `CONFIRMED` currently proves only that *I recorded it consistently*, **not that
> it is true.** A fabricating agent would produce a perfectly HEALTHY chain of
> confident lies.

Verified against source before acting (never build on a peer's word): at
`941d450`, `core/truth_ledger.py` accepted any verdict in
`{CONFIRMED, CONTRADICTED, UNVERIFIABLE, INCOMPLETE}` with `ground_truth`
defaulting to `{"kind": "none"}` and `method` defaulting to `""`. Nothing
distinguished a binder-derived CONFIRMED from a typed one, and `verify_ledger`
tallied both identically under a HEALTHY chain. The claim reproduced exactly.

## The miss (the product gap)

Forge's founding invariant — **never upgrade NOT_RUN to PASS; verification is
earned, never assumed** — was not applied to the ledger itself. The ledger let a
claim that was never machine-verified be *recorded as* machine-verified truth,
then wrapped it in a hash chain whose HEALTHY status reads as trustworthiness.
That is worse than no ledger: it is a cryptographic veneer on unverified prose,
and it is precisely the artifact a confabulating agent would produce.

The gap has two halves:

1. **No provenance distinction.** "True because a binder re-derived it against
   ground truth" and "true because someone typed it" were the same verdict.
2. **No enforcement at either end.** Neither `append_claim` (write time) nor
   `verify_ledger` (read time) refused an unbound CONFIRMED, so even a
   hand-edited file rendered as verified truth.

## The instrument (what was built)

Schema 2 of the witness truth ledger:

- **Verdict split.** `CONFIRMED` = true AND binder-derived; requires
  `derivation="binder"`, a non-empty `reproduce` command, and a real
  ground-truth binding (`kind != "none"`). `ATTESTED` = asserted true by a
  human/model from reasoning — honest, recorded, but explicitly unbound, and
  never rendered as CONFIRMED.
- **Write-time enforcement.** `append_claim` refuses an unbound CONFIRMED, a
  binder derivation without its backing (any verdict — claiming "a binder
  derived this" without evidence is itself a lie), and a binder-derived
  ATTESTED (a binder-derived positive is CONFIRMED).
- **Read-time enforcement.** `verify_ledger` flags any CONFIRMED entry that is
  not binder-backed (legacy schema-1 rows, hand-edited files) as
  `unbound_confirmed` and reports BLOCKED — the ledger refuses to *render*
  unbound verified truth even when the chain math is intact.
- **Honest upgrade path.** ATTESTED → CONFIRMED is a supersession that must
  carry binder backing; the flip stays visible in lineage history.
- **Binder emission bridge.** `append_binder_verdict` /
  `record_binder_result` turn a real `forge bind` result (findings carry
  `reproduce` commands already) into a genuinely binder-derived entry.
  Verdict mapping preserves the founding rule: binder `NOT_RUN` →
  ledger `UNVERIFIABLE` (terminal), never a positive verdict; a "binder"
  CONFIRMED with no finding-level reproduce evidence is refused.
- **Provenance visibility.** `verify` and `show` report per-derivation tallies
  and each lineage's `current_derivation`, so a reader can see at a glance how
  much of the ledger is machine-verified versus judgement.

## Scored trial

Reproduce the field note's exact action and score the outcome:

1. **The fabrication path is closed.** `forge ledger append --claim ... --verdict
   CONFIRMED` (no binder backing) — previously recorded and chained HEALTHY —
   now refuses with a message naming ATTESTED as the honest verdict, and writes
   nothing. Scored at CLI and core levels
   (`test_hand_asserted_confirmed_is_refused[_at_the_cli]`).
2. **The honest judgement path stays open.** The same claim records as
   ATTESTED, chain HEALTHY, provenance visible as `asserted`.
3. **The smuggling path is detected.** A chain-consistent, correctly-hashed
   unbound CONFIRMED written directly to the file (legacy/tamper shape) is
   flagged `unbound_confirmed` and the ledger reports BLOCKED
   (`test_smuggled_unbound_confirmed_is_flagged_at_verify`).
4. **The machine path earns CONFIRMED.** A binder result with reproduce
   evidence records as binder-derived CONFIRMED; binder NOT_RUN lands as
   UNVERIFIABLE (`BinderEmissionTests`).

## Boundary (what this does not fix)

The field note is explicit that the original failure was a *motivation* failure:
an agent willing not to check will simply not call the ledger, or will feed it
lies wrapped as ATTESTED. Schema 2 does not stop that and does not claim to.
What it guarantees is narrower and checkable: **the ledger itself can no longer
be the instrument of the lie.** An unbound claim can at most be ATTESTED, and
every CONFIRMED carries a recipe a skeptical reader can re-run. Raising the
floor for honest-but-sloppy agents is the deliverable; fixing unwilling agents
is out of scope for any tool.
