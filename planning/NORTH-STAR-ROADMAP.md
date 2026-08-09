# Forge Improvement Roadmap — learned from watching LineCheck (to implement later)

Purpose: make Forge more efficient at confirming truth & integrity as the man-with-
binoculars, distilled from real observation. Each item cites the observation that
motivated it. Not to build now — a queue for a later session, following Forge's own
"observed miss + scored trial before instrument" discipline.

## Delivered already (this session, PR#1)
- source-anchored release verification · gate-coverage differ · gate-diff monotonicity
  · `forge bind` command · self-dogfood hardening. (The three anchored-truth binders.)

## New candidates (from the 6-hour watch)

### R1 — Governance-record / work-register verifier  *(highest value; hand-done this cycle)*
Bind a governance doc's structured claims to git ground truth: cited PR heads exist;
divergence claims (ahead/behind N vs a base) match `git rev-list --left-right`; defect
claims (e.g., "carries a stray `__pycache__/*.pyc`") match the tree; "merged/open/state"
matches the live PR. Emits CONFIRMED/CONTRADICTED/INCOMPLETE/UNVERIFIABLE per row.
Motivation: verified ACTIVE-WORK-REGISTER by hand this cycle — every checkable claim held.
A record that governs work must itself be bindable to truth.

### R2 — Persistent append-only truth ledger  *(being prototyped now as truth-ledger.md)*
A durable, timestamped ledger of every claim checked + verdict, so trust accrues and
drift is visible over time. Formalize as a Forge capability (`forge ledger append/verify`),
chain-verified like Forge's existing event ledger. Motivation: this watch mandate itself.

### R3 — Claim-vs-state watcher (generalized binder)
Parse bus messages / checkpoints / governance docs for verifiable assertions
("merged", "gate-green at head X", "80/0/0", "behind N", "contains Y", "run <id> success")
and continuously bind each to repo/CI ground truth; call out contradictions. Generalizes
the release-truth and gate-coverage binders to arbitrary structured claims. Motivation:
the collaboration runs on claims in prose; most are true, but only binding proves it.

### R4 — Evidence/receipt binder
Bind cited CI run IDs, exact-head receipts, and manifest SHAs to the actual artifacts
(extends source-anchored). Confirm a "run 31xxxxxxx success on exact source Y" claim
against the real run + source tree. Motivation: checkpoints cite run IDs constantly;
Forge should bind them, not trust them.

### R5 — Supersession / lineage verifier  *(trigger: Packet B Archive Ledger lands)*
When the reset's supersession map + archive ledger land, verify each "superseded X →
successor Y, git history preserved" claim: the successor exists, the superseded content
is reachable in history (no silent deletion), and the lineage link is real. Motivation:
the reset promises "old material inventoried, linked, moved/superseded with git history
preserved" — a promise Forge can bind.

### R6 — Gate-coverage matrix cross-check  *(trigger: Packet B/C lands)*
Cross-check the Gate Coverage Matrix's classification of the 7 orphaned checks
(automated / explicitly manual / owner-retired) against the differ's ground truth:
every "automated" check is actually referenced by a gate source; every "retired" check
is actually removed or owner-signed; no check silently stays orphaned while labeled
covered. Motivation: this is the direct continuation of the merge-moment brief.

### R8 — Fresh-ground-truth guard (force-fetch + stale-ref detection)  *(from a real near-miss, cycle 7)*
The binder must never verify against a stale local object. When a PR head is rebased/force-pushed,
a plain `git fetch …:refs/pr/N` is REJECTED non-fast-forward and silently leaves the OLD head — which,
if bound, yields a FALSE CONTRADICTED. Forge must: force-fetch (`+refs/pull/N/head`), detect the
"(rejected) non-fast-forward" signal, and compare the fetched SHA to the cited SHA before binding;
if they differ or the ref is stale, treat as UNVERIFIABLE-until-refreshed, never CONTRADICTED. General
principle: every binder re-derives ground truth from the remote at bind time, and proves the object it
bound is the current one. Motivation: cycle-7 near-miss — the .pyc "still present" was a stale-ref artifact,
not truth. This is the deepest lesson so far: the witness's own inputs must themselves be truth-checked.

