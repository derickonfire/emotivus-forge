# Active Ledger Assertions

Forge can attach bounded deterministic obligations to project-authorized records without executing arbitrary code. The project owns the JSON contract; Adopt validates and records it; Check re-evaluates every active assertion.

## Supported record types

- `decision`
- `resolved-defect`
- `guardrail`
- `release-rule`
- `project-rule`

## Supported assertion kinds

- `path-exists`
- `path-absent`
- `file-contains`
- `file-not-contains`
- `json-equals`
- `zip-excludes-prefix`
- `zip-includes-path`

Assertion targets must remain inside the host project and outside `.forge` and the Forge distribution. Contract evidence paths must exist when authority records the assertion.

## Record and retire

```bash
forge adopt . --record-ledger-assertion ledger-assertion.json
forge adopt . --retire-ledger-assertion resolved-feature-state \
  --ledger-assertion-reason "The owner replaced this rule with a newer confirmed decision." \
  --ledger-assertion-authority owner
```

The contract source and normalized contract are fingerprint-bound. A missing or changed source moves the record to `approval-required` and blocks Check until authority records it again or retires it. Retirement preserves the original Ledger history and stops enforcement.

## Check meaning

A failed active assertion blocks Scoped Check and reopens the trusted claim. A passing assertion proves only the declared deterministic predicate. It does not prove feature correctness, package completeness, deployability, live-baseline accuracy, or release readiness.

Full contracts and individual results remain local. Resume reports compact active, retired, and attention counts to conserve tokens.
