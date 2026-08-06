# Governed Continuity Register

Forge’s continuity register preserves compact current project facts and explicit knowledge gaps without becoming a transcript, vector database, or general-purpose AI memory service.

## Record

```text
forge adopt . --record-continuity-register forge-continuity-register.json
```

Recording must be a separate Adopt operation. One register is active at a time. A replacement must explicitly name the active register it supersedes and provide a durable change reason.

## Trust order

1. `owner-declared`
2. `project-evidenced`
3. `developer-recorded`
4. `agent-inferred`
5. `automatically-extracted`

A lower-trust source cannot silently replace a higher-trust value. Project-evidenced facts require exact project-file support. Owner-declared facts require a declaration or Ledger event.

## Fact fields

Each fact includes a stable ID and key, value, trust, rationale, impact, support references, change reason when applicable, and truth boundary.

Supported references are:

- exact project files;
- existing Forge Ledger events;
- explicit declarations inside the authority-owned contract.

Changed or missing project-file support makes the register stale. Changed contract bytes require renewed recording.

## Knowledge gaps

Gaps include a stable ID, question, priority, open or resolved state, required evidence, optional owner, blocking scopes, and truth boundary. Resolved gaps require evidence. Open gaps cannot disappear from a superseding register without explicit resolution or retirement.

A gap may explicitly block Resume, Check, Ship, deployment, release, or roadmap claims. Forge does not infer blocking scope from prose.

## Retire

```text
forge adopt . --retire-continuity-register continuity-main \
  --continuity-register-reason "Replaced after owner review."
```

Retirement preserves history and does not activate an older register automatically.

## Boundary

The register records project-owned continuity truth and unknowns. It does not authenticate a human, prove factual completeness, monitor chat continuously, infer authorship, authorize source changes, or authorize release.
