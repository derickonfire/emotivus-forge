# Observed miss — a stale ref or superseded head can bind a claim to false truth

**Type:** observed miss (G1 project-truth) · **Recorded:** 0.576→next cycle
**Trial status:** **DELIVERED this cycle** — scored trial passed (see below).
Instrument: `core/ref_integrity.py` (shared head-integrity guard, baked into every
binder) + `core/claim_binder.py` (generalized structured-claim binder emitting
ledger verdicts).

## What happened (LineCheck)

Twice in the LineCheck engagement the observer's ground truth went stale under a
moving branch:

1. The hand-kept observer ledger (whose shape `test_truth_ledger` reproduces)
   records a real near-miss: a reconciled PR head was read as "still shows
   `.pyc`" — **CONTRADICTED** — from a stale local ref; only a force-fetch
   revealed the corrected truth and the verdict had to be superseded to
   CONFIRMED. The false CONTRADICTED was authored by ref staleness, not by the
   project.
2. The `LC-ARCH-1_1/codex/0009` receipt records the mirror case: a PR body kept
   naming an old base/head after the branch had moved, and the review had to be
   re-bound to the current exact head before acceptance.

The binder track (0.576) gates on `git cat-file -t <head>` — object *existence*.
That is necessary but not sufficient, in two distinct ways:

- **A superseded head still exists.** After a rebase or force-push the old
  commit remains in the local object store until gc. A binder pointed at it
  runs happily and verdicts truthfully *about that tree* — but the claim being
  checked is about "the PR / the branch", and rendering CONTRADICTED there is
  false for the claim. Existence lies about currency.
- **A symbolic ref resolves silently to stale truth.** `origin/feature` is a
  local snapshot of remote state. Without a force-fetch it can lag or diverge
  arbitrarily; a binder evaluating it binds the claim to whatever the last
  fetch happened to see, with no record that freshness was never established.

## The miss (the product gap)

Forge's binders could emit a **false CONTRADICTED** (or a false CONFIRMED — the
same defect with a friendlier face) when the anchor ref was stale or superseded,
and nothing in the result recorded that the anchor's currency was unverified.
The core invariant — never upgrade NOT_RUN to PASS — was honoured for *object
absence* but not for *object staleness*. A deterministic oracle that can be
pointed at yesterday's truth and asked to contradict today's is exactly the
"capable-but-wrong model" failure Forge exists to prevent, wearing Forge's own
uniform.

Secondarily: `forge bind` spoke only three hard-wired claim shapes. The
multi-agent protocol work (R9) needs the general primitive — "every claim pins
an exact head; every accept carries a bindable receipt" — as structured claims
whose verdicts land in the truth ledger with reproduce evidence.

## The instrument (what was built)

**1. `core/ref_integrity.py` — one shared guard, baked into every binder.**
`assess_head(repo, ref)` classifies the anchor before any binder logic runs:

- `MISSING` / `NOT_A_COMMIT` — as before, NOT_RUN.
- **`SUPERSEDED`** — an exact SHA that exists but is no longer reachable from
  any local ref or HEAD: the signature of a rebased/force-pushed-away head.
  Binders refuse with NOT_RUN (ledger: UNVERIFIABLE) and say exactly why and
  what to do (`git fetch --force`, re-bind at the current head). Never a
  content verdict, so never a false CONTRADICTED.
- **`STALE_REMOTE_REF`** — a remote-tracking name whose local value differs
  from what the remote reports now (`git ls-remote`): NOT_RUN, with both SHAs
  in the finding.
- **`REMOTE_UNVERIFIED`** — a remote-tracking name whose remote cannot be
  contacted: NOT_RUN. Freshness that cannot be established is not assumed —
  the same rule as NOT_RUN→PASS.
- `FRESH` — an exact SHA reachable from a current ref, or a local name
  (branch/tag/HEAD), which is local truth by definition. Binders proceed.

Config escape hatch `allow_superseded_head: true` exists for deliberately
historical binds (auditing an old head *as* an old head); the head-currency
finding is still recorded so the result cannot masquerade as current truth.

**2. `core/claim_binder.py` — `forge bind claims`.** Structured claims in a
config file, each deterministically evaluated against git ground truth behind
the same guard, each finding carrying its reproduce command:

- `head-equals` — ref R currently resolves to SHA X (the "claim pins an exact
  head" primitive; remote-name freshness enforced).
- `ancestry` — commit A is an ancestor of commit B.
- `blob-identity` — path P at ref X is byte-identical to P at ref Y (or to a
  given blob SHA) — the "verbatim received-source charter unchanged" check from
  the LC receipts, mechanized.
- `file-sha256` — file bytes at an exact head hash to a stated value.
- `file-regex` — file at an exact head matches / captures a stated value.

**3. Verdicts feed the truth ledger.** Every `forge bind` subcommand takes
`--ledger --project <p>`: the binder result is recorded via
`record_binder_result` as a binder-derived entry (schema 2), so CONFIRMED in
the ledger is machine-earned, CONTRADICTED carries its reproduce, and a guard
refusal lands as UNVERIFIABLE — terminal, never upgraded.

## Scored trial

Reproduce the LineCheck failure modes in a real two-repo (remote + clone)
fixture and score the outcome:

1. **Rebased PR head.** Claim bound at head H; branch rebased and force-pushed
   (H superseded, still in the object store). Binder at H must yield **NOT_RUN
   with a SUPERSEDED head-integrity finding — not CONTRADICTED**; with
   `--ledger`, the entry lands **UNVERIFIABLE**.
2. **Stale remote-tracking ref.** Local `origin/feature` lags a remote
   force-push. Binding at `origin/feature` must yield NOT_RUN naming both SHAs;
   after `git fetch --force`, the same bind proceeds to a content verdict.
3. **The false-CONTRADICTED is actually prevented.** The rebased head's tree
   genuinely fails the release-truth check while the current head passes: the
   old code path would have said CONTRADICTED; the guard says NOT_RUN, and the
   re-bind at the fetched current head says CONFIRMED.
4. **Structured claims round-trip.** `head-equals`/`ancestry`/`blob-identity`
   claims evaluate to CONFIRMED with reproduce commands and land in the ledger
   as binder-derived; a claim at a superseded head lands UNVERIFIABLE.

## Adversarial review (pre-commit, this cycle)

A multi-lens adversarial review (3 reviewers × per-finding refutation verifiers)
ran against the guard + claim binder before commit and surfaced **7 confirmed
correctness defects** (1 further claim ruled a false positive). All 7 were fixed
and locked with regression tests; the review is the reason this increment is
trustworthy rather than merely green. The most important were two that reopened
the very hole the guard exists to close:

1. **Abbreviated / uppercase anchors bypassed SUPERSEDED (critical).** The
   exact-SHA reachability check keyed on the anchor's 40/64-char *spelling*, so a
   12-char or uppercase form of a rebased-away head slipped through as FRESH. Fixed
   by classifying an anchor as a raw object id via `rev-parse --symbolic-full-name`
   (a raw id has none), never by char-count.
2. **`blob-identity` did not guard `other_ref` (critical).** A stale/superseded
   `other_ref` produced a content verdict against unverified state (a false
   CONFIRMED/CONTRADICTED). Fixed by guarding both anchors.
3. **Remote-tracking refs conferred FRESH on exact SHAs (high).** `for-each-ref
   --contains` counted `refs/remotes/*`, laundering a SHA kept alive only by a stale
   remote-tracking snapshot into FRESH. Fixed by scoping reachability to
   `refs/heads`/`refs/tags` + HEAD; a remote-only SHA now falls to SUPERSEDED
   (the safe refusal).
4. **`head-equals` rejected git's own short-sha form (high)** → false CONTRADICTED;
   fixed with prefix-tolerant oid matching (safe: `actual` is the unique resolved id).
5. **A passing `gate-diff --ledger` crashed (high).** Its CONFIRMED findings carried
   no reproduce, so `record_binder_result` refused to back the CONFIRMED and the
   command exited 2. Fixed by attaching the reproduce recipe to the positive findings.
6. **`blob-identity` with no comparison target → false CONTRADICTED (medium);**
   fixed to NOT_RUN.

The review's discipline is the point: the original suite stayed green while every
one of these holes was open, because it only ever exercised full-length lowercase
SHAs from `git rev-parse`. The regression tests now exercise abbreviated, uppercase,
remote-only, and superseded anchors explicitly.

## Boundary (what this does not fix)

The guard proves anchor *currency* at bind time, not claim correctness, and
`ls-remote` freshness is a point-in-time read — a force-push a millisecond
after the check wins the race; re-binding is cheap and deterministic, so the
remedy is re-run, not trust. `SUPERSEDED` detection is scoped to the local
object store's view (`for-each-ref --contains` + HEAD); a shallow or partial
clone that never had the refs sees MISSING, which is equally honest. And none
of this makes an unwilling agent call the binder — it makes the binder's word
worth binding to when called.
