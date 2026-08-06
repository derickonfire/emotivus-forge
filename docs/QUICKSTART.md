# Quickstart

Place the exact public runtime folder `Emotivus-Forge/` inside the target project root, then run from
the target project root:

```bash
python3 Emotivus-Forge/forge.py
```

Read `.forge/resume.md` before editing. Run Forge also prints one short, copy-ready continuation instruction:

> **Forge recommends this prompt —** Continue this project from the exact next action: …

Copy that prompt into the active AI conversation. If Forge reports a blocker or cannot confirm the objective, the prompt tells the agent to stop before changing code. See `GUIDED-NEXT-PROMPT.md`.


## Developing Forge with Forge

The development source is the target project; it is not the runtime folder for that invocation.
Create this layout:

```text
Emotivus-Forge-Project/
├── FORGE-MANIFEST.json
├── emotivus_forge/
├── tests/
└── Emotivus-Forge/      # exact extracted public runtime
```

From `Emotivus-Forge-Project/`, run `python3 Emotivus-Forge/forge.py`. Do not run source-root
`python3 forge.py` for self-development: that command treats the source root as the runtime and has
no separate host project beside it.

## Confirm uncertain authority

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --confirm-objective "Implement the approved authentication flow." \
  --objective-source BACKLOG.md
```

## Run scoped Check

```bash
python3 Emotivus-Forge/forge.py check .
```

Forge derives changed paths from the observed checkpoint. Any `--changed` path is corroboration-only.
On an unbaselined tree, clean component observations produce aggregate `NOT_RUN`, not PASS. Review the
reported exact fingerprint, then record authority as a separate operation and checkpoint:

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --authorize-baseline <EXACT_SHA256_FROM_CHECK> \
  --baseline-reason "Reviewed and accepted this exact tree."
python3 Emotivus-Forge/forge.py check . --checkpoint
```

A real detected defect remains `FAIL` before or after authority.

## Approve and run the native gate

```bash
python3 Emotivus-Forge/forge.py adopt . --approve-native
python3 Emotivus-Forge/forge.py check . --run-native
```

## Activate bounded Doctor diagnosis

Copy `examples/doctor-activation-contract.example.json` into the target project, replace its evidence path and scope with real project facts, then run:

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --activate-capability doctor \
  --capability-contract forge-doctor-contract.json
python3 Emotivus-Forge/forge.py check . --run-capability doctor
```

Doctor does not repair or mutate the environment. A changed contract requires explicit reactivation. See `ADVANCED-CAPABILITIES.md`.

## Record project identity

Copy `examples/project-identity.example.json` into the target project and replace the example values with owner-declared identity.

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --record-identity forge-project-identity.json
```

Forge never chooses these values. It rejects monotonic rollback and reports only a compact identity summary in Resume. See `PROJECT-IDENTITY.md`.

## Record an expiring obligation

Record an `event-obligation` guardrail before the temporary window closes:

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --record-guardrail event-obligation.json
```

When the observable event occurs, confirm it with project evidence:

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --confirm-project-event production-domain-confirmed \
  --project-event-evidence DOMAIN-DECISION.md
```

After closure, Check blocks until every declared obligation is addressed and project authority reviews and retires or replaces the guardrail. See `GUARDRAILS.md`.

## Close a completed session

```bash
python3 Emotivus-Forge/forge.py check . \
  --checkpoint \
  --close-session \
  --session-type code-increment \
  --completed "Implemented the approved bounded change." \
  --risk "Browser behavior remains unverified." \
  --next-action "Run the browser verification fixture."
```

Ship remains explicit and evidence-bounded. `release-ready` can pass only when every cumulative project-declared requirement and the separate exact-package authorization are current.

## Record a field-validation trial

Copy the field-trial and field-observation examples into the target project and replace their sources and labels with real project facts.

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --record-field-trial forge-field-trial.json

python3 Emotivus-Forge/forge.py check . \
  --close-session \
  --next-action "Run the next declared field scenario." \
  --field-observation field-observation-001.json
