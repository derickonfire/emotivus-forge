# Advanced Capabilities

Advanced capabilities never activate because their code exists. Each requires a project trigger, project-owned contract, explicit scope, exclusions, budgets, focused regressions, authority, and a distinct reason it adds value beyond the project’s native tools.

## Active clean-room capabilities

### Forge Doctor

- mode: diagnose-only;
- compares declared local runtime expectations with the observed CLI;
- never repairs, installs, mutates, or claims production equivalence.

### Runtime Proof

- mode: content-aware HTTP;
- verifies bounded status and minimum viable content at exact allowed origins;
- GET-only and unauthenticated;
- stores no response body;
- does not execute JavaScript or prove visual, database, deployment, or release correctness.

See `RUNTIME-PROOF.md`.

## Integrated controlled-core release contracts

### Release Proof

Release Proof is no longer a dormant advanced engine. Forge 0.525 provides a clean-room, project-owned assurance-map contract in the active core. It binds declared ZIP members and release surfaces to explicitly classified assurance domains and current evidence receipts. It performs structural and cryptographic consistency checks only; it does not execute reviews or authorize release.

See `RELEASE-PROOF.md`.

## Still inactive

Graph, legacy Lab, expanded Evidence, Confidentiality Certification, CI Bridge, Update, and Mirror remain inactive. Their metadata may be shown, but no legacy vaulted module is imported.

## Activation lifecycle

A capability contract is fingerprint-bound. If the contract or any attached recipe changes or disappears, the capability becomes `reactivation-required` before its service module is imported. Deactivation preserves the durable Ledger record.

Release Proof uses the same fingerprint-bound authority discipline but is an integrated core contract rather than a lazily imported legacy capability.
