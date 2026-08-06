# Forge Project Passport

The Project Passport is the durable, portable summary of the project’s current truth and assurance boundary.

## Location

```text
.forge/passport/passport.json
.forge/passport/passport.md
```

Related continuity outputs:

```text
.forge/passport/adopted-snapshot.json
.forge/passport/observed-snapshot.json
.forge/passport/check-snapshot.json
.forge/passport/resume.json
.forge/passport/resume.md
.forge/passport/check.json
.forge/passport/proof-card.json
.forge/passport/proof-card.md
```

## Sections

### Identity

Project name, stable identity, target version, Forge version, workspace classification, deployment target, and classification confidence.

### Structure

Detected adapters and runtimes, graph summary, discovered executable and user-facing surfaces, and current recurring-evidence coverage.

### Continuity

Current objective, active plan, active pivot, durable record counts, learned contracts, last green result, whether source changed since that result, and the project token-equivalent baseline used to measure Resume efficiency.


### Token efficiency

The Passport records the current project snapshot's file count, byte count, token-equivalent estimate, default compact Resume budget, and estimation method. Resume adds the actual packet estimate, estimated context avoided, reduction percentage, and whether the packet stayed within budget.

This is a transparent planning heuristic. It must not be represented as exact model usage, provider billing, prompt caching, or guaranteed savings.

### Safety

Doctor status, environment and layout problems, source-completeness status, current work scope, and packaging-policy contradictions.

### Evidence

Strongest required claim, claim status, uncovered surfaces, target-environment status, deployment-state status, delivery provenance, problems, and limitations.

### Changes

Per-file added, modified, and removed paths since the previous Forge observation. This mechanism uses project-relative paths and SHA-256 hashes and does not require Git.

### Uncertainties

Forge must preserve uncertainty instead of converting a weak inference into a fact. Current uncertainty areas include workspace authority, source completeness, surface coverage, environment parity, persisted-state proof, and Doctor problems.

### Next action

One recommended public command and a reason. This is derived from the current Passport rather than maintained as a generic command list.

## Checkpoint behavior

- **Adopt** creates the initial adopted and observed snapshots.
- **Resume** compares the working tree to the latest observation but does not advance it.
- **Check** compares, calculates impact, runs proof, then advances the observed snapshot.
- **Ship** runs fresh Release proof and writes a Proof Card; it does not hide unsupported claims.

## Privacy boundary

Snapshots store project-relative paths, file size, type, and SHA-256 hash. They do not copy host file contents into Forge Core or public distributions.
