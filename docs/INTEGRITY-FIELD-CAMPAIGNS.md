# Integrity Field Campaigns

Forge 0.544 includes a deterministic development instrument for exercising workspace and
artifact-integrity boundaries against synthetic public-neutral fixtures.

## Run the current campaign

From the Forge development source root:

```bash
python3 tools/run_integrity_campaign.py . \
  --output research/integrity-campaign-0.544.json
```

The receipt uses schema `forge-integrity-campaign/1` and binds the current source version,
environment, scenario results, and truth boundary.

## Six scenarios

1. **External writer after checkpoint.** A separate process mutates an observed file; the workspace
   must become `DRIFTED` and Ship may not use the old seal candidate.
2. **Package-source drift before publication.** The actual deterministic package builder writes its
   temporary archive, an external process changes a selected source, and the mandatory final recheck
   must refuse publication.
3. **Rival same-version artifacts.** Same basename and declared version with different exact bytes
   must report a collision.
4. **Filename/manifest disagreement.** A filename version that contradicts the packaged manifest
   must be visible as a failure.
5. **Explicit quarantine recovery.** Moving the rival into `.forge/quarantine/` must remove it from
   ordinary observation without rewriting either artifact.
6. **Project-owned ignore boundary.** Artifacts beneath an active `.forgeignore` pattern remain
   outside ordinary collision observation.

## Boundaries

A PASS proves only these declared local scenarios under the recorded environment. It does not prove
all filesystems, network shares, atomicity models, hostile processes, process identities, platforms,
branch merges, package consumers, or future versions. `.forgeignore` is a project-owned observation
boundary, not a confidentiality control, package exclusion, authority grant, or release fact.

## Portable separately invoked candidate protocol

Forge 0.549 retains the kit runner that preserves controller preparation, writer mutation, and reviewer
review. Controller preparation now first observes unbaselined `NOT_RUN`, records exact-fingerprint authority in a separate Adopt operation, and only then creates the passing checkpoint used by the drift trial.
finalization across three process invocations. It binds a challenge and exact target hashes to the
public runtime and requires Ship to observe workspace drift. The receipt records operator assertions
but cannot authenticate their independence or prove another operating system. See
`PORTABLE-EVIDENCE-KITS.md`.
