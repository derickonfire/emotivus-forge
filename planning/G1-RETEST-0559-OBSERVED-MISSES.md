# G1 re-test on 0.559 — regressions held + deeper-gate observed misses

**Method:** 15 adversarial agents. 5 re-tested the 0.559 fixes; 10 attacked the deeper
G1 gate. Each built isolated fixtures and actually ran `forge.py` against 0.559.

## Regressions — ALL HELD (0.559 fixes are not regressed)

- **M-G1-2 / M-G1-3 / M-G1-4 / M-G1-5:** clean, on every surface. Bounded change
  confidence, inferred-vs-confirmed labels, scoped secrets claim, gated run
  commands all held.
- **M-G1-1:** held for the cases the fix targets — a mismatched `baseline_id`
  (no ledger event) and a deleted ledger both correctly yield `UNCORROBORATED`,
  `release_eligible=false`, quarantined. The fix is intact.
- **Deeper-gate HELD:** stale-evidence-as-current (checkpoint invalidated on
  change), NOT_RUN native gate → PASS (forged stdout markers not treated as a
  project PASS), and snapshot-fingerprint collision (0.559 bounded labeling covers
  it).

## The dominant deeper-gate finding: "self-consistent ≠ authentic"

**Root cause (1 critical + 4 high):** Forge's ledger/corroboration chain is an
**unkeyed public SHA-256 chain** (`ledger.py:_canonical_hash` / `verify_ledger_chain`
— no signature, no per-instance secret) that **travels inside the project's
`.forge/`**. So anyone able to write `.forge` — above all, whoever authored an
*imported* package — can recompute a self-consistent chain containing an
`authority-baseline-authorized` (or `artifact-provenance-recorded`) event whose
payload matches the shipped state. Forge's own `verify_ledger_chain` calls it
HEALTHY, and corroboration then asserts, unhedged, *"corroborated by a
chain-verified authorization event in this instance's ledger"* → `release_eligible:
true`, `status: CURRENT`. The same class lets artifact-provenance emit `CONFIRMED`
("bytes match authority-recorded digests") without corroborating against a
chain-verified event.

This is exactly the multi-model / cross-vendor import threat: a package arriving
from another model must not be able to assert authority it did not earn *here*.

Findings in this cluster:
- **DG-1 (critical):** legacy/imported state with a fabricated-consistent chain →
  `Authority baseline: CURRENT`; migration `setdefault`s and retains an imported
  `active` baseline rather than downgrading it.
- **DG-2 (high):** authority-baseline corroboration spoofable by a fully-rebuilt
  self-consistent chain (the M-G1-1 residual).
- **DG-3 (high):** ledger-chain tamper — a self-consistent forged chain (even with
  an absurd timestamp) is trusted as HEALTHY → corroborated:true.
- **DG-4 (high):** artifact-provenance asserts CONFIRMED ("bytes match…") without
  corroborating against a chain-verified `artifact-provenance-recorded` event.
- **DG-5 (high):** exact-byte — Check emits CONFIRMED comparing recorded digests
  without re-verification against a chain-verified event.

### The real fix (recorded for the regroup — needs design, not a rushed seal)

**Instance-binding.** Generate a per-instance secret/keypair at adopt time, stored
**outside** the shipped `.forge` payload (an OS-protected location or a keystore
keyed by project path), and sign `authority-baseline-authorized` /
`artifact-provenance-recorded` events (or the chain head) with it; corroboration
verifies that signature, not just self-consistent SHA-256. The subtlety the agents
flagged: the key must live somewhere an imported package cannot also carry — this
is the crux and deserves a proper design pass. Until it exists, Forge must **label
the residual honestly and never let unkeyed corroboration confer authenticity.**

## Lesser deeper-gate findings (recorded)

- **DG-6 (medium):** ship `candidate-unchanged` reason says "No project paths
  changed after the checkpoint" without the bounded qualifier when un-hashed files
  exist (the M-G1-2 phrasing didn't reach `ship_claims.py`).
- **DG-7 (medium):** `no-unresolved-same-version-branch` returns PASS without
  keying the collision guard off the incoming package's *differing bytes*.
- **DG-8 (medium):** native evidence is not bound to a source/tree fingerprint, so
  evidence captured for tree A can read as current for tree B.

## 0.560 scope (bounded, green, honest — the rest deferred to the regroup)

1. **Honest corroboration boundary:** corroboration wording + `TRUTH_BOUNDARY` now
   state that the ledger chain is **unkeyed and travels with the project** — it
   proves internal consistency and that an authorization event exists, but does
   **not** cryptographically prove the authorization was performed by this instance
   rather than imported/fabricated by anyone able to write `.forge`. The over-claim
   "in this instance's ledger" is removed. (Subtract unearned certainty in the words.)
2. **Ship bounded phrasing (DG-6):** `candidate-unchanged` carries the bounded,
   un-hashed qualifier.

Deferred to the regroup as the flagship next increment: **cryptographic
instance-binding** (DG-1..DG-5), plus provenance corroboration parity, migration
downgrade of imported `active` baselines (needs schema-gated logic so legit
re-adopt is untouched), same-version-collision-by-bytes (DG-7), and native-evidence
source binding (DG-8).

*Data source: workflow `g1-retest-and-deeper-gate` (15 agents); per-agent
transcripts in the run's `journal.jsonl`.*