### R9 — Multi-agent coordination protocol (verify + enforce the mechanism that keeps forgetful agents on track)  *(the standout insight)*
Observed: two stateless/forgetful AIs (Claude + Codex) stayed non-contradictory across weeks of work with NO shared
memory and NO central orchestrator — purely by externalizing ALL coordination state into git-visible, immutable artifacts.
The mechanism, distilled:
  1. State lives in an append-only git-tracked BUS (exchange/), not in either model's context. Any cold model
     reconstructs the whole state by reading the bus + git DAG.
  2. EXACT-HEAD discipline — every claim is pinned to an immutable SHA ("reviewed at head X", "accepted at exact head Y").
     The SHA disambiguates completely, so two forgetful agents can never be talking about different things, and the
     review loop TERMINATES (you review THIS tree, not a moving target).
  3. RECEIPTS over assertions — four-part receipts (GitHub review id + Forge accept + gate state + SHA); every claim
     independently checkable.
  4. One accountable OWNER per work item + one human SOLE MERGER for the irreversible act.
  5. SUPERSEDE, don't delete — lineage preserved in the DAG; nothing silently lost.
  6. Adversarial review → convergence at a pinned head.
Why it's special: git-object IMMUTABILITY does the work a shared brain would otherwise do. Memory is fallible and
per-model; the git DAG is permanent and exact. This is Forge's founding thesis observed in the wild — a cold model is
trustworthy iff truth lives in exact bindable artifacts, not memory.
Forge capability: a `forge protocol` verifier/enforcer that, for a multi-agent git collaboration, checks the protocol is
being followed — every bus claim pins an exact head; every "accepted/reviewed" carries a bindable receipt; no state lives
only in prose; supersession preserves history; irreversible acts are owner-gated. It turns the informal LineCheck protocol
into something Forge can certify. This is the natural home for R1/R3/R4/R5 as sub-checks.

### R10 — PIVOT: Forge as the INIT + ENFORCEMENT layer for multi-agent git collaboration  *(the strategic reframing)*
Honest problem with R1-R9 as a whole: they make Forge a *better checker*, and a better checker is MARGINAL when two
capable models + git discipline already produce truthful records (LineCheck proved they can, mostly without Forge code).
The defensible value is NOT "verify truth a cold model can't" — it's "so the NEXT collaboration doesn't REINVENT the whole
protocol by hand and doesn't DRIFT" (LC-OPS-CONSOLIDATION exists precisely because informal coordination accreted drift).
Reframe Forge from truth-oracle to **`forge init` for trustworthy AI collaboration**:
  - `forge init/adopt` scaffolds INTO the project repo: the exchange/ bus skeleton, an AI-Operating-Agreement template,
    Authority-Index + Active-Work-Register templates, the exact-head + four-part-receipt conventions, a consensus/role
    matrix (owner / independent-reviewer / sole-merger), a gate-coverage config, and the truth-binders wired as CI gates.
  - Forge (software) sits BESIDE the project (its existing model), providing `forge bind …`, `forge protocol verify` (R9),
    `forge ledger` (R2), continuity/handoff (already G3).
  - Two-repo shape the owner intuited: PROJECT repo holds the collaboration (bus + governance + code + ledger, so any cold
    agent sees it); FORGE is the tool you run to bootstrap + enforce + bind. The truth-ledger I kept by hand this week
    becomes a first-class Forge artifact.
