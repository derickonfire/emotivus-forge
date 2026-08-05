# Interaction and Token Telemetry

Forge records local operational evidence in `.forge/metrics.jsonl`. Telemetry exists to test whether Forge saves work over repeated sessions—not to manufacture a savings claim.

## Truth classes

Forge distinguishes three classes:

1. **Observed local facts** — operation duration, files scanned, output characters, cached records reused, evidence reused or invalidated, retries, and corrections.
2. **Exact provider reports** — input and output token counts explicitly copied from a named provider.
3. **Heuristic estimates** — character-based approximations such as Resume characters divided by four.

A heuristic is never labeled as provider measurement or actual token savings. Workspace bytes are never converted into a token-savings claim.

## Recording a measured Session Close

```bash
python3 Emotivus-Forge/forge.py check . \
  --close-session \
  --next-action "Continue the matched task." \
  --provider "Example Provider" \
  --provider-input-tokens 1200 \
  --provider-output-tokens 300 \
  --retry-count 1 \
  --correction-count 0 \
  --session-output-characters 4800
```

Provider input and output counts must be supplied together with the provider name. These values are exact only to the extent that they were copied accurately from the provider report.

## Controlled benchmark protocol

A matched comparison should use:

- the same bounded task;
- the same project starting state;
- the same provider, model, settings, and tool permissions;
- one `with-forge` arm and one `without-forge` arm;
- exact provider input and output token counts;
- retry and correction counts;
- at least three matched pairs before an in-sample break-even conclusion.

Record each arm with a shared logical benchmark family and its arm:

```bash
--benchmark-id auth-flow-01 --benchmark-arm with-forge
--benchmark-id auth-flow-01 --benchmark-arm without-forge
```

The `without-forge` count may be entered after the control run; Forge is only storing the provider report. The recording action itself is not included in the supplied provider count unless the benchmark protocol intentionally includes it.

## Break-even language

- Fewer than three pairs: **insufficient-pairs**; break-even is unknown.
- Three or more pairs with lower aggregate exact tokens in the Forge arms: **observed-in-sample**.
- Three or more pairs without lower aggregate exact tokens: **not-observed-in-sample**.

An observed in-sample result is not a universal savings claim. Task quality, correctness, retries, model behavior, and project maturity still matter.

## Small-task warning

For a small one-off task, Forge overhead may exceed its benefit. Forge is expected to earn value through repeated continuity, authority reuse, and reduced rediscovery—not through ceremony on every trivial task.

## Field evidence is separate from token telemetry

Field observations may record time to meaningful work, reviewer judgments, Doctor recommendation outcomes, guardrail trigger outcomes, and usability scores. These are human- or fixture-supplied field evidence, not provider token measurement.

Exact provider token reports and field observations may be reviewed together, but Forge does not silently combine them into a causal savings or value claim. See `FIELD-VALIDATION.md`.
