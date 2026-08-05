# Release Proof and Delivery Provenance

Forge v1.3.4 preserves the observed-evidence boundary introduced in v1.3.3 and corrects neutral-acceptance defects in package authority, semantic surface identity, delivery diagnostics, and exact final-handoff verification.

## The governing rule

> Forge proves only the exact claim supported by current, joined, observed evidence. Declaring coverage is necessary for scope control, but declaration alone is never execution proof.

Run the coverage report:

```bash
python3 Emotivus-Forge/forge.py prove coverage .
```

## Claim levels

Forge reports the strongest configured and automatically required claim:

1. `source-verified`
2. `package-verified`
3. `entrypoints-executed`
4. `upgrade-verified`
5. `target-environment-verified`
6. `delivery-verified`
7. `staging-accepted`
8. `production-observed`

Each level includes the obligations below it. The report lists unsupported claims and known limitations separately.

## Proof Map

The Release Proof report joins:

- Discovered browser pages, routes, APIs, webhooks, jobs, CLIs, and entrypoints
- Typed recurring command evidence
- Exact observed surface attestations
- Current Forge Lab reports
- Current runtime-contract reports
- Persisted-state transition evidence
- Target-runtime, extension, and service evidence
- Deployment package evidence
- Delivered artifacts, generators, source inputs, hashes, and final-bundle membership
- Verification claims in standard documents and configured objective sources that are not backed by current recurring commands

A producer counts only when its evidence is PASS, bound to the current source-tree fingerprint, still matches its command, recipe, or contract fingerprint, and contains the observation required by the claim.

## Typed evidence

Evidence producers declare what they are intended to prove:

- `static`
- `unit`
- `integration`
- `entrypoint-execution`
- `browser-behavior`
- `database-upgrade`
- `target-environment`
- `package`
- `delivery-provenance`
- `staging`
- `production-observation`

Assertion volume never substitutes for evidence type or surface coverage.

## Observed surface attestations

A command declaration may bound its intended coverage with exact paths, patterns, or selectors such as `all:browser-page`. That declaration does not mark a surface covered.

A passing Gate command must also emit one exact observation line for each surface it actually exercised:

```text
FORGE_SURFACE: index.php
FORGE_SURFACE: admin/users.php
FORGE_SURFACE: webhook:hooks/inbound.php:hooks/inbound.php
```

Forge records these lines in the Gate result. A surface is covered only when:

1. The producer declaration permits that surface.
2. The current passing result attests that exact path, name, or canonical `kind:path:name` identity.
3. The evidence type is execution-capable for the requested claim.

A blanket declaration plus a blank or generic PASS command therefore covers nothing.

Forge Labs attach exact attestations to successful probes and verification steps. Runtime contracts that declare surfaces must emit a `surfaces` list in their runtime evidence payload.

## Surface coverage

Forge discovers executable and user-facing surfaces, then reports which recurring producers cover each one. Plain-PHP discovery distinguishes browser pages, APIs, webhooks, scheduled jobs, and CLI tools; it excludes known nested support bootstraps and collapses generic Graph hints into one semantic obligation per path.

Projects can add or correct surfaces in `release_proof.surfaces`. Discovery remains reviewable because no universal heuristic can infer every application boundary perfectly.

## Bound deployment-state and target-environment evidence

Stateful projects declare relevant transitions in `release_proof.deployment_states`, including:

- Empty state plus current code
- Prior-release state plus current code
- Current state plus current code
- Ahead-of-code state, when supported

`environment.target` separately records target runtimes, required extensions, required services, and evidence collected at `release-equivalent` or `production-observed` boundaries.

A referenced evidence file counts only when its reference names both:

- `path`: the current evidence file; and
- `producer`: a current registered Forge Gate command.

The producer command must declare the evidence path in `evidence.artifacts`. Forge snapshots the file before execution, then records its output hash, byte count, and whether it was created or refreshed during that exact run. Release Proof rejects:

- A string-only path reference
- An unregistered or stale producer
- A producer whose command hash no longer matches configuration
- A file that existed before a no-op command and was not refreshed
- A file changed after the producer passed
- A PASS file bound to the wrong source-tree fingerprint

Example command configuration:

```json
{
  "id": "deployment.verify-upgrade",
  "command": ["python3", "tools/verify_upgrade.py"],
  "evidence": {
    "types": ["database-upgrade"],
    "artifacts": [".forge/runtime/upgrade-evidence.json"]
  }
}
```

Example deployment-state reference:

```json
{
  "id": "prior-release-plus-current-code",
  "state": "prior-release-plus-current-code",
  "required": true,
  "evidence": {
    "path": ".forge/runtime/upgrade-evidence.json",
    "producer": "deployment.verify-upgrade"
  }
}
```

A fresh installation does not prove an upgrade, and a local Doctor result does not prove the target host.

## Delivery provenance

The final owner-facing handoff is a first-class object. Every current artifact must be either:

- **Generated** by a Forge-observed executable command with explicit source inputs, generator fingerprint, execution receipt, input fingerprint, output bytes, and SHA-256; or
- **Frozen** with an explicit reviewed reason.

Register an artifact:

```bash
python3 Emotivus-Forge/forge.py prove deliver . \
  --profile handoff --action record --input artifact-record.json
```

Build and verify the exact outer handoff:

```bash
python3 Emotivus-Forge/forge.py prove deliver . \
  --profile handoff --action build
```

Forge runs a pre-delivery Release Gate, builds the final bundle, then runs the Release Gate again against the completed delivery. Undeclared deliverable-shaped files, stale input or generator fingerprints, output-hash drift, invalid commands, ambiguous current roles, and mismatched bundle membership block delivery proof.

## Important boundary

Observed attestation proves what a registered producer reported during a current Forge-managed run; it does not make arbitrary project-owned verification logic infallible. Application-specific checkers still require sound implementation, independent review, and appropriate staging or production boundaries.

Forge also cannot prove undeclared external activity. Manual work must be imported into the delivery manifest or explicitly frozen. Release Proof makes the remaining perimeter visible rather than silently treating it as covered.


## v1.3.4 delivery-dimension and final-bundle rules

Release Proof keeps claim blockers and dimension diagnostics distinct. A missing outer handoff is reported as an exact delivery problem, but it does not block the handoff-build action that resolves it. Compact coverage exposes both the combined actionable problem set and the narrower `claim_problems` set.

Recording or refreshing a declared artifact invalidates any previous final-bundle receipt. Final delivery verification then opens the ZIP and verifies that each declared member is present exactly once and that its archived bytes match the current declared artifact SHA-256. Name-only membership is not sufficient.
