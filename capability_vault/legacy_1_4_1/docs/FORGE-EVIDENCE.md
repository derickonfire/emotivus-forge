# Forge Evidence

Forge v1.0.5 distinguishes execution state from process exit code.

## Status model

Every planned check is represented as one of:

- `PASS` — completed and satisfied its declared contract.
- `FAIL` — completed and proved the check failed.
- `SKIP` — explicitly skipped. A required check fails the Gate unless `allow_skip` is declared.
- `ERROR` — Forge could not obtain trustworthy execution evidence, the command timed out, the runner failed, or required evidence was missing or contradictory.
- `NOT_RUN` — the check was planned but was not reached after an earlier blocker.

A zero exit code remains sufficient for ordinary commands using the default `exit-code` protocol. Projects that need assertion, migration, or SKIP completeness should declare marker evidence.

## Marker protocol

A command can emit:

```text
FORGE_STATUS: PASS
FORGE_ASSERTIONS: 1508
FORGE_SKIPS: 0
FORGE_MIGRATIONS: 24
FORGE_EXECUTED: 17
```

Configuration:

```json
{
  "id": "host.full-gate",
  "command": ["bash", "tools/run_all_checks.sh", "."],
  "timeout": 1800,
  "evidence": {
    "protocol": "markers",
    "required": true,
    "allow_skip": false,
    "required_fields": ["status", "assertions", "skips", "migrations"]
  }
}
```

Forge rejects missing required markers and contradictory status/exit-code evidence.

## Execution history and anomalies

Forge stores comparable check history in `.forge/evidence/execution-history.json`. Comparisons are keyed by check ID, command fingerprint, and environment signature. After at least three comparable successful runs, Forge records suspiciously fast execution and evidence-count regressions.

Timing alone creates an `ANOMALY_WARNING`. A suspicious run becomes blocking when evidence also regresses—for example, assertions or migrations fall, SKIPs increase, or required status evidence disappears while the Graph remains materially stable. A reviewed anomaly can be explicitly accepted once:

```bash
python3 Emotivus-Forge/forge.py check . --profile section --fresh \
  --allow-anomaly host.full-gate
```

The override is recorded in the Gate report. It does not alter the historical baseline or suppress future anomalies.
