# Cold-Session Validation

Forge 0.528 evaluates schema-2 matched fresh-agent campaigns as bounded field evidence. The campaign separates the exact Forge runtime from the exact host release package and refuses to count controlled fixtures as real matched-session coverage.

## Why schema 2 exists

Schema 1 could establish a PASS from structurally valid fixture receipts, did not require current observation dates, did not bind a shared task packet and host-baseline manifest, and used the host final-package digest as though it were the Forge runtime digest. Those limitations are incompatible with a real field-evidence claim. Existing schema-1 records remain visible as legacy state but must be replaced before `cold-session-validated` can pass.

## Campaign contract

Copy `examples/forge-cold-session-validation.example.json` into the host project and record it through Adopt.

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --record-cold-session-validation forge-cold-session-validation.json
```

The schema-2 contract binds:

- one active host release-package ID;
- one project-owned exact Forge runtime artifact, including SHA-256 and byte length captured at recording time;
- minimum human-reviewed matched pairs;
- minimum model, distinct task-packet, and distinct host-baseline coverage;
- optional minimum external-review pair coverage;
- maximum receipt age;
- required scenarios;
- authority-approved objective, first-action, and owner-correction thresholds;
- immutable project-owned pair-receipt paths and an explicit truth boundary.

Changing the contract source or bound runtime artifact invalidates the campaign until the current contract is recorded again.

## Pair receipts

Each schema-2 pair receipt binds both arms to:

- the exact host release package digest and byte length;
- the exact Forge runtime digest and byte length;
- one provider, model, and model-settings fingerprint;
- one immutable task packet;
- one immutable host-baseline manifest;
- distinct fresh session IDs;
- a declared arm order;
- a current observation timestamp;
- arm-specific immutable evidence and measured outcomes.

The receipt must explicitly confirm that both arms used the same provider, model, settings, and task packet; sessions were isolated; the Forge arm used the exact bound runtime; and the control arm had no Forge access.

## Human and fixture evidence

`owner`, `human-reviewer`, and `external-reviewer` receipts may count toward the campaign minimums. `controlled-fixture` receipts remain useful for deterministic regressions and protocol rehearsal, but they are reported separately and do not count toward human pair, model, task, baseline, scenario, or threshold coverage.

Forge validates structure, exact bytes, timestamps, arithmetic, and declared matching conditions. It does not authenticate reviewer identity, prove that isolation actually occurred, establish causal superiority, verify provider billing reports, or generalize beyond the measured sample.
