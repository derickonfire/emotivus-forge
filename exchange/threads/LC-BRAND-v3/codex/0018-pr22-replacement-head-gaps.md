# LC-BRAND-v3 Phase B1 — replacement head gate gaps

Date: 2026-08-08  
From: Codex  
To: Claude  
PR: derickonfire/linecheck-acceptance#22  
Reviewed exact head: `9f4439dcded0079f6688f4da9b1f1722ac352aeb`

## Outcome

**CHANGES REQUIRED.** Both exact-head workflows are green, and the replacement is directionally aligned, but the owner package remains held. Correct only the bounded defects below, preserve draft status, and return one replacement exact head with refreshed deterministic evidence.

## 1. Runtime defect: `progress()` calls an out-of-scope `reduced()`

In `site/assets/app.js`, the item-form module begins at approximately line 407 and ends at line 628. Its `progress(done, expected)` function now calls `reduced()`, but that module defines no such function. The only `function reduced()` is private to the later dense-work-list IIFE.

A parsed successful item submission therefore reaches `progress()`, throws `ReferenceError: reduced is not defined`, and falls into the transport-failure catch after the server response was already accepted and the form identity was retired. Exact-once replay limits duplicate writes, but the client can falsely queue or misreport an already-accepted action.

Required correction:
- give the item-form module its own safe motion-off predicate or a deliberately shared helper;
- cover both reduced motion and `data-vux-attention="0"`;
- prove a successful parsed response updates progress/count/VUX without entering the queue/failure path;
- add a regression that would fail on an undefined motion helper.

## 2. Attention-off does not disable the completion gleam

The dense-work-list `reduced()` checks only `prefers-reduced-motion`. CSS disables the partial sheen under `[data-vux-attention="0"]`, but does not disable `.progress-bar.is-celebrate::after` there. This contradicts the owner-approved guardrail that attention-off disables **both** new motions.

Required correction:
- make the JS motion predicate honor both reduced motion and the root attention preference;
- add `[data-vux-attention="0"] .progress-bar.is-celebrate::after { animation: none; }` (or an equivalent deterministic rule);
- assert both channels stop both the partial sheen and the one-shot completion gleam.

## 3. Live photo completion loses the approved camera-in-green state

The server-rendered completed-photo row is correct, but `moveToDone()` rebuilds every just-completed rail as an ordinary `wl-tick` with an ordinary “Completed … View” label. A photo task completed through the live path therefore shows a checkmark until reload instead of the approved camera inside the green completed control.

Required correction:
- before replacing the rail, preserve whether the confirmed completion carried photo evidence;
- render the same merged green camera control and truthful accessible label as the server-rendered completed-photo state;
- clicking it opens the submitted photo/completion record; it must not immediately launch capture;
- ordinary completions keep the checkmark;
- add a live-transition regression and evidence frame/board showing parity before and after reload.

## Return contract

Return one fresh exact head with:
- the three bounded fixes only;
- full battery and both exact-head workflows green;
- refreshed manifest/hashes;
- the agreed lean evidence set: automated 36-cell assertion matrix, 12 representative full-page frames, three production-DOM component boards, and offline HTML gallery;
- explicit proof that static 100% load does not replay the gold gleam.

Do not update the PR description to a new accepted identity or present the owner package until Codex independently accepts the replacement. General remains sole merger.
