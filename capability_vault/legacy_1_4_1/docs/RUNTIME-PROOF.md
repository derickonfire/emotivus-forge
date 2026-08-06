# Runtime and User-Behavior Proof

Forge v1.3 deepens **Prove** without adding another public core. Runtime contracts connect project-owned executable checks to Forge Gate, Graph, Evidence, and Lab.

Forge does not invent application behavior. A project declares what must be true, supplies the command that exercises it, and emits structured evidence. Forge verifies the declaration, current contract fingerprint, evidence boundary, required cases, coverage, result, and persistence safety.

## Evidence boundaries

From weakest to strongest:

1. `static-source`
2. `local-process`
3. `disposable-local-environment`
4. `sandbox`
5. `staging`
6. `release-equivalent`
7. `production-observed`

Each Gate profile may require a minimum boundary. Stronger names do not make evidence stronger; the declared environment and retained report must justify the boundary.

## Runtime contract registry

Initialized projects receive:

```text
.forge/contracts/runtime-contracts.json
```

Generate the current proof plan:

```bash
python3 Emotivus-Forge/forge.py prove lab . --action contracts
```

Run one contract:

```bash
python3 Emotivus-Forge/forge.py prove lab . --action contract --contract admin-authorization
```

List the resulting proof:

```bash
python3 Emotivus-Forge/forge.py prove evidence . --action list
python3 Emotivus-Forge/forge.py prove evidence . --action show --id runtime:admin-authorization
```

## Structured evidence protocol

The project command must emit JSON directly or on a final marker line:

```text
FORGE_RUNTIME_EVIDENCE={...}
```

The payload must include:

- `schema`
- `contract_id`
- `kind`
- `contract_fingerprint`
- `evidence_boundary`
- `status`
- `cases`

Forge supplies the current values to the command as:

```text
FORGE_RUNTIME_CONTRACT
FORGE_RUNTIME_CONTRACT_FINGERPRINT
FORGE_RUNTIME_EVIDENCE_BOUNDARY
```

Evidence from an older contract is rejected. Credential-like output is redacted before reports are stored.

## Authorization contracts

A static role map cannot prove runtime authorization. Authorization proof requires explicit expected cases describing actor, action, target or resource, and expected allow or deny outcome.

Coverage includes:

- Allowed access
- Denied access
- Direct URL denial
- Denied POST or mutation
- CSRF enforcement
- Explicit-deny precedence
- Privilege grant, revoke, and escalation boundaries
- Immediate session behavior after suspension or revocation

This is intentionally stronger than verifying that a role contains a permission string. Projects must declare who may administer privileges, whether self-promotion is allowed, which peers or superiors may be targeted, and what happens to existing sessions.

## Migration contracts

Forge models migration dependencies using declared schema capabilities and predecessor migrations. It detects:

- Missing predecessors
- A shipped migration depending on an excluded predecessor
- Duplicate providers
- Cycles and self-dependencies
- Missing migration files
- Ordered-chain gaps

Executable evidence then proves first-run behavior, idempotency, data preservation, and package inclusion. Static dependency analysis is not presented as database execution proof.

## Browser and integration contracts

Forge detects existing Playwright, Cypress, Puppeteer, Selenium, WebdriverIO, and common compose/test infrastructure. It orchestrates project-owned commands rather than replacing them.

Runtime contract kinds include browser, API, webhook, cron, email, SMS, upload, and external provider behavior. Required categories emphasize negative and failure behavior as well as successful paths.

## Evidence boundary

Runtime contracts prove only their declared environment and cases. A disposable local database does not prove production data, a sandbox provider does not prove live delivery, and a browser smoke does not prove every viewport or assistive technology.

## Relationship to Release Proof

A passing runtime contract is one evidence producer. It supports only its declared surfaces, cases, environment boundary, and current contract fingerprint. `prove coverage` joins current runtime evidence with other producers and reports uncovered release obligations.
