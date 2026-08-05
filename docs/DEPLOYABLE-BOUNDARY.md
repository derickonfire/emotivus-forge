# Deployable Boundary

Forge can record a project-owned schema-1 contract that classifies changed paths by delivery role and, when configured, compares a registered delta ZIP against the authoritative allowed changed set.

## Why this exists

A changed file is not automatically deployable. Projects often change source, tests, planning, release evidence, generated archives, and private operator material in one session. Forge keeps those categories explicit rather than treating one undifferentiated changed-file list as a delivery package.

## Contract behavior

A boundary defines:

- authority and a project-owned source file;
- named roles with glob patterns;
- whether unclassified changed paths block;
- roles prohibited from registered delivery artifacts;
- optional registered delta artifacts;
- exact or subset path-set comparison;
- the baseline build for which a delta was computed;
- an explicit verification boundary.

Every canonical observed changed path must match zero, one, or several roles. Overlap always blocks. Unclassified paths block when `strict_unclassified` is true and otherwise produce a warning.

A delta artifact references an active artifact-provenance record. Forge reads the current ZIP members, compares them with the allowed canonical observed changed paths, and verifies that the declared delta baseline still matches the owner-declared project baseline.

## Commands

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --record-deployable-boundary forge-deployable-boundary.json

python3 Emotivus-Forge/forge.py adopt . \
  --retire-deployable-boundary release-boundary \
  --deployable-boundary-reason "The delta workflow was retired."
```

## Truth boundary

A passing boundary proves only that the current canonical observed changed set was classified without prohibited overlap and that configured delta members match the declared allowed path set and baseline. It does not prove the package works, deployment occurred, the live baseline is correct beyond the owner declaration, or the release is ready.
