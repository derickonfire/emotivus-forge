# Authority and Native Evidence

## Authority confirmation

Forge discovers roadmap, release, decision, requirement, and verification candidates. It ranks active records above archived material, rejects unsupported objective fragments, may follow an explicit project-local authority link, and preserves owner confirmation.

```bash
forge adopt . --confirm-objective "Exact approved objective" --objective-source BACKLOG.md
forge adopt . --confirm-authority roadmap=BACKLOG.md
```

Confirmed values are written to `.forge/authorities.json` and recorded in `.forge/ledger.jsonl`. See `OBJECTIVE-AND-NATIVE-AUTHORITY.md`.

## Project-authority baseline

Objective authority, native execution authority, and project-tree authority are separate. A native-gate approval does not authorize the current project bytes. After reviewing the complete fingerprint printed by Check, project authority may record the exact current tree only through a separate Adopt operation:

```bash
forge adopt . --authorize-baseline <snapshot-sha256> \
  --baseline-reason "Reviewed and accepted this exact tree."
forge check . --checkpoint
```

Adopt refreshes preserve the observed checkpoint. Unexpected changes remain quarantined from authority-bound Ship claims until a new exact fingerprint is explicitly authorized. Forge does not authenticate the named authority or prove authorship. See `AUTHORITY-BASELINES.md`.

## Canonical native quality ecosystem

Forge selects one proposed canonical gate and catalogues subordinate or alternate tools under that ecosystem. It does not absorb their code or treat every helper as an independent authority.

```bash
forge adopt . --native-mode forge-authorized
forge adopt . --native-mode owner-only
forge adopt . --native-mode external-ci
forge adopt . --native-mode evidence-import-only
```

`--approve-native` remains a compatibility alias for `forge-authorized`. Every mode stores the candidate ID, exact command, fingerprint, and authority. A changed fingerprint requires reapproval.

## Direct execution

```bash
forge check . --run-native
```

Direct execution is available only in `forge-authorized` mode and only after explicit request. Owner-only, external-CI, and evidence-import-only modes block rather than bypass policy.

## Evidence import and retention

```bash
forge check . --import-native-evidence native-evidence.json
```

Imported owner or CI evidence must match the current candidate ID, gate fingerprint, execution mode, authority, and verification tier. Forge retains the exact imported record locally and returns only bounded summaries and references. It never reports an imported run as Forge execution.

Structured markers can describe check identity, status, evidence type, and affected surface. A direct process exit code and structured evidence must agree before Forge reports PASS.
