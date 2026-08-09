# Forge Development — Phased Plan (new North Star)

**North Star:** Forge = the machinery that lets a forgetful AI maintain a DURABLE,
TRUTHFUL, EVOLVING model of a subject across sessions.
  - subject = software PROJECT → bind to git (exact-head, receipts, gates, binders)
  - subject = PERSON/domain → bind to provenance + supersession + honesty invariants
Both archetypes are one thesis. Roadmap items R1–R10b (see forge-improvement-roadmap.md).

**Execution repo:** emotivus-forge (Forge's own repo), on a dev branch, normal PR flow.
NOT Llweb. NEVER touch the LineCheck `exchange/` bus (read-only fetch of origin/main only).
Every phase follows Forge discipline: observed-miss doc → scored trial → instrument;
`python3 -m unittest discover -s tests` green; `forge.py self-test` live count; narrative-
integrity lockstep; runtime-reachability classified. Version-bump / seal / distributable = OWNER.

**Checkpoint protocol:** user says "continue" to advance. At each phase END I reconfirm
where we are + that the remaining phases still make sense. I STOP and ask when a real
decision is owner's (scope, appetite, irreversible or ambiguous choices).

---

## Already delivered (PR #1, branch claude/g1-source-anchored-release — owner to seal)
G1 truth-anchoring: source-anchored release verifier · gate-coverage differ · gate-diff
monotonicity · `forge bind` command · self-dogfood hardening. 575 tests / 61 modules green.

---

## Phase 1 — Truth Ledger  (R2)   ·   FOUNDATION, no external trigger needed
Build `forge ledger` as a first-class capability: append-only, provenance-stamped,
supersede-don't-delete, chain-verified (like Forge's existing event ledger).
Commands: `ledger append` (claim + ground-truth pointer + verdict + provenance),
`ledger verify` (chain + re-bind checkable claims), `ledger show`.
Why first: it's the substrate every later phase records into, and it directly generalizes
the truth-ledger I kept by hand this week. Powers BOTH archetypes.
EXIT: ledger capability shipped + tested + self-dogfooded; the hand-kept ledger's entry
shape is reproducible by the tool.

## Phase 2 — Fresh-ground-truth guard + generalized claim binder  (R8 + R3, folds R1/R4)
(a) Bake force-fetch / stale-ref detection into every binder (the cycle-7 near-miss lesson):
re-derive ground truth from remote at bind time; a rebased/force-pushed head must never yield
a FALSE CONTRADICTED — differ/stale → UNVERIFIABLE-until-refreshed.
(b) Generalize `forge bind` to arbitrary structured claims (claim-vs-state watcher): governance-
record rows (R1), cited run-IDs / receipts / manifest SHAs (R4) become claim types.
EXIT: no binder can be fooled by a stale object; the generalized binder reproduces this week's
hand-done Work-Register / Authority-Index verifications.

## Phase 3 — Protocol verify + enforce  (R9, folds R5)
`forge protocol verify` for a multi-agent git collaboration: every bus claim pins an exact head;
every accept carries a bindable receipt; no coordination state lives only in prose; supersession
preserves history (R5 lineage); irreversible acts are owner-gated. Phase-2 binders = sub-checks.
EXIT: run it against the real LineCheck bus (read-only) and have it certify the protocol the two
AIs followed by hand — no false alarms, catches a deliberately-broken fixture.

## Phase 4 — `forge init` / `adopt` scaffolder + LineCheck harvest  (R10)   ·   NORTH-STAR HEADLINE
`forge init` scaffolds INTO a new project repo: bus skeleton, AI-Operating-Agreement template,
Authority-Index + Work-Register templates, exact-head + four-part-receipt conventions, owner/
sole-merger role matrix, gate config, binders wired as gates. Harvest LineCheck's REUSABLE
substrate into templates (gate-runner pattern, NOT_RUN-never-PASS invariant, governance docs) —
leave LineCheck's DOMAIN checks behind. Two-repo shape.
LIKELY STOP-AND-ASK: template scope / how opinionated the scaffold should be.
EXIT: `forge init` produces a repo that `forge protocol verify` (Phase 3) passes on day one.

## Phase 5 — Person-subject / second-brain track  (R10b)   ·   MOST NOVEL
Generalize ledger + continuity to a NON-code subject: provenance + supersession + honesty
invariants, with the HARD boundary enforced — never smooth a guess into confident recall;
mark unverifiable as unverifiable (the inverse of never-upgrade-NOT_RUN→PASS, applied to a life).
LIKELY STOP-AND-ASK: appetite + scope — this is a new product surface, not just a binder.
EXIT: a subject-ledger that records life-facts with provenance and refuses to fabricate; the
confident-liar failure mode is blocked by a test.

## Phase 6 — Self-binding & anti-drift  (R2/R9 on Forge's OWN templates + R7)
Apply the ledger + protocol-verify to Forge's SHIPPED templates so `forge init` can never
scaffold a STALE agreement (don't become a new drift source while selling drift-prevention).
Ledger-consolidation / drift report (R7): CONFIRMED/CONTRADICTED/UNVERIFIABLE rollup + verdict-
flip detection. Closes the honesty loop.
EXIT: Forge's own templates are bound to the current protocol; drift report is a repeatable output.

---

## Cross-cutting, every phase
- Observer keeps running on 20-min cadence with the new North Star as the lens: keep learning
  from LineCheck, keep the ledger, ping when something contradicts truth OR when LineCheck shows
  a pattern that should feed a phase.
- Don't interfere with LineCheck's bus. Read-only. Owner seals releases.
