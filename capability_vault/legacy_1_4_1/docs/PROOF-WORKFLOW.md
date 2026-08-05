# Proof Workflow

The public Prove core contains six real capabilities:

- **Gate** — Quick, Section, and scoped Release checks
- **Lab** — disposable behavioral verification and runtime contracts
- **Evidence** — Gate, Release Proof, delivery provenance, execution history, anomalies, and failure bundles
- **Deliver** — deployment, internal, state, and final owner-facing handoffs
- **Mirror** — Forge certifies Forge
- **CI** — thin integration that invokes Forge proof

```bash
python3 Emotivus-Forge/forge.py prove gate . --level quick --fresh
python3 Emotivus-Forge/forge.py prove coverage .
python3 Emotivus-Forge/forge.py prove lab . --action plan
python3 Emotivus-Forge/forge.py prove evidence . --action list
python3 Emotivus-Forge/forge.py prove deliver . --profile deployment
python3 Emotivus-Forge/forge.py prove deliver . --profile handoff --action build
```

Every check is explicitly `PASS`, `FAIL`, `SKIP`, `ERROR`, or `NOT-RUN`. A required skip, missing migration count, missing assertion evidence, contradictory output, uncovered executable surface, unsupported target environment, stale generator input, or incoherent final handoff cannot silently become a stronger release claim.

## Gate versus Release Proof

Gate establishes that declared checks executed honestly. Release Proof asks whether current typed evidence covers the product surfaces, persisted states, target environment, and exact delivery required by the configured claim. These are related but not interchangeable.

Claim levels range from `source-verified` through `production-observed`. A green result names the exact level and retains limitations. See `RELEASE-PROOF.md`.

## Runtime contracts

Runtime contracts remain inside **Lab** and connect project-owned executable proof to Forge Gate and Evidence. They cover authorization management, migration chains, browser journeys, APIs, webhooks, jobs, messaging, uploads, providers, and graceful failure behavior.

Forge rejects stale contract fingerprints, insufficient evidence boundaries, missing required cases, and credential-bearing stored output.

## Failure context

Failure bundles assemble changed-since-green paths, Graph context, related learned contracts, environment findings, raw output, and reproduction commands. Forge supplies deterministic evidence; the active human or AI interprets cause and chooses repairs.
