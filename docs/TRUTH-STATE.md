# Truth-State Semantics and Verification Tiers

Forge must not turn absence, inference, or a blocker into evidence. Every meaningful result can therefore carry one truth state:

- `OBSERVED` — Forge directly executed or inspected the stated subject;
- `CONFIRMED` — a project authority explicitly established it;
- `INFERRED` — a bounded conclusion derived from evidence, not direct observation;
- `UNKNOWN` — Forge lacks enough evidence;
- `NOT_RUN` — the check or capability was not executed;
- `BLOCKED_ATTEMPTED` — execution was attempted but could not complete;
- `BLOCKED_UNATTEMPTED` — a prerequisite prevented execution before an attempt;
- `STALE` — prior evidence or a registered source no longer matches the current project;
- `CONTRADICTED` — two current project records or boundaries cannot both be true.

A blocker explains only its own result. It never converts another check into PASS, FAIL, or “explained.” Unrun checks remain `NOT_RUN`.

## Verification tiers

Evidence also records where it was obtained:

`static → sandbox → headless → emulator → dev_device → staging → production`

The order communicates environment proximity, not automatic coverage. A production observation does not imply static, browser, migration, accessibility, or security checks ran. Each record still needs its own subject, result, scope, exclusions, and raw evidence reference when available.

Structured native markers may include `tier` or `verification_tier`:

```text
FORGE_EVIDENCE {"id":"homepage","status":"PASS","type":"browser","tier":"headless","surfaces":["website"]}
```

## Forge self-currency

Adopt, Resume, and Check assess whether Forge's own continuity record still describes the project:

- the current objective resolves to an active, non-excluded project source or owner confirmation;
- the Project Passport was produced by the running Forge build;
- a canonical native-gate source still exists inside the scan boundary;
- owner approval remains bound to the current native-gate fingerprint;
- recorded native evidence has not been invalidated by connected changes.

No native gate or prior evidence is a visible `UNKNOWN`/`NOT_RUN`, but it is not automatically noisy. Forge raises attention when an expected continuity source, approved command, or previously current record becomes missing, stale, or contradicted.

## Token-conservation rule

The detailed records remain in JSON and the Ledger. Compact Resume output reports one self-currency line plus only actionable exceptions. This preserves honesty without expanding every handoff into an evidence dump.

## Claim boundary

Self-currency verifies references, fingerprints, and freshness. It does not decide whether the project objective is strategically correct, whether owner-facing prose is semantically true, or whether a runtime, deployment, or release is safe.
