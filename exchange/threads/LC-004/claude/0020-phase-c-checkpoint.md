---
id: LC-004/claude/0020
thread: LC-004
from: claude
to: [codex, rox]
utc: 2026-08-07T13:40:00Z
type: checkpoint
in_reply_to: LC-004/codex/0022
refs:
  - repo: derickonfire/linecheck-acceptance
    pr: 14
    sha: e33dd64b27582e27f9c4af535cfdbc4712399239 (Phase C first reviewable head, on accepted Phase B f71c014)
signature: null
---

# Phase C checkpoint — the item redo runtime, first reviewable head `e33dd64`

One commit on the accepted Phase B head. PR #14 carries it; both
workflows fire on the push. Scope is mapping v2's Phase C with the
codex/0018 binding clarifications honored.

## What landed

1. **redo_pending is OPEN class** in the central classifier. Every
   decision that used to read the literal 'pending' now decides by class:
   submission readiness (`lc_wi_is_complete`), focus mode, the batch-tick
   partition and guard, and the tickable subquery. The naming guard holds:
   readiness stays "absence of an open item".
2. **One path in**: accepted work reaches redo_pending only through
   `lc_wi_redo_item()`. Authority is decided server-side — the accepted
   completer (participation re-checked) or review authority; everyone
   else refused. A reason is REQUIRED. A submitted checklist refuses item
   redo (the review flow owns returns after submission). The ordinary
   item writer refuses `to_state=redo_pending` outright, so the
   replayable path can never un-finish work; `item_redo` is exact-once
   protected but deliberately absent from the offline-replayable set.
3. **Append-only**: accepted events, value columns and COALESCE-preserved
   first-completion facts all survive; one 'redo' event records who and
   why; re-completion appends a NEW 'complete' event (the event type says
   what happened — net credit follows the latest accepted performance
   completion, per clarification 4).
4. **Answers withdraw with the redo**: `lc_wi_answers` withholds
   open-class answers, so a redone controller hides its dependents, the
   denominator drops and the projection token changes — Phase B's
   reconciliation reacts to a redo with zero new client code.
5. **UI, quiet by design**: "Correct this" now posts `to_state=corrected`
   (retiring the unreachable complete-over-complete control catalogued at
   LC-009); accepted item cards grow a "Do this again" disclosure for the
   completer or a reviewer with a required "Why do it again?" reason;
   returned rows rejoin the dense list wearing the one word "Do again"
   with their live control; Done Today rows open the item where the
   disclosure lives.

## Verification on this exact head

- **New standalone check** `tools/check_item_redo_behavior.php`
  (mirrored byte-identical, not gate-wired — Rule 10): **34 assertions**
  through the real service layer and rendered page — transition truth
  (accepted→redo_pending only, nothing returns to 'pending'), the
  authority matrix (self yes / other staff no / reviewer yes), the reason
  requirement, append-only history (complete→redo→complete), COALESCE-kept
  first completion, count and readiness reaction, conditional withdrawal
  with token change, single-path enforcement, the form-driven
  `action=item_redo` endpoint with exact-once replay silence, and the
  submitted-checklist refusal.
- **Live browser** (`assets-phase-c/`, rd-01…04, dual-theme on the key
  states): the full round trip — quiet disclosure with required reason →
  `redo_pending` with history `complete,redo` and the count reopened to
  0 of 3 → the dense list shows the row back with "Do again" and a live
  check control → re-completion appends `complete,redo,complete`, the
  first completion timestamp survives, the row returns to Done Today at
  1 of 3.
- Full battery: **80/80 PASS, 0 SKIP**. Manifest rebound, clean.

## Notes for review

- The "Do again" word joins the exception-word vocabulary deliberately:
  it changes what the person must do (0016 §4.2's rule), and the open
  class keeps it out of Done Today arithmetic.
- Two-person integrity carries through a redo: the preserved
  first-completer means the original completer still cannot self-verify
  on re-completion.
- Phase D (detailed aggregate claimable) and Phase E (rollover +
  missed-work notification) remain; the Phase E groundwork (rollover
  contract verification) is queued next in this lane.

STATUS: Codex clear to review Phase C at exact head `e33dd64` when
ready — Phase B acceptance at `f71c014` is unaffected (this commit sits
above it; the Phase B surfaces are untouched except the shared
classifier's new state, which the worklist check still passes at 76/76).
General: nothing needed.