```

Forge aggregates the reviewer-supplied local sample but does not grade itself or turn the results into a universal product claim. See `FIELD-VALIDATION.md`.

## Truth states

Read `truth_summary`, `self_currency`, and native `truth` objects before describing a Check. `NOT_RUN` is not a PASS, `BLOCKED_UNATTEMPTED` means no execution occurred, and `BLOCKED_ATTEMPTED` means an execution attempt could not complete. Resume keeps only a compact exception summary; detailed records remain in JSON and `.forge/ledger.jsonl`.
## Record artifact provenance

After the project-owned generator creates an artifact, record its lineage with `forge adopt . --record-artifact-provenance forge-artifact-provenance.json`. See `ARTIFACT-PROVENANCE.md`.



## Record a deployable boundary

Copy `examples/deployable-boundary.example.json`, define project-owned delivery roles and any registered delta artifacts, then run:

```bash
python3 Emotivus-Forge/forge.py adopt .   --record-deployable-boundary forge-deployable-boundary.json
```

See `DEPLOYABLE-BOUNDARY.md`.

## Record canonical claims

Copy `examples/canonical-claims.example.json`, replace every source and statement with explicit project-owned truth, then run:

```bash
python3 Emotivus-Forge/forge.py adopt .   --record-canonical-claims forge-canonical-claims.json
```

See `CANONICAL-CLAIMS.md`.

## Native execution authority

```bash
forge adopt . --native-mode owner-only
forge check . --import-native-evidence native-evidence.json
```

Use `forge-authorized` only when the project authority permits Forge to execute the current fingerprint. See `OBJECTIVE-AND-NATIVE-AUTHORITY.md`.

## Record a runtime-state matrix

After recording project identity and activating bounded Runtime Proof, copy the matrix and evidence examples into the project and replace every placeholder with project-owned facts:

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --record-runtime-matrix runtime-state-matrix.json

python3 Emotivus-Forge/forge.py check . \
  --run-capability runtime-proof \
  --runtime-state-evidence runtime-state-evidence.json
```

No evidence means `NOT_RUN`. Forge does not deploy, restore state, or execute migrations. See `RUNTIME-STATE-MATRIX.md`.

## Establish project-tree authority

After first adoption, run Check and review the complete fingerprint:

```bash
forge check .
forge adopt . --authorize-baseline <snapshot-sha256> --baseline-reason "Reviewed and accepted this exact tree."
forge check . --checkpoint
```

Do not combine baseline authorization with unrelated Adopt options. A passing Check without explicit authorization remains only an observed checkpoint.



## Record exact migration identity

After recording exact project lineage, copy either `examples/forge-migration-catalog.example.json` or `examples/forge-no-migrations.example.json` into the project and replace every placeholder with exact project-owned facts:

```bash
forge adopt . --record-migration-catalog forge-migration-catalog.json
```

Retire a catalog separately before recording its replacement. A legacy ledger containing only sequence numbers remains body-unknown. See `MIGRATION-IDENTITY.md`.

## Record exact lineage before relying on branch ancestry

Create a project-owned lineage contract using the shape in `examples/forge-lineage.example.json`, then record it as a separate Adopt operation:

```bash
forge adopt . --record-lineage path/to/project-lineage.json
```

For an incoming branch or changed package, use `examples/forge-merge-candidate.example.json` and quarantine it before reconciliation:

```bash
forge adopt . --record-merge-candidate path/to/merge-candidate.json
forge adopt . --resolve-merge-candidate candidate-id=approved-for-reconciliation \
  --merge-candidate-reason "Reviewed ancestry and selected manual reconciliation only."
```

A merge-candidate decision never applies or authorizes the branch. After manual reconciliation, record a new exact lineage, obtain project-tree authority, and run a fresh Check checkpoint.


## Record authoritative packaged release facts

After exact lineage, package-family, surface, and native evidence are current, record a separate project-owned fact contract:

```text
forge adopt . --record-release-facts forge-release-facts.json
```

This operation validates declared visible values inside one exact result artifact. It does not inspect arbitrary prose.
