# Observed miss — the truth+protocol discipline has no one-command on-ramp

**Type:** observed miss (adoption / ceremony-per-change) · **Recorded:** Phase 4 (R10)
**Trial status:** DELIVERING this cycle — scored trial encoded as a test (see below).
Instrument: `core/scaffold.py` + `forge init`.

## What happened (the field note talking back)

The LineCheck Independent Reviewer's field note
(`planning/FIELD-NOTE-linecheck-reviewer-on-adopting-forge.md`, against Forge
0.576) is the clearest statement of this miss, and it is blunt on purpose:

- *"The value is the **discipline** (bind claims to ground truth; never turn a
  hope into a fact; carry state across cold sessions), not the software."*
- *"It only becomes a **reduction** in ceremony when the binders re-derive the
  claims automatically. Today they don't."* The reviewer appended nine ledger
  entries **by hand** — more typing than the prose already written.
- *"This project already carries numbered bus lanes, four-part receipts, a
  ten-section communication authority, Packets A/B/C, amendment ledgers,
  supersession maps. Bolting a ledger layer onto that can **feed** the disease
  as easily as cure it."*
- The single honest metric: **"does ceremony-per-shipped-change go down?"**

By Phase 3 the discipline is real and checkable: `forge bind` (four binders) and
`forge protocol verify` (six invariants) deterministically re-derive claims and
certify a coordination protocol. But **there is no way to plant that discipline
into a project in one step.** An adopter who wants the exact-head / bindable-
receipt / owner-gated / single-baton protocol has to hand-author the config, hand-
wire a gate, and hand-write the operating conventions — i.e. rebuild the very
ceremony the field note warns is the original disease. The discipline exists; the
*on-ramp* does not.

## The miss (the product gap)

Forge can **check** a protocol (Phase 3) but cannot **establish** one. That gap
has two costs, both of which the field note predicts:

1. **Adoption is all manual discipline.** Every adopter re-implements the truth
   layer by hand. Hand-built ceremony is unfalsifiable until someone also hand-
   wires the checker — and most won't. The tool that sells "ceremony down" ships
   with a hand-assembly requirement that drives ceremony *up* on day one.
2. **The discipline is not self-demonstrating.** Nothing produces a repo where
   `forge protocol verify` passes out of the box, so a cold agent has no concrete,
   already-checkable example of the shape it is supposed to follow — only prose
   describing it, which is the exact "state lives only in prose" failure Phase 3
   was built to catch, reintroduced at the adoption boundary.

This is the north-star headline phase precisely because closing it converts the
discipline from *a thing you must assemble* into *a thing you can plant and
immediately falsify*.

## The instrument (what is being built)

`core/scaffold.py` — `plan_scaffold(target, profile, ci)` / `apply_scaffold(plan,
dry_run)` — deterministically emits Forge's truth+protocol layer into a project
repo, **strictly additively** (never overwrites; reports every skipped path),
with `--dry-run` preview. Three profiles keep ceremony **opt-in and scaled to
collaboration size** — the direct answer to the ceremony-per-change metric:

- **`truth`** (default): the truth layer *only* — a seed `.forge/protocol.json`,
  a CI-agnostic `forge-gate.sh`, and a short note wiring the gate. No bus, no
  operating agreement, no registers. The anti-ceremony default.
- **`pair`**: truth + a short two-party operating agreement and a two-holder seed.
- **`fleet`**: pair + the harvested LineCheck substrate (bus skeleton, Authority-
  Index + Work-Register templates, owner/sole-merger role matrix). The DOMAIN
  checks LineCheck ran are deliberately left behind; only the reusable gate-runner
  pattern and the NOT_RUN-never-PASS invariant are harvested.

Gate wiring is CI-agnostic by default (`forge-gate.sh`); `--ci github` also emits
a workflow. Both greenfield and brownfield are supported; brownfield is additive
and previewable.

The seed protocol is the load-bearing detail: an empty protocol is `NOT_RUN`
(not a pass), and a seed that pins today's HEAD would flip to `CONTRADICTED`
under `--repo` after the next commit. So the seed is a genesis **`act`** record
(non-head-pinning) plus `initial_holder` — the minimal well-formed protocol that
earns `CONFIRMED`/`LIVE` on day one and does not rot, while claiming no
verification that was not earned.

## Scored trial (the EXIT criterion, encoded as a test)

Roadmap EXIT for Phase 4: **"`forge init` produces a repo that `forge protocol
verify` (Phase 3) passes on day one."** The trial:

1. **Day-one pass.** Scaffold each profile into a fresh temp git repo; run
   `verify_protocol` on the emitted `.forge/protocol.json` with `check_liveness`
   → **CONFIRMED / LIVE** (exit 0). Also with `--repo <that repo>` → still
   CONFIRMED (the genesis `act` pins no head, so head-currency has nothing to
   fail on).
2. **Additive / idempotent.** A second `init` over the same tree writes nothing
   (every path skipped); `--dry-run` writes nothing; an existing `.forge/` file
   is never overwritten.
3. **Profiles.** Each profile emits exactly its declared file set; `--ci github`
   additionally emits the workflow.

## Boundary (what this does not do)

It scaffolds a *code project* (Phase 5 is the person/domain subject). It does not
bind Forge's OWN shipped templates to the current protocol — that self-binding /
anti-drift guarantee is Phase 6, and until it lands the scaffold is checked by the
same test suite as everything else, not by itself. It plants a falsifiable protocol;
it cannot make an unwilling agent run the gate — as the field note insists, tooling
raises the floor for honest-but-sloppy agents and does nothing for unwilling ones.
Version-bump / seal / distributable remain the owner's act.