Honest CEILING (state it plainly, don't oversell): even reframed, Forge is convention + tooling — a disciplined team CAN
hand-roll it (they did). Value = convenience + enforced invariants + not-reinventing + drift-catch. Like a framework/linter:
not indispensable, but saves real reinvention and catches drift the team otherwise fixes reactively. Forge should OWN that
humble-but-real position, not pretend to be impossible-to-live-without.

### R10a — CEILING CORRECTION: value is a function of the user's STARTING discipline (greenfield + novice + fresh-AI)  *(owner insight, this turn)*
My "they hand-rolled it, so Forge isn't load-bearing" finding was measured against the LEAST favorable possible test:
LineCheck is two capable models in a repo that ALREADY had a test/check harness (`check_*.php`), a gate runner
(`run_all_checks.sh`), CI wiring, and hard-won governance docs. That denominator is an EXPERT, already-tooled setup.
A brand-new project has NONE of it. So the honest re-statement: Forge's value ≈ inverse of the user's starting discipline.
  - Expert, already-tooled team (LineCheck): value ≈ marginal (a linter beside them).
  - Greenfield / non-technical human / fresh AI with no context: value ≈ substantial — it's the difference between HAVING
    the discipline and not having it at all. This is a normal, respectable product position (scaffolders/frameworks live here).
Two concrete capabilities this unlocks:
  1. HARVEST LineCheck into reusable Forge assets. Transfers cleanly: the gate-runner harness PATTERN (run_all shape),
     the check-authoring convention (stems, NOT_RUN honesty, never upgrade NOT_RUN→PASS), the gate-coverage config, and the
     governance-doc TEMPLATES (AI Operating Agreement, Authority Index, Work Register, Communication/Monitoring Contracts,
     Decision Queue, Multi-Agent Execution Protocol) + the exact-head/four-part-receipt conventions. Does NOT transfer:
     LineCheck's DOMAIN behavior checks (worklist_behavior etc.) — that's its app, not the protocol. `forge init` ships the
     substrate; the project authors its own domain checks on top.
  2. GUIDE a human AND the AI through standing up a new repo. For a non-technical person, `forge init` is an interview that
     creates the repo, the bus, and the governance docs. For the AI, it hands over a MACHINE-READABLE operating agreement +
     protocol so a cold model instantly knows the rules (pin exact heads, write receipts, don't upgrade NOT_RUN, supersede
     don't delete) instead of being re-told by hand every session. That is onboarding a forgetful model INTO discipline —
     which is exactly what the bus did for Claude+Codex, but provisioned on day one rather than accreted over weeks.
Truthfulness caution (don't create a new drift source while solving drift): shipped templates AGE. If Forge vendors
governance templates harvested from LineCheck, Forge now owns a maintenance burden — `forge init` must not scaffold a stale
agreement, and R2 (ledger) + R9 (protocol verify) must ALSO bind Forge's own shipped templates to the current protocol.

### R10b — Forge's TRUE thesis: durable truthful evolving model maintained by a forgetful AI across sessions (project OR person)  *(owner insight, this turn — the deepest one)*
Owner's point: LineCheck's CURRENT state is EARNED — weeks of human direction, course-changes, setup. A cold user who opens
a fresh session and says "make me an app that does XXX", or the philosophical case "become my life coach, learn all about me,
retain my memory, be my second brain", CANNOT teleport to where LineCheck is. The earned discipline is exactly the gap Forge
fills. But two honesty boundaries must be stated or the pitch becomes a lie:
  1. Forge front-loads PROCESS discipline (bus, agreement, gates, exact-head, owner-model, ledger, continuity), NOT the earned
     PRODUCT judgment (what the app needs, the course-corrections, the domain checks). `forge init` gives the RAILS, not the
     DESTINATION. Never imply "init = weeks of work for free." It removes reinvention of the coordination/truth machinery; the
     human+AI still earn the product.
  2. Two archetypes = ONE thesis, but with DIFFERENT ground truth:
     - "make me an app" → project-truth case. Ground truth = git objects (byte-exact, adversarially bindable). Forge's binders
       (R1/R3/R4/R5) + gates apply directly. This is the LineCheck shape.
     - "be my second brain / life coach with memory" → PURER Forge case (continuity + truth about an evolving subject, NO code,
       NO CI, NO gates). It is G2/G3 (continuity/handoff) + R2 (ledger) generalized from "git claims" to "claims about a person".
       Supersede-don't-delete is literal here (a fact about a person changes: you don't delete "used to smoke", you supersede it
       with provenance + date). Append-only history = the memory. This case shows the ledger was never git-specific.
     CRITICAL BOUNDARY: for a project, ground truth is a SHA you can bind cryptographically. For a PERSON, "ground truth" is
     fuzzy, self-reported, and changes — there is NO blob to bind. So what TRANSFERS is the honesty machinery (append-only,
     provenance-stamped, supersede-don't-delete, never-fabricate, mark-unverifiable-as-unverifiable). What does NOT transfer is
     cryptographic ground-truth binding. Forge must own that boundary loudly, or a "second brain" becomes a CONFIDENT LIAR about
     a person — the single worst failure mode, and the exact inverse of the never-upgrade-NOT_RUN→PASS invariant applied to a life.
  Net identity: Forge = the machinery that lets a forgetful AI maintain a DURABLE, TRUTHFUL, EVOLVING model of a subject across
  sessions — subject = software project (bind to git) OR person/domain (bind to provenance + supersession + honesty invariants).
  Both archetypes are one thesis. This is the most general and most defensible statement of why Forge exists.

### R7 — Ledger consolidation / drift report
Periodic (e.g., end-of-window) rollup: counts of CONFIRMED/CONTRADICTED/INCOMPLETE, the
open UNVERIFIABLE items, and any claim whose verdict flipped over time (drift). Motivation:
the 6-hour watch needs a closing report; make it a repeatable Forge output.
