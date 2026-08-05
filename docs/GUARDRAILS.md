# Safety Guardrails

Forge guardrails preserve authority-confirmed project rules that must influence future Check behavior. They are project-owned JSON contracts recorded through **Adopt**; Forge does not infer or activate them from chat prose.

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --record-guardrail guardrail.json
```

Forge supports two bounded modes.

## Atomic change sets

`mode: atomic-change-set` binds at least two named project surfaces that must appear in one canonical observed change set. This is appropriate when a partial implementation would be misleading or unsafe—for example, a public dietary label whose storage, editor control, and public rendering must land together.

See `examples/atomic-guardrail.example.json`.

Check behavior:

- no trigger path changed → `NOT_APPLICABLE`;
- some required surfaces changed → blocker and Scoped Check FAIL;
- every declared surface changed → atomic guardrail PASS;
- contract changed or disappeared → related work is blocked until the authority records the current source again.

A PASS proves only declared change-set coverage. It does not prove correctness, feature completion, migration safety, browser behavior, deployment safety, or release readiness.

## Event-triggered obligations

`mode: event-obligation` represents a temporary condition that is valid only until an observable project event closes its free-change window.

See `examples/event-obligation.example.json`.

The contract declares:

- `closes_at.event_id` and a human-readable event description;
- one or more blocked/revisit surfaces;
- why leaving the temporary state after closure is unsafe;
- the verification boundary.

Before the event is confirmed, the guardrail is `WAITING_FOR_EVENT` and does not create noise. The project authority confirms the event with project evidence:

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --confirm-project-event production-domain-confirmed \
  --project-event-evidence DOMAIN-DECISION.md \
  --project-event-authority owner
```

After confirmation:

- missing obligated surfaces block Check;
- touching every declared surface changes the result to `AUTHORITY_REVIEW_REQUIRED`;
- Check remains blocked until project authority reviews the result and retires or replaces the obligation.

Forge does not automatically declare the obligation satisfied merely because files changed.

## Retirement

Retirement requires authority and a durable reason:

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --retire-guardrail production-domain-window \
  --guardrail-reason "The confirmed domain replaced every temporary placeholder after review." \
  --guardrail-authority owner
```

Retirement is appended to the Ledger and never erases the original rule or closing event.

## Storage and token boundary

Contracts, events, normalized content, and fingerprints stay in existing `settings.json` and `ledger.jsonl`; no ninth first-contact state file is added. Compact Resume carries a brief active-rule summary rather than the full contract.
