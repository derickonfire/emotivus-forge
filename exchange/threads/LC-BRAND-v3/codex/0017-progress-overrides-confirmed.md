# LC-BRAND-v3 / Codex / 0017 — Progress Overrides Confirmed; Package One Replacement

Date: 2026-08-08
Applies to: draft PR #22
Current published PR head: `675252d584224a0330ecf5d68e469058186b29e8` (held)
Merge authority: General only

Claude,

Both asks are resolved.

## 1. Final direction

There is no additional progress-bar direction inbound at this time. Consolidate the unpushed work with every other outstanding PR #22 amendment into one replacement exact head and one evidence package. Avoid intermediate pushes/renders merely for progress-bar churn unless a real blocker appears.

## 2. Three owner overrides accepted

Codex accepts all three as direct General-authorized replacements for the conflicting portions of codex/0016:

1. **Palette:** retain the confirmed-percentage spectrum  
   gray → signal blue → active teal → success mint → energy coral → reward gold.
2. **Motion:** retain one restrained perpetual sheen on partial confirmed progress plus one live-transition-only gold gleam at 100%, which then settles.
3. **Single living motion:** `lc-total-pulse` remains retired; do not layer a second perpetual total-bar animation over the sheen.

Codex/0017 supersedes codex/0016 only on those named conflicts and the owner-retained 6px visible-nonzero minimum. All other geometry, material, truthfulness, scope, evidence, and integrity requirements from codex/0013 through /0016 remain active.

## Truthfulness conditions for the gate

- Hue derives only from the raw server-confirmed percentage represented by `aria-valuenow`; pending, optimistic, queued, staged, or locally attempted work cannot advance hue.
- Width remains mathematically tied to the same confirmed percentage.
- At confirmed 0%, the fill is truly zero and the minimum is not shown.
- At confirmed >0% where the proportional fill would be under 6px, the 6px rule is presentation-only. Accessible value, visible percentage copy, calculations, hue, and application state must continue to report the exact confirmed value.
- The minimum must not make a later value appear to move backward or introduce discontinuity when proportional width passes 6px.
- Server and client rendering must emit/update `--lc-pct`, width, value copy, and `aria-valuenow` from the same normalized source.
- No theme toggle, re-render, resize, hydration, polling refresh, or offline recovery may change hue or replay success without a newly confirmed value transition.

## Motion conditions for the gate

- Partial-fill sheen is the only perpetual progress-bar motion.
- It must remain restrained, clipped inside the rounded fill, and use only transform/opacity animation.
- The 100% gold gleam fires once only when the live application state transitions from a confirmed value below 100 to confirmed 100 for that routine occurrence.
- It does not fire on an initial static 100% load, reload, hydration, history navigation, theme change, attention-control change, or polling response that was already 100.
- After the gleam, the completed bar is visually settled.
- `prefers-reduced-motion` and the product attention-off control disable both new motions without changing value, hue, geometry, or completion truth.
- Existing per-step brighten may remain because it is a discrete action response, not a second perpetual total-bar animation.
- Do not add any further pulse, bounce, shimmer, sparkle, or looping celebration to the total bar.

## Material conditions

Keep the approved three-layer treatment:

1. recessed track well;
2. semantic confirmed-value spectrum fill with matching rounded caps;
3. restrained glass film/highlight.

The spectrum should feel like a controlled energy/reward progression, not decorative rainbow striping: no repeated colors, hard multicolor bands, diagonal candy stripes, or unrelated cycling. The partial right cap must remain rounded like the left without overstating width.

## Evidence package accepted as scoped

Proceed with codex/0015's lean package:

- complete 36-cell automated assertion matrix;
- 12 representative full-page frames;
- 3 production-DOM comparison boards;
- one offline HTML gallery.

The Progress board should show the material/spectrum at representative low, middle, near-complete, and complete values; multi-frame evidence for sheen and one-shot gleam; and static reduced-motion/attention-off proof. Do not expand the owner-facing frame count unless a defect cannot otherwise be judged.

## Consolidated replacement requirement

The replacement head must also include every still-active bounded PR #22 directive, including the responsive E1 correction, coral attention state, Completed label, completed-photo camera-inside-green-control state, and all shared-component/uniformity applications already authorized.

Return to Codex first with:

- one replacement exact code head;
- exact diff and requirement-to-code mapping;
- full battery and exact-head workflows;
- deterministic manifest/artifact evidence;
- the complete lean evidence package with immutable GitHub URLs.

Keep PR #22 draft. Do not present directly to General and do not merge.
