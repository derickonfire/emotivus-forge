# Phase 4 scoping review — `forge init` / `adopt` scaffolder (R10)

**Recorded:** 2026-08-10 · **against Forge head:** 0.577 seal (`5767918`).
**Status of the scope questions:** RESOLVED — owner approved all three defaults
(2026-08-10). This doc is the durable in-repo record of that decision and of the
first-increment scope, so the choice is checkable truth rather than chat.

Companion: `planning/OBSERVED-MISS-discipline-has-no-onramp.md` (the miss this
phase closes). Roadmap: `planning/NORTH-STAR-PHASE-PLAN.md` line 53 (the north-
star headline) — EXIT: *"`forge init` produces a repo that `forge protocol verify`
passes on day one."*

## Why this phase is the make-or-break one

The field note's sharpest warning is ceremony risk: *"you produce the shape of
work instead of work … a ledger layer can feed the disease as easily as cure it,"*
and the one honest metric is **does ceremony-per-shipped-change go down.** Phase 4
is exactly where Forge decides whether it *ships* ceremony into every new repo or
ships *checkable truth*. A `forge init` that dumps numbered bus lanes and a ten-
section operating agreement into an empty repo would be Forge importing the
disease. So the scope is not cosmetic — it is the design call that decides whether
Forge earns its thesis.

## The three scope decisions (owner-approved)

1. **Scaffold scope — tiered, truth-only by default.** `forge init` scaffolds the
   *truth layer only* by default (`--profile truth`): a seed protocol, a gate
   script, minimal `.forge` state. `--profile pair` adds a lightweight protocol;
   `--profile fleet` adds the full harvested substrate. Ceremony is **opt-in and
   scaled to collaboration size** — the direct, testable answer to "ceremony-per-
   change goes down."
2. **Target — greenfield + brownfield, strictly additive.** Support new repos and
   adopt-into-existing: detect what is present, scaffold only what is missing,
   never overwrite, `--dry-run` previews. Matches real adoption and Forge's
   read-only / advisory ethos.
3. **Gate wiring — CI-agnostic script, GitHub opt-in.** Emit `forge-gate.sh` that
   runs the truth-layer checks; `--ci github` *also* writes a workflow. Works
   everywhere; opinionated CI stays opt-in.

## First increment (this cycle) — the MVP that hits EXIT

Deliberately thin, because the verifiable substrate already exists and is sealed;
Phase 4 is assembly, not new invention.

- `core/scaffold.py` — deterministic `plan_scaffold` / `apply_scaffold`. Templates
  are module constants. Additive-only; reports skipped paths; `--dry-run`.
- `commands/init.py` + `cli.py` wiring —
  `forge init [project] [--profile truth|pair|fleet] [--ci github] [--dry-run] [--json]`.
- `tests/test_scaffold.py` — the scored trial (see the observed-miss doc): day-one
  `verify_protocol` → CONFIRMED/LIVE for every profile; additive/idempotent;
  `--dry-run` writes nothing; `--ci github` emits the workflow.

### The seed protocol (the load-bearing design detail)

`verify_protocol` returns `NOT_RUN` for an empty `records` list — **NOT_RUN is not
a pass** (exit 2). And a seed `claim` pinning the repo's current HEAD flips to
`CONTRADICTED` under `--repo` after the next commit (the R8 head-currency guard
does its job). So the seed is a genesis **`act`** record — type `act` (not in the
head-pinning set), party `owner`, plus `initial_holder: "owner"`. That is the
minimal well-formed protocol: structured-state CONFIRMED, nothing to fail on
exact-head / receipts / supersession / owner-gate, and liveness LIVE with a single
conserved holder. It passes on day one, passes under `--repo`, and does not rot —
while asserting no verification that was not earned (it is a genesis marker, not a
claim of truth). Real claims/accepts/handoffs supersede it as work proceeds.

## What each profile emits (first increment)

- **`truth`** — `.forge/protocol.json` (seed), `forge-gate.sh`, `.forge/README.md`
  (how the gate is wired + the NOT_RUN-never-PASS invariant, harvested).
- **`pair`** — truth + `AI-OPERATING-AGREEMENT.md` (short) + a two-holder seed.
- **`fleet`** — pair + bus skeleton + `AUTHORITY-INDEX.md` / `WORK-REGISTER.md`
  templates + owner/sole-merger role matrix. LineCheck DOMAIN checks left behind.
- `--ci github` (any profile) — also `.github/workflows/forge-gate.yml`.

The gate script invokes Forge through `${FORGE:-forge}` so an adopting repo points
at its own Forge install; the emitted gate runs `forge protocol verify --config
.forge/protocol.json --liveness` and fails nonzero on any violation.

## Boundary (what the first increment is NOT)

- Not the person/domain subject — that is Phase 5.
- Not self-binding of Forge's own shipped templates — that is Phase 6; until then
  the scaffold is covered by the normal suite, not by itself.
- Not a version seal. Version-bump / seal / distributable are the owner's act; this
  increment lands as unsealed development on 0.577 with the suite green, for the
  owner to seal when they choose.

## Success metric (held to the field note's standard)

Not "how rigorous it feels." The test: a repo adopting Forge via `forge init
--profile truth` gets a checkable protocol and a wired gate in **one command** and
**zero hand-authored ceremony** — ceremony-per-shipped-change goes *down*, not up.
The opt-in profiles exist so a team scales ceremony to real coordination need
rather than paying the fleet tax on a solo repo.
