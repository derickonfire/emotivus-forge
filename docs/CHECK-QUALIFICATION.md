# Check Qualification

Forge distinguishes a check that **ran green** from a check whose current implementation has recorded evidence that it rejected declared known-bad inputs. Qualification is project-owned evidence about detector capability, not a guarantee of complete coverage.

## Qualification contract

A schema-1 qualification records:

- one qualification ID and native `check_id`;
- project authority;
- the current check source;
- verification tier;
- one or more known-bad cases whose expected and observed result are both `FAIL`;
- immutable evidence paths and fingerprints;
- documented limitations;
- scanned-surface count;
- an explicit truth boundary.

```bash
forge adopt . --record-check-qualification check-qualification.json
forge adopt . --retire-check-qualification membership-active-negative-proof \
  --check-qualification-reason "The project replaced this detector with a different implementation." \
  --check-qualification-authority owner
```

## Native evidence mapping

After an explicitly requested native run, Forge labels each reported check:

- `qualified` — the current check source and every negative-case evidence file still match the authority-recorded qualification;
- `unqualified` — no current qualification exists;
- `stale` — the check source, qualification source, or negative-case evidence changed or disappeared.

The observed native result remains separate. A stale qualification does not rewrite a real native PASS or FAIL; it changes only what Forge may claim about the detector's demonstrated capability.

Detailed cases, limitations, fingerprints, and surface counts stay in structured local state. Resume reports compact qualified, unqualified, stale, and attention counts.

## Boundary

Qualification proves only that the recorded implementation rejected the declared bad cases at the recorded boundary. It does not prove semantic correctness, complete query discovery, absence of false positives or false negatives, runtime fidelity, or release readiness.
