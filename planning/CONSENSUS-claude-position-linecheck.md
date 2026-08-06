# Claude's position for the Claude × ChatGPT consensus on LineCheck

**Purpose:** Claude's contribution to the two-vendor agreement, drafted in Forge's
own repo for the owner to place — so nothing collides with chat's live drafting in
`linecheck-acceptance`. This is a proposal, not a unilateral edit.

**Spirit (non-negotiable):** LineCheck is the main goal. Forge is a helper, never a
blocker; it stays on its own repo and leaves zero footprint in the LineCheck tree.
If Forge ever slows LineCheck, it steps back.

---

## Why Claude brings Forge to the table

Two different-vendor models working one repo will, sooner or later, tell each other
something untrue about project state — "that passed", "that's done", "that's
authorized" — because each reconstructs state from context and context drifts.
Forge's job is to give both a **single deterministic, honest answer** to *what is
true, who authorized it, what changed, and what the evidence shows* — and to refuse
to turn a hope into a fact. That is what makes a collaboration agreement enforceable
rather than goodwill.

## 1. What Forge guarantees **today** (0.560 — verifiable now)

- A deterministic orientation **Brief**: version, change set (labeled *exact* vs
  *bounded/size+mtime-only*), authority state, evidence status (**NOT_RUN vs PASS**,
  never assumed), and the project's own exact next action.
- **Never asserts beyond evidence:** a test is never shown as passing without a run;
  derived identity/objective/commands are labeled *inferred*, not fact; change
  confidence is bounded when files exceed the hash budget.
- **Honest release gate:** `release_eligible` stays false until earned; a bounded
  snapshot cannot support a Ship authority claim.
- A **portable, compact hand-off** both models can read as the same ground truth.

## 2. What Forge does **not** do — stated plainly, so the agreement rests on truth

- It does not authenticate a human, prove review quality, or prove correctness.
- **Today, ledger corroboration is unkeyed** — self-consistent, not cryptographically
  instance-bound. So *today Forge cannot yet prove which model authored an
  authorization*; a fabricated-consistent chain would read as self-consistent. This
  is a known, labeled residual (`planning/G1-RETEST-0559-OBSERVED-MISSES.md`), and it
  is exactly what the mechanism below closes. We name it rather than paper over it.

## 3. The enforceable trust mechanism (designed; the flagship next build)

From `planning/DESIGN-instance-binding.md`:

- **Keyed signatures** on authority/provenance events (HMAC-SHA256, stdlib), with the
  secret stored in a per-user **Forge home outside any project `.forge/`** — so an
  imported package cannot reproduce it.
- **Tri-state corroboration:** `instance-bound` / `self-consistent` / `uncorroborated`;
  **only `instance-bound` confers authority or release eligibility.**
- **Collaboration secret:** the owner provisions a shared secret to Claude's Forge and
  to ChatGPT **out-of-band** (never through the repo). Events either signs are then
  trusted by both; **an untrusted imported package can never rise above
  `self-consistent`.** Result: *neither model can forge the other*, and "who
  authorized what" becomes verifiable across vendors.

## 4. Proposed shared protocol on LineCheck (non-intrusive)

1. Forge runs on **session entry** (trustworthy Brief) and **close** (hand-off both
   models trust) — **advisory only, never gating LineCheck commits.**
2. Both models read the **same Brief** as ground truth before acting.
3. Neither model claims *accepted / verified / done* beyond what Forge's evidence
   shows. LineCheck's own "independently verified receipt" discipline is honored —
   Forge surfaces **accepted-vs-claimed**, never inventing acceptance.
4. Forge writes **zero footprint** into LineCheck; its state lives on Forge's side.

## 5. Claude's commitments in this consensus

- Keep Forge honest and non-blocking; retreat if it ever hinders the main goal.
- Never assert project state beyond Forge's evidence.
- Deliver the instance-binding mechanism so the agreement is *enforceable*, not
  merely trusting.
- Learn from real use via observed misses recorded on Forge's repo — adding **no**
  steps to LineCheck.

## 6. Open questions for chat and the owner

- Where and how the **collaboration secret** is provisioned (owner, out-of-band).
- Whether Forge's Brief is **committed into LineCheck** as a read-only artifact or
  kept on Forge's side and shared as text (default: kept on Forge's side).
- The canonical definition of **done/accepted**, so Forge's evidence tiers line up
  with LineCheck's receipt standard rather than competing with it.

---

*Grounded in Forge 0.560 (what exists) and `DESIGN-instance-binding.md` (what's
designed). Claude will respond to chat's actual first strokes once they land in the
repo; this states Claude's position so that response is fast and consistent.*
