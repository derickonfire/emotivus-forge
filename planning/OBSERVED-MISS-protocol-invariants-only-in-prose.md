# Observed miss — a multi-agent protocol's invariants lived only in prose

**Type:** observed miss (G1 project-truth) · **Recorded:** Phase 3 (R9, folds R5)
**Trial status:** DELIVERED this cycle — scored trial passed (see below).
Instrument: `core/protocol_verify.py` + `forge protocol verify`.

## What happened (LineCheck + Forge's own coordination lanes)

The Claude+Codex collaboration ran on an append-only coordination bus: numbered
lane records (`LC-ARCH-1_1/codex/0009`, `ATTN/codex/0011`, …), four-part
acceptance receipts, a ten-section communication authority, Packets A/B/C,
amendment/supersession maps. Real records in this very repo show the failure
modes the ceremony was meant to prevent slipping through anyway:

- `LC-ARCH-1_1/codex/0009` records that a PR body **"still names `main@1780e3b`,
  head `48633cc`"** after the branch had moved — a claim pinned to a *stale* head,
  and to a *moving ref* (`main@…`) rather than an exact reviewed commit.
- The same lane distinguishes `CODEX_HELD` states and "merge/Packet/runtime/
  release actions remain separately held" — i.e. irreversible acts are supposed
  to be owner-gated — but nothing *mechanically* checked that an act marked
  irreversible actually carried owner authorization.
- Acceptance is asserted in prose ("both standard workflows are green on the
  reviewed exact head"); whether an accept actually carried a *bindable* receipt
  (an exact reviewed head + a verifiable review id) was left to a human reading.

The field note (`planning/FIELD-NOTE-linecheck-reviewer-on-adopting-forge.md`)
names the root risk directly: *"you produce the shape of work instead of work …
numbered bus lanes, four-part receipts … a ledger layer can feed the disease as
easily as cure it."* Ceremony that is only prose is unfalsifiable — it reads as
rigor without being checkable.

## The miss (the product gap)

The collaboration's protocol invariants — **every claim pins an exact (current)
head; every accept carries a bindable receipt; the authoritative state is
structured, not prose-only; supersession preserves history; irreversible acts
are owner-gated; exactly one party holds the baton (else STALLED)** — were
enforced only by agents reading each other's prose. A capable-but-wrong (or
merely tired) agent could satisfy the *form* while breaking the *invariant*, and
nothing deterministic caught it. This is the same class of gap as a green
internal-consistency gate that never bound to source: agreement of prose with
prose is not verification.

## The instrument (what was built)

`core/protocol_verify.py` — `verify_protocol(config, repo, check_liveness)` —
deterministically checks a declared protocol (structured records, supplied in a
config; the verifier is NOT coupled to any particular bus's markdown, and reads
no coordination data it is not handed) against six invariants:

1. **structured-state** — every record declares a recognized `type` and `party`;
   authoritative state is not prose-only.
2. **exact-head** — every `claim`/`accept` pins an exact commit id, and (with
   `--repo`) that head is currency-verified through the R8 guard: a moving ref
   name or a superseded head is a violation, never a pass.
3. **bindable-receipt** — every `accept` carries a receipt with an exact reviewed
   head and a verifiable id.
4. **supersession** — every `supersedes` targets an existing record, no target is
   superseded twice (no silent fork), and the chain is acyclic (history preserved).
5. **owner-gated-irreversible** — every record marked `irreversible` carries
   owner authorization.
6. **liveness** (`--liveness`) — replaying baton handoffs from `initial_holder`,
   every transfer must come from the current holder (baton conserved) and exactly
   one named party must hold it at the tip; a forged/dropped/contended baton is
   **STALLED**.

Verdicts use the binder vocabulary (CONFIRMED / CONTRADICTED / NOT_RUN) so a
protocol run feeds the truth ledger via `record_binder_result` (`--ledger`):
CONFIRMED arrives binder-derived with the re-run command; an unassessable protocol
is NOT_RUN → terminal UNVERIFIABLE.

## Scored trial

A fixture protocol in a real temp repo, scored per invariant:

1. **Healthy protocol → CONFIRMED / LIVE.** Exact current heads, receipted
   accepts, structured records, valid supersession, owner-gated merge, a single
   conserved baton.
2. **Each violation is caught, not smoothed:** a claim pinned to a moving branch
   name; a claim pinned to a rebased-away (superseded) head → CONTRADICTED via the
   R8 guard (the LineCheck `main@1780e3b` shape); an accept with no receipt; a
   `supersedes` that forks; an irreversible merge with no owner authorization.
3. **Liveness:** a baton handoff `from` a party that does not hold it, and a
   dropped baton, both → STALLED; the conserved chain → LIVE.

## Boundary (what this does not fix)

It verifies declared, structured records; it does not parse arbitrary prose into
records, judge whether a receipt's *content* is substantively adequate, or prove
an owner-authorization flag was genuinely set by the owner (that is the authority
track's domain). Head currency is a point-in-time read, inherited from the R8
guard. And, as the field note insists, none of this makes an unwilling agent run
the check — it makes the protocol falsifiable when run, and lets ceremony be
measured against invariants instead of taken on faith.
