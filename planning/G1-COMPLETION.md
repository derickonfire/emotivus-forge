# G1 · Provable Project Truth — completion verification

**Verdict: COMPLETE (as of 0.566).** Every dimension of the G1 completion rule is
adversarially verified by a passing regression, and the certified suite passes twice,
deterministically, from the public package's own independently extracted bytes.

## Completion rule

> Exact identity, authority, lineage, evidence binding, adversarial package rejection,
> and package authorization all pass from independently verified bytes.

## Dimension → adversarial evidence

| Dimension | Adversarial guarantee | Covering regression(s) |
|---|---|---|
| **Exact identity** | File / tree / package identity is exact; `.forge` is excluded from project scans | `test_project_identity`, `test_release_facts`, `test_artifact_collision` |
| **Authority (import rejection)** | An imported/hand-edited `active` baseline with no matching chain-verified event → `UNCORROBORATED`, quarantined, not release-eligible | `test_authority_baseline::test_bounded_authority_snapshot_cannot_support_ship_authority_claim` |
| **Authority (instance-binding)** | Only an authorization signed by a key this instance trusts is `instance-bound` and release-eligible; a fabricated/unsigned event is `self-consistent`, never release-eligible | `test_authority_baseline::test_unsigned_imported_authorization_is_self_consistent_not_release_eligible` |
| **Authority (multi-party)** | A shared collaboration secret makes authorizations mutually instance-bound across enrolled parties; a party without it sees only self-consistent | `test_authority_baseline::test_collaboration_secret_makes_authorizations_mutually_instance_bound` |
| **Lineage** | Parent/fork/collision/quarantine recorded exactly; same-version collision keyed off differing bytes and declared version | `test_lineage` |
| **Evidence binding (provenance)** | A deliverable's lineage is `CONFIRMED` only when its recording event is instance-bound; an imported/unsigned record is honest as current but not authenticated | `test_provenance_delivery::test_imported_provenance_recording_is_not_instance_bound_confirmed` |
| **Evidence binding (native)** | Imported native evidence is bound to its source tree; once the tree changes it is `stale-source-changed`, not current, even under an unchanged gate command | `test_native_invocation_handoff::test_native_evidence_is_bound_to_the_source_tree_it_was_captured_against` |
| **Change confidence** | A count of 0 on un-hashed (over-budget) files is reported `bounded`, never bare "unchanged / high confidence" | `test_authority_baseline` (M-G1-2), `test_core_adoption_check` |
| **Adversarial package rejection** | Wrong-package / tampered / stale-evidence branches are quarantined and never silently accepted; a forged NOT_RUN native marker is not treated as a project PASS | `test_lineage`, `test_native_invocation_handoff`, `test_cli_integration` |
| **Package authorization** | Release authorization requires a current exact final-package binding (`_current_exact_package` raises otherwise); a bounded snapshot cannot support the authority-bound Ship claim | `test_release_authorization`, `test_authority_baseline` |

## Independent exact-byte verification (P2-09)

The public `RUN-FORGE.zip` was extracted to a fresh directory and its certified suite
run from those bytes:

- **Run 1:** `Ran 533 tests … OK`
- **Run 2 (determinism):** `Ran 533 tests … OK`
- Embedded package version: `0.565`; identical result both runs.

## Honest boundaries (what "G1 COMPLETE" does and does not claim)

- Forge authenticates a **key/instance**, not a human identity or review quality; a
  stolen instance secret (full machine compromise) defeats instance-binding.
- Corroboration is symmetric-keyed (HMAC); trust is between owner-provisioned parties.
- `release_authorization` remains **false** as shipped — G1 COMPLETE certifies the
  *provable-truth core*, not that any specific release is authorized or efficacious.
- One field-test finding (DG-7, same-version collision) was reviewed and did **not**
  survive verification; no speculative fix was made
  (`planning/G1-RETEST-0559-OBSERVED-MISSES.md`).

## Disposition

G1 moves from **ACTIVE** to **COMPLETE**. P2-08 (adversarial trials) and P2-09
(independent exact-byte verification) are satisfied. G2 and G3 remain the open goals;
G3's foundation is materially advanced by the instance-binding delivered under G1.
