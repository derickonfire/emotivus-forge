# Portable Evidence Execution Kits

Forge can package the exact public runtime, neutral task definition, standalone runner, and fillable
receipts needed to execute evidence workflows on another machine. The kit is an execution aid. It is
not evidence merely because it exists or verifies successfully.

## Build one exact kit

First build the public runtime, then bind the kit to those exact bytes:

```text
python3 tools/build_evidence_kit.py build \
  --runtime deploy/RUN-FORGE-0.549.zip \
  --output deploy/Emotivus-Forge-0.549-Evidence-Kit.zip
```

Verification checks deterministic timestamps, duplicate and unsafe member names, encrypted and
symbolic-link members, every declared payload digest and byte length, the sealed benchmark-task ID,
and the embedded runtime's packaged version.

```text
python3 tools/build_evidence_kit.py verify \
  --kit deploy/Emotivus-Forge-0.549-Evidence-Kit.zip
```

The manifest always begins with:

- `evidence_status: NOT_RUN`;
- `independent_evidence_claimed: false`;
- `release_authorized: false`;
- `private_key_retained: false`.

## Independent-writer candidate workflow

After extraction, the standalone runner supports three invocations:

```text
python run-evidence.py prepare-writer --workspace trial \
  --controller CONTROLLER_NAME \
  --controller-assertion "separately controlled"

python run-evidence.py writer --workspace trial \
  --writer WRITER_NAME \
  --writer-assertion "separately controlled"

python run-evidence.py finish-writer --workspace trial \
  --reviewer REVIEWER_NAME --accepted
```

Preparation creates a synthetic public-neutral project, extracts the exact bound runtime, records the
controller environment, confirms a neutral project-owned objective, and creates a passing checkpoint.
The writer step verifies the checkpoint-bound target bytes, changes them, and records before/after
hashes plus a challenge and writer environment. Finish runs exact-runtime Ship and requires
`workspace_integrity: DRIFTED` with `release_ready: false`.

A successful receipt is only a reviewed candidate. Forge records whether process IDs differed and
whether operator names assert separation, but it cannot authenticate people, administrative control,
or another operating system. Independent evidence remains a separate human and environment claim.

## Matched handoff benchmark workflow

```text
python run-evidence.py prepare-benchmark --output-dir benchmark \
  --provider PROVIDER --model MODEL
```

Preparation binds one immutable task to the exact runtime digest and creates distinct Forge and control
workspaces, arm instructions, and null token/reviewer templates. A template is explicitly `NOT_RUN`.

After both isolated provider runs, copy exact provider-reported input and output token counts into
`forge-run.json` and `control-run.json`. A named reviewer must accept each run against every criterion.
Then finalize:

```text
python run-evidence.py finalize-benchmark --packet-dir benchmark
```

Finalization uses Forge's exact benchmark instrument. It refuses missing or estimated tokens, changed
task/runtime/provider/model identity, incorrect arms, shared workspaces, or absent accepted review.
A `PAIRED` result describes only the exact sample; it is not a universal savings or quality claim.

## Truth boundary

The kit never moves a private key, never contacts a provider, never invents token counts, never
authenticates a reviewer, and never authorizes release. Preserve the original kit, completed receipts,
provider reports, and review record together for later evidence assessment.

## Deterministic evidence returns

Forge 0.549 adds `package-writer-return` and `package-benchmark-return` to the standalone evidence
runner. Each command emits one deterministic allowlisted ZIP bound to the exact original evidence kit.
The source-owned reviewer recomputes the writer or benchmark result and emits a content-addressed
review receipt with explicit duplicate status and non-authorizing claim scope. See
`docs/EXTERNAL-EVIDENCE-REVIEW.md`.
