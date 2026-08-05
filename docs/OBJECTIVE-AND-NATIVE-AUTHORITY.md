# Objective Recovery and Native Execution Authority

## Objective recovery

Forge ranks active authority sources above archived material. A line that only redirects to another file, ends as an obvious fragment, or cannot stand alone as work is retained as rejected evidence rather than becoming the project objective.

When that line explicitly names a project-local Markdown, text, or reStructuredText authority file, Forge may follow the link within the project boundary. For an ordered roadmap it selects the first item not marked complete, built, satisfied, closed, shipped, retired, or withdrawn.

Forge does not infer an objective from arbitrary links, external URLs, or missing files. When no supported objective resolves, owner confirmation remains required:

```bash
forge adopt . \
  --confirm-objective "Build the approved routine creation path." \
  --objective-source Planning/ROADMAP-ORDER.md
```

The authority registry preserves the selected source, resolution method, link origin, rejected candidates, and confirmation state locally. Routine Resume output carries only the confirmed objective and actionable exceptions.

## Native execution modes

A canonical native quality ecosystem has one explicit execution mode:

| Mode | Forge may execute? | Accepted evidence |
|---|---:|---|
| `forge-authorized` | Only after explicit `--run-native` | Forge execution |
| `owner-only` | No | Structured owner evidence |
| `external-ci` | No | Structured external-CI evidence |
| `evidence-import-only` | No | Structured evidence from an allowed declared authority |

Set or change the mode through Adopt:

```bash
forge adopt . --native-mode owner-only
```

The selected candidate ID, command, fingerprint, mode, and authority record are stored in `native-tools.json`. If the gate changes, its previous approval becomes `reapproval-required` regardless of mode.

## Structured evidence import

```bash
forge check . --import-native-evidence native-evidence.json
```

The evidence file must remain inside the project, outside `.forge`, and conform to `forge-native-evidence/1`. Forge validates the candidate ID, current gate fingerprint, execution authority, status, verification tier, and entries before copying the exact record into local evidence storage.

Forge does not execute the gate during import and does not rewrite imported evidence as Forge-generated proof. A stale fingerprint, authority mismatch, malformed record, or evidence path outside the project blocks the import.

See `examples/native-evidence.example.json`.

## First-adoption continuity

Before the first Session Close, continuity is `not-established`. This is expected and does not itself create an attention warning. After continuity exists, stale or missing support is reported separately.

## Claim boundary

Objective linking is bounded document recovery, not general project reasoning. Imported evidence verifies record currency and authority compatibility, not the honesty of the provider, completeness of the native gate, runtime correctness, deployment, or release readiness.

## Exact invocation requirement

Execution mode alone is not approval to run a bare script. Every active native policy now requires a project-owned exact invocation contract:

```bash
forge adopt . \
  --native-mode owner-only \
  --native-invocation forge-native-invocation.json
```

The contract binds argv, working directory, bounded non-secret environment overrides, timeout, verification tier, and expected check coverage. Imported evidence must match both the gate-source fingerprint and invocation fingerprint. See `NATIVE-INVOCATION.md`.
