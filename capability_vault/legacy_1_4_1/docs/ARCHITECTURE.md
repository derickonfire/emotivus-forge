# Architecture

## Forge Core

`emotivus_forge/` contains project detection, guided setup, configuration, auditing, baseline classification, existing-tool migration, architecture mapping, blast-radius analysis, defect-to-regression memory, disposable verification labs, release validation, resumable profile execution, reporting, documentation serving, and deployment-safe packaging.

Forge Core contains no client, restaurant, product, application, integration, version, migration, credential, or business-rule assumptions.

## Shared intelligence chain

Forge v1.0.2 deliberately connects three systems:

1. **Forge Graph** maps project structure, dependencies, routes, systems, tests, and integration indicators.
2. **Forge Learn** attaches approved invariants and regressions to affected paths and mapped subsystems.
3. **Forge Lab** runs declared disposable verification recipes and can be assigned to Section or Release Gates.

This creates a traceable chain from changed files to affected systems, remembered defects, targeted tests, and required verification.

## Adapters

`adapters/` documents supported stack families:

- PHP
- JavaScript
- CSS
- Apache/cPanel
- Node.js
- Python

Detection activates relevant built-in checks. Specialized project linters, tests, builds, dependency tools, browser suites, and integration checks are orchestrated through configured commands rather than unnecessarily reimplemented by Forge.

## Policy Packs

`policy-packs/` is an intentionally empty extension boundary. A project may add a private policy pack containing its own business invariants, graph enrichments, regressions, or lab recipes. Project-specific packs are not part of the neutral Forge distribution.

## Project contract

`.emotivus-forge.json` controls:

- adapters and runtime requirements
- assurance preset and deployment target
- scan exclusions
- quality expectations
- release version source and migration policy
- required package files and hard exclusions
- quick, section, and release commands
- architecture-graph output and refresh profiles
- learned-contract paths
- disposable lab recipes and required profiles
- existing-tool migration state
- live verification checklist categories

## Forge Graph model

Graph nodes represent files, entry points, tests, routes, migrations, webhooks, scheduled jobs, environment variables, and external integrations. Edges represent dependencies, declarations, calls, reads, implementation, and test relationships.

Graph extraction is intentionally heuristic and evidence-backed. Dynamic runtime behavior may require explicit project rules.

## Forge Learn model

Proposals are inactive JSON evidence. Approval creates an active contract. Static contracts are evaluated during audit; command contracts are registered in the selected Gate; manual contracts remain explicit checklist work. Learned-contract violations are never converted to inherited baseline debt.

## Forge Lab model

Lab recipes define workspace mode, setup commands, service start, HTTP probes, verification commands, teardown, environment, and timeouts. The safe default copies the project into an ephemeral directory and removes it after success.

Lab evidence is narrower than production evidence. It does not replace target-host or real-provider verification.

## Existing-tool migration

Forge scans for CI workflows, package-manager scripts, validators, linters, test runners, architecture graphers, impact tools, defect ledgers, browser suites, smoke environments, packagers, release scripts, deployment scripts, secret scanners, configuration files, and AI-agent instructions.

Candidates are classified as:

- **retain** — keep the underlying implementation
- **absorb** — register a safe command in a Forge profile
- **review** — compare overlapping behavior before deciding
- **replace** — eligible only for explicit reversible quarantine

No detected file is silently deleted.

## Baseline model

A finding fingerprint is based on its check ID, path, and message. A baseline converts matching warning or informational findings to `LEGACY`. Changed or newly introduced findings become `NEW`. Blockers, errors, and learned-contract violations are non-baselinable.

## Packaging model

The packager applies immutable engine exclusions, project exclusions, `.deployignore`, hard-sensitive patterns, private-key scanning, credential-literal scanning, symlink refusal, required-file validation, and release gating. The ZIP includes `FORGE-DEPLOY-MANIFEST.json` with file hashes, byte sizes, exclusions, and problems.

## First-contact and continuity layer

Forge v1.0.4 adds four host-project boundaries:

- **Host isolation:** Forge Core and `.forge/` are excluded from Forge's host-mode scans; Mirror mode deliberately reverses that boundary for Forge self-certification.
- **Doctor:** deterministic current-machine and working-layout evidence.
- **Brief:** deterministic session-start evidence assembled from configuration, Gates, Graph, Learn, and Doctor.
- **Portable state:** a separately manifested internal archive for carrying assurance state through ZIP-based, no-Git project lifecycles.

Forge Core remains independent from host runtime source. Existing project tools are orchestration inputs, not code to merge into Forge or discard automatically.

## Maintenance boundary

Forge Update operates on the intact top-level Forge installation, never application runtime files. It stages the incoming distribution, preserves configured private extensions, records configuration migrations, and runs the incoming Forge as a subprocess before committing the upgrade. Doctor remediation is a separate reviewed transaction system. CI Bridge emits deterministic adapters around Forge Gates. Internal Delivery composes source and portable state without weakening deployment exclusions.

## Controlled-change model

Pivot remains an internal capability of the Change core. Its durable stores remain under `.forge/project/`:

- `pivots.json` — direction, obligations, dispositions, mode history, checkpoint, completion evidence.
- `plans.json` — the linked transition Plan and quality-evidence coverage.
- `ledger.json` — versioned standards, decisions, requirements, and lifecycle history.
- `pivot-checkpoints/<pivot-id>/` — hash-verified pre-pivot assurance state and latest green evidence.
- `.forge/policies/learned-contracts.json` — learned contract lifecycle status and history.

The checkpoint intentionally does not copy product source. Forge records the source fingerprint and requires source preservation through source control or an internal delivery. This avoids implying that an assurance tool is a source-control system.

Pivot completion is a deterministic boundary: final dispositions, reasons, successors, replacement evidence, quality coverage, release mode, and a current passing Release Gate. Completing a Pivot applies lifecycle changes to the Ledger and learned contracts.

## Runtime-contract model

Runtime proof stays inside Prove → Lab. The registry at `.forge/contracts/runtime-contracts.json` declares project-owned executable contracts for authorization, migrations, browsers, APIs, webhooks, scheduled jobs, messaging, uploads, and external providers.

Forge validates the current contract fingerprint, evidence boundary, required categories, explicit expected cases, command result, and persisted redaction. Authorization contracts require actor/action/target outcomes for privilege administration and session revocation. Migration contracts add a static schema-capability graph before executable first-run, idempotency, data-preservation, and package-inclusion evidence.

Forge detects existing browser and service tooling and orchestrates it. It does not implement a replacement browser engine, database harness, or provider simulator.

Impact schema 2 keeps three different claims separate: certification impact, dependency reach, and runtime-path reach. File-level Graph edges do not become branch-level behavioral proof without project-specific contracts or live journeys.
