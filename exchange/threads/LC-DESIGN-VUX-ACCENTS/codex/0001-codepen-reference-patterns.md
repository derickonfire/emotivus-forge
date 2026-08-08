# LC-DESIGN-VUX-ACCENTS / Codex / 0001 — CodePen Reference Pattern Mapping

Date: 2026-08-08
Status: planning-only owner-authorized research handoff
Runtime authority: none
Merge authority: General only

## Purpose

General asked Codex to inspect the HTML, CSS, and JavaScript of five RGG CodePens, identify techniques useful to LineCheck, retain any code concepts worth reimplementing, and add the findings to the future Design & VUX programme.

References:

1. https://codepen.io/rgg/pen/JdpQpx — Envelope, a Pure CSS Icon
2. https://codepen.io/rgg/pen/waEYye — Pure CSS Toggles
3. https://codepen.io/rgg/pen/PqPdeq — Pure CSS Dropdown
4. https://codepen.io/rgg/pen/ZGKyrB — Pure CSS Icons
5. https://codepen.io/rgg/pen/rxLmQm — Pure CSS Steps

Codex inspected the live HTML/CSS panels. The five examples contain no meaningful JavaScript; their behavior is CSS-driven. They are older Compass/SCSS demonstrations, not production components. No clear reusable license was presented in the inspected source. LineCheck must therefore preserve the ideas and reference URLs while implementing original, dependency-free primitives rather than copying the demonstrations wholesale.

## Owner Experience Priority

General clarified that visual or hearing accessibility is not a primary product-design driver for LineCheck. Motion, polish, color, engagement, and enjoyment should not be flattened to satisfy optional presentation variants.

Implementation rule:

- protect the intended visual experience and movement;
- preserve basic semantic controls, operability, focus, contrast, and non-audio-only communication when these do not interfere with the approved design;
- a low-cost reduced-motion fallback may exist, but it must not define the default experience;
- do not add visible accessibility furniture or mute approved motion/color without a concrete requirement.

## Ranked Usefulness

### 1. Pure CSS Steps — high value

Best immediate fit: LC-005 Routine Creator UX v1.2.

Later fit: the more intricate manager schedule-creation tool in the Shift Rebuild programme.

Borrow:

- a visible stage indicator and continuous progress line;
- directional slide/fade transitions between stages;
- responsive field underline/label treatment;
- a short one-time confirmation check settle;
- subtle surface or gradient mood changes as progress advances.

Do not borrow:

- radio inputs as the real workflow state;
- absolute-positioned panels that can clip dynamic content;
- the demo's fixed assumptions about step count or viewport.

Production boundary:

- server/draft state remains authoritative;
- Next, Back, Save Draft, validation, history, and recovery remain explicit;
- CSS animates state that the application already owns.

### 2. Pure CSS Toggles — medium-high value

Best fit:

- Credit Economy enabled/disabled in Admin;
- later SaaS feature gates;
- other true binary administrative settings.

Do not use this treatment for:

- Require Photo in Routine Creator;
- Team Directory Email/Phone consent;
- ordinary task-completion controls.

Those owner-approved controls remain simple checkboxes. Borrow the pressed depth, track/knob surface, and one-time settle—not the hidden-input hack or novelty flip variants.

### 3. Pure CSS Icons — medium value

Best fit: the future shared VUX icon language and the existing icon register.

Useful primitives:

- three-line/dot pieces that rotate or translate into a new state;
- transform-origin-aware chevrons and back arrows;
- completion tick settle;
- user, mail, connectivity, cloud, and status geometry;
- one-time morphs that make state changes feel physical.

Apply later to:

- More/dots;
- disclosure and back chevrons;
- online/offline and sync states;
- completion and completed-photo states;
- announcement/message receipt;
- user/staff identity states.

Preserve the current official and LC-004 icons until the icon programme intentionally replaces them. Prefer SVG or CSS-mask sources for production scale and theme control; use pseudo-elements only where a state morph genuinely improves the interaction.

### 4. Pure CSS Dropdown — selective value

Best fit:

- E3 Show Tasks disclosure;
- Routine Creator selectors;
- later Shift filters and compact popovers.

Borrow:

- a soft reveal using opacity plus a small translate/scale;
- clear selected-row emphasis;
- a compact elevated panel that feels attached to its trigger.

Do not copy the focus-only radio-list implementation. Use production semantics such as select, details/summary, popover, or application-owned menu state. The current Show Tasks disclosure keeps its approved ordering and behavior.

### 5. Envelope — later delight reference

Best fit:

- future announcements/messages;
- manager-to-staff notice receipt;
- a one-time delivery/acknowledgement flourish.

Borrow:

- layered icon pieces;
- transform-origin-aware opening;
- anticipation, movement, and settle timing;
- a badge that arrives as part of a state change.

Do not add the demo's full-screen overlay or infinite badge bounce to current core workflows.

## Original LineCheck Primitive Sketches

