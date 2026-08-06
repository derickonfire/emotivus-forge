# Design — cryptographic instance-binding for authority & provenance

**Status:** design only (for the regroup). No code yet. Closes the dominant
deeper-gate finding from `planning/G1-RETEST-0559-OBSERVED-MISSES.md`
("self-consistent ≠ authentic") and subsumes the provenance-parity and
migration-downgrade misses.

## 1. The problem, precisely

Forge's ledger is an **unkeyed** SHA-256 chain that lives *inside* the project's
`.forge/`. `verify_ledger_chain` proves the chain is internally consistent — nothing
more. Because the algorithm is public and the chain travels with the package, anyone
who can write `.forge` (above all, the author of an *imported* package) can
recompute a consistent chain carrying an `authority-baseline-authorized` (or
`artifact-provenance-recorded`) event that matches the shipped state. Corroboration
then reports `CURRENT` / `release_eligible`. 0.560 made the *wording* honest; this
design makes the *check* real.

**Goal:** an authorization/provenance event must be verifiable as having been
produced by a party the owner trusts — and un-forgeable by anyone who merely ships a
package — so that only trusted-signed events may confer authority or release
eligibility.

## 2. Threat model

**In scope (must defeat):**
- An imported / migrated package whose `.forge` (state + ledger) is fully attacker-authored, including a self-consistent chain, asserting authority/provenance it did not earn on the verifying instance.
- In-place edits to `.forge` by a process without the instance secret.

**Out of scope (documented as honest limits, not solved here):**
- Full compromise of the owner's machine / theft of the instance secret (then the attacker *is* the instance).
- Proving a **human** reviewed anything — Forge authenticates a key/instance, never a person (existing `TRUTH_BOUNDARY`).
- A legitimate owner moving machines: an intentional key export/import is an explicit owner action, not a silent transfer.

## 3. Mechanism — keyed MAC over authority/provenance events

Add a **keyed signature** to the two authority-bearing event kinds
(`authority-baseline-authorized`, `artifact-provenance-recorded`):

- On record, compute `sig = HMAC-SHA256(instance_secret, canonical_event)` where
  `canonical_event` already includes `previous_event_hash` (so the signature also
  chains). Store `sig` and a non-secret `key_id` (a public label, e.g. the SHA-256
  of the public half / a random per-key id) on the event.
- On corroborate, recompute the MAC with each **trusted** secret and require a match.
  Self-consistency of the hash chain is necessary but **no longer sufficient**.

Baseline algorithm is **HMAC-SHA256 (Python stdlib `hmac`)** to honor Forge's
stdlib-only constraint. Asymmetric Ed25519 (via an optional `cryptography` import,
degrading gracefully when absent) is a documented future upgrade that would let a
*public* key be shared for verification without sharing signing power — cleaner for
many-party trust, but not required for the realistic LineCheck case below.

## 4. Key material & storage — the crux

**The signing secret must never live inside the project's `.forge/`** (or it ships
with the package). It lives in a per-user **Forge home** outside any project tree:

- Location: `${FORGE_HOME:-~/.config/emotivus-forge}/keys/` (OS-appropriate;
  0600 perms). Never written under a project directory, never packaged, never in git.
- **Instance secret:** generated once on first adopt (`secrets.token_bytes(32)`),
  stored in Forge home. This is the instance's identity.
- **Trusted-signer set:** the set of `key_id`s whose signatures this instance will
  elevate. Always includes the instance's own key. Peer keys are added only by an
  explicit **owner enrollment** action, and the enrollment lives in Forge home too —
  *not* in `.forge/`, so an imported package cannot enroll itself.
- If Forge home is unavailable (read-only env, CI): degrade to **unsigned /
  self-consistent-only** — honestly labeled, never elevated. No hard failure.

## 5. Corroboration becomes tri-state

`_corroborate_baseline` (and the provenance evaluator) return one of:

| binding | meaning | confers authority / release_eligible? |
|---|---|---|
| `instance-bound` | event signature verifies against a **trusted** key | **yes** |
| `self-consistent` | chain consistent, but signature missing or from an **untrusted** key | **no** — labeled, quarantined from release |
| `uncorroborated` | no matching event, or chain broken | **no** |

Only `instance-bound` may raise `release_eligible` or render "CURRENT · authorized".
This is the concrete closure of the critical finding.

## 6. Multi-model / LineCheck — the collaboration case

LineCheck has two trusted parties (Claude's Forge, ChatGPT's context) on one repo.
Symmetric HMAC handles this cleanly because *both are owner-trusted*: the owner
provisions a **shared collaboration secret** into each trusted party's Forge home
**out-of-band** (never through the repo). Events signed with it are `instance-bound`
for every enrolled party; an *untrusted* imported package lacks the secret and can
only ever reach `self-consistent`. The threat is untrusted packages, not the trusted
peers — so a shared symmetric team key is sufficient and simplest. (Ed25519 per-party
keypairs are the upgrade path if the trust set grows beyond a hand-provisioned team.)

This is why the deferred G1 crypto work and the LineCheck pivot converge: the
collaboration secret *is* how two vendors trust each other's "this was authorized /
this artifact is real" without either being able to forge the other outside the team.

## 7. Backward compatibility & migration

- Existing 0.560 unkeyed baselines carry no signature → corroboration reports
  `self-consistent` (not `instance-bound`); they keep working but no longer elevate
  release eligibility until re-authorized locally (which signs them). No hard break.
- **Migration downgrade (subsumed):** an imported `active` authority baseline whose
  events are not `instance-bound` is downgraded to `not-established` on migrate/adopt.
  This replaces the standalone migration-downgrade miss and needs the tri-state to be
  correct (so legit local re-adopt, which is `instance-bound`, is untouched).
- **Provenance parity (subsumed):** `artifact-provenance-recorded` gets the same
  signing + tri-state; CONFIRMED requires `instance-bound`.

## 8. Honest boundaries (must be stated in TRUTH_BOUNDARY)

- Proves a trusted **key/instance** produced the event — not a human, not review
  quality, not correctness.
- A stolen instance secret defeats it (machine-compromise is out of scope).
- Cross-machine legit use requires explicit key export/import by the owner.

## 9. Bounded implementation chunks (for after the regroup)

1. **Key store** — `instance_key.py`: get-or-create instance secret in Forge home;
   trusted-signer set; enroll/export owner actions; graceful degrade when home is R/O.
2. **Signed events** — extend `ledger.record_event` (or a wrapper) to sign the two
   authority-bearing kinds; add `sig` + `key_id` fields; keep other kinds unsigned.
3. **Tri-state corroboration** — `_corroborate_baseline` + the provenance evaluator
   verify signatures against trusted keys; only `instance-bound` elevates.
4. **Migration downgrade** — imported non-`instance-bound` `active` baselines →
   `not-established`.
5. **TRUTH_BOUNDARY + wording** update to the tri-state reality.

## 10. Test plan (adversarial, mirrors the field test)

- Legit local authorize → `instance-bound`, release-eligible (exact strength).
- Fabricated self-consistent chain (attacker key not enrolled) → `self-consistent`,
  **not** release-eligible, quarantined. (This is the exact spoof 0.560 could not stop.)
- Imported legacy `active` baseline → downgraded to `not-established`.
- Enrolled peer (collaboration secret) signature → `instance-bound` (the LineCheck case).
- Forge home read-only → degrade to `self-consistent`, never elevate, no crash.
- Provenance: mismatched/forged provenance event → not CONFIRMED.

Regressions extend existing methods (certified suite stays 523/54); the version bump
is lockstep as usual.
