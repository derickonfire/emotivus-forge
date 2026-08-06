# Confirmed Relationship-Aware Change

Forge 0.513 can use project-owned relationship contracts to expand the impact of an canonical observed changed path without claiming that related paths changed.

## Supported relationship kinds

- `entrypoint-include`
- `import`
- `behavior-binding`
- `resource-consumer`
- `decision-path`
- `migration-effect`
- `test-covers`

Each relationship declares source and target path patterns, a propagation direction, affected surfaces, optional required checks, a reason, evidence paths, authority, and an explicit verification boundary.

## Record a relationship set

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --record-relationship-set forge-relationships.json
```

A changed or missing contract becomes `approval-required`. Retire a relationship set only through the authority path:

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --retire-relationship-set public-runtime \
  --relationship-set-reason "The project replaced this relationship model."
```

## Check behavior

During Scoped Check, Forge:

1. derives canonical observed changed paths from the observed checkpoint;
2. traverses only active project-owned relationships;
3. adds confirmed affected surfaces and required checks to the Check plan;
4. reports related paths separately from changed paths;
5. blocks when a required relationship endpoint disappears or the contract loses approval.

A related path is context, not a change claim. Forge does not automatically scan or run checks against the related path unless a project-native gate or another explicit rule selects it.

## Token boundary

Full relationships and path sets remain in project-owned contracts and local Check/Ledger records. Compact Resume reports only active-set, impact, related-path, and attention counts.

## What this does not prove

A current relationship contract does not prove runtime reachability, dynamic loading, correct behavior, complete consumer coverage, or that every project relationship has been recorded. Forge does not infer unrecorded relationships or delete code based on this model.