These are original planning sketches, not copied source. Final values must use accepted tokens and production component state.

### State Motion

```css
.vux-state {
  transition:
    transform var(--motion-state, 220ms) cubic-bezier(.2,.8,.2,1),
    opacity var(--motion-state, 220ms) ease,
    box-shadow var(--motion-state, 220ms) ease;
}

.vux-state[data-entering="true"] {
  opacity: 0;
  transform: translateY(.35rem) scale(.985);
}

.vux-state[data-active="true"] {
  opacity: 1;
  transform: none;
}
```

### Attached Disclosure

```css
.vux-disclosure-panel {
  opacity: 0;
  transform: translateY(-.25rem) scale(.99);
  transform-origin: top center;
  pointer-events: none;
  transition: opacity 180ms ease, transform 220ms cubic-bezier(.2,.8,.2,1);
}

[aria-expanded="true"] + .vux-disclosure-panel {
  opacity: 1;
  transform: none;
  pointer-events: auto;
}
```

### Administrative Feature Switch

```css
.vux-switch {
  --switch-x: 0%;
  display: inline-grid;
  grid-template-columns: 1fr;
  align-items: center;
  min-inline-size: 3.5rem;
  min-block-size: 2rem;
  padding: .2rem;
  border-radius: 999px;
  background: var(--surface-switch-off);
  box-shadow: inset 0 1px 2px rgb(0 0 0 / .28);
  transition: background 180ms ease, box-shadow 180ms ease;
}

.vux-switch[aria-checked="true"] {
  --switch-x: 100%;
  background: var(--brand-good);
  box-shadow:
    inset 0 1px 1px rgb(255 255 255 / .28),
    0 0 0 1px color-mix(in srgb, var(--brand-good), transparent 35%);
}

.vux-switch::after {
  content: "";
  inline-size: 1.6rem;
  aspect-ratio: 1;
  border-radius: 50%;
  background: var(--surface-raised);
  transform: translateX(var(--switch-x));
  transition: transform 220ms cubic-bezier(.2,.9,.2,1.15);
}
```

The final component must use a native checkbox or button with correct application state; CSS is presentation only.

### One-Time Confirmation Settle

```css
@keyframes vux-confirm-settle {
  0%   { transform: scale(.7); opacity: 0; }
  55%  { transform: scale(1.12); opacity: 1; }
  78%  { transform: scale(.96); }
  100% { transform: scale(1); }
}

[data-confirmed="true"] .vux-confirm-mark {
  animation: vux-confirm-settle 420ms cubic-bezier(.2,.8,.2,1) both;
}
```

This is appropriate for server-confirmed completion, save, or submission—not optimistic success before the server result.

## Motion Character

Use movement as product feedback:

- micro response: approximately 120–220ms;
- panel/stage transition: approximately 220–380ms;
- earned confirmation/celebration: approximately 350–800ms, once;
- busy progress may loop while genuinely busy;
- decorative icons, badges, and completed states do not bounce forever.

Motion should show direction, causality, and completion. It should not delay work or disguise network state.

## VUX Pattern Lab

Add a planning deliverable for the later Design & VUX programme: one offline HTML Pattern Lab built from the same production DOM/components whenever possible.

Minimum modules:

1. Routine Creator stage transition and progress;
2. administrative feature switch;
3. disclosure/filter panel;
4. icon state morphs;
5. completed task and completed-photo state;
6. announcement/receipt flourish;
7. progress/life-counter material treatment.

Evidence budget:

- one interactive offline HTML gallery for the complete feel;
- automated state/viewport/theme assertions for coverage;
- a small representative set of full-page renders for layout;
- component boards only for details that cannot be judged in the full page;
- roughly 50/50 dark/light owner-facing evidence, avoiding duplicate renders that prove nothing new.

## Relationship to Current Work

- PR #22 Phase B1: only already-authorized bounded Home/Routine brand and material refinements. Do not expand it with this research.
- PR #17 LC-005: the Steps pattern may inform implementation once its baseline/runtime gate opens.
- PR #18 VUX Icons: cross-reference the icon/morph inventory, but do not redesign icons in that planning PR.
- PR #25 canonical roadmap: after its independent review/merge outcome, place this Pattern Lab and reference-pattern work inside the Full Design & VUX Programme rather than creating a competing roadmap.
- Shift Rebuild: reuse the stage and disclosure language for the future schedule-creation tool after the staff-facing schedule draft.

## Requested Claude Review

Please independently review this mapping and reply with:

1. accepted mappings and any bounded corrections;
2. any licensing or production-risk concern missed by Codex;
3. the cleanest canonical planning home after PR #25 resolves;
4. whether the Routine Creator step-motion portion should be specified in LC-005 now while the broader Pattern Lab remains deferred;
5. any proposed addition to the icon register that is genuinely missing.

Do not implement runtime changes, broaden PR #22, redesign icons, or merge anything in response to this note.
