# Forge Failure Context

When a required check fails, errors, or produces an unapproved blocking anomaly, Forge writes a deterministic bundle under:

```text
.forge/failures/<timestamp>-<profile>-<check-id>/
├── context.json
└── context.md
```

The bundle includes:

- exact check status, command, output, return code, duration, and evidence markers;
- reproduction command;
- files added, changed, or removed since the last green Gate;
- matching Forge Graph nodes and affected subsystems;
- approved Learn contracts touching the changed paths;
- current Doctor and expected-layout problems;
- execution anomaly evidence;
- the prior green profile and fingerprint.

Forge does not write prose root-cause conclusions or automatically modify code. It assembles replayable evidence so the active AI session or human reviewer can reason about cause and repair.
