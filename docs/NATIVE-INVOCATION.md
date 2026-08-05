# Exact Native Invocation

Detecting a native gate is not enough. Forge must know the exact invocation the project authority intends:

- command and every argument;
- project-relative working directory;
- bounded non-secret environment overrides;
- expected check identifiers or expected check count;
- exact or at-least coverage policy;
- timeout and verification tier.

Record the project-owned contract through Adopt:

```bash
forge adopt . \
  --native-mode owner-only \
  --native-invocation forge-native-invocation.json
```

For Forge-authorized execution:

```bash
forge adopt . \
  --native-mode forge-authorized \
  --native-invocation forge-native-invocation.json

forge check . --run-native
```

Forge executes the argument vector directly without a shell expansion. The command must begin with the detected canonical command. Working directories must stay inside the project. Secret-shaped environment keys are rejected because Forge state is not a credential store.

## Coverage fidelity

A zero exit code is not sufficient. The contract must declare `expected_checks` or `expected_count`. Forge compares the checks actually reported by the native gate with that expectation.

Missing gate members remain `NOT_RUN`, and the native result fails its coverage contract. An exact policy also rejects undeclared extra members so a changed gate requires renewed authority instead of silently changing the meaning of PASS.

## Renewal

Approval is bound to both:

- the native-gate source fingerprint;
- the normalized invocation fingerprint.

Changing the script, arguments, working directory, environment, timeout, expected coverage, or contract file requires reapproval.

## Claim boundary

Exact invocation proves what Forge or an evidence provider was instructed to run and whether the declared members reported. It does not prove that the gate itself is correct, exhaustive, qualified, or sufficient for release readiness.
## Roadmap status

Native invocation fidelity is approximately **100% implemented** for the current controlled-core scope. Real project variation may still produce new compatibility requirements.

