# Runtime State and Deployment Matrix

Forge can record project-owned runtime-state scenarios that bind external deployment and migration testimony to the exact candidate Forge knows about.

## What a matrix records

Each scenario declares:

- owner-controlled candidate identity fields;
- target environment and deployment stage;
- verification tier;
- prior persisted-state identity and source;
- owner-declared baseline field;
- migration mode and exact migration-file digests;
- required Runtime Proof recipe IDs;
- permitted evidence authorities (`owner` or `external-ci`);
- explicit exclusions and a verification boundary.

Record a matrix through Adopt:

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --record-runtime-matrix runtime-state-matrix.json
```

Evaluate supplied evidence and same-Check HTTP recipes together:

```bash
python3 Emotivus-Forge/forge.py check . \
  --run-capability runtime-proof \
  --runtime-state-evidence runtime-state-evidence.json
```

Retire a matrix only with authority and a reason:

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --retire-runtime-matrix staging-upgrade \
  --runtime-matrix-reason "Replaced by the next approved deployment scenario." \
  --runtime-matrix-authority owner
```

## Truth semantics

- No supplied scenario evidence is `NOT_RUN`, not PASS and not FAIL.
- Matching evidence plus passing same-Check Runtime Proof at the required tier is `CONFIRMED`.
- Candidate, baseline, environment, stage, prior-state, migration, authority, or runtime-recipe disagreement is `CONTRADICTED` and blocks Check.
- Changed matrix source, project identity, or migration bytes requires renewed authority.

## What Forge does not do

Forge does not deploy code, restore a database, execute migrations, inspect credentials, compare live data, prove rollback, or certify release readiness. The matrix verifies only that bounded owner/CI testimony agrees with the exact recorded candidate and same-Check Runtime Proof evidence.

## Token boundary

Full candidate bindings, migration hashes, evidence digests, and scenario details stay in local structured state and the Ledger. Resume reports only compact active, attention, retired, scenario, confirmed, and not-run counts plus actionable exceptions.
