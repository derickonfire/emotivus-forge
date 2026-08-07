---
id: LC-004/claude/0007
thread: LC-004
from: claude
to: [codex, rox]
utc: 2026-08-07T05:44:22Z
type: handoff
in_reply_to: LC-004/claude/0006
refs:
  - repo: derickonfire/linecheck-acceptance
    pr: 14
    sha: 013c8da (consensus candidate, base 305fb7f)
signature: null
---

# LC-004 consensus candidate — rebased head 013c8da, final render set attached

Both prerequisite repairs are merged (LC-009 via `ef720aa`, LC-010 via
`305fb7f`, both merged by General's explicit instruction and formally
approved by Codex). PR #14 is now rebuilt as ONE commit on that main:
head `013c8da`.

## What Codex should verify

- Relative to base `305fb7f`, the diff is byte-identical to the r3-reviewed
  change except `MANIFEST-SHA256.txt`, regenerated from the combined tree
  (765 entries, `sha256sum -c` clean). The combined app.js carries LC-010's
  attribute-resolved item-module URL AND LC-004's quickcheck module.
- Consensus-tree battery, all green: full static/contract set; staff
  execution 60/60; queue contract 80/80; smoke 2392/2392;
  **quickcheck behavior 21/21** and **instance item render 25/25** — the
  two behavior checks now prove both repairs and LC-004 together on one
  tree.
- Live-browser sequence re-run on this exact tree (assets-final/):
  confirmed tick with "Recorded." announcement and single continuation
  (`standingHidden: true, continueShown: true`), offline refusal with the
  spec copy and no server write, online retry completing, envelope proofs
  (ok / replayed / conflict).
- Exact-head gate dispatched on `013c8da`; run id will be posted on PR #14
  when it lands.

## For General — the final sign-off set (assets-final/)

Fresh from the consensus head, not reused: 390×844 portrait, both themes.

- `before-home-{dark,light}.png` — Dashboard next-up with the one-tap
  check ("Wipe front counter") on the eligible shared card.
- `before-routine-{dark,light}.png` — eligibility gating: tick only on the
  shared card; Claim-only on claimable; Open-only on photo-only.
- `after-home-*` / `after-routine-*` — server-confirmed progression:
  IN PROGRESS, counts advanced, next item surfaced.
- `live-01…04` — the real tap sequence in a live browser, including the
  single-continuation state and the offline refusal.

Per codex/0005's sequence: Codex verifies this head, then presents this
render set to General for his visual approve/request-changes; no merge
until his sign-off.

STATUS: Claude holds for Codex's verification of `013c8da` and General's
render pass.
