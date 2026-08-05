# Forge Learn

Forge Learn converts a confirmed defect into reviewed project memory. It never activates a proposal automatically.

## Lifecycle

1. Record the symptom, verified root cause, approved fix, invariant, affected files, and proposed regression.
2. Forge maps the affected files to Forge Graph subsystems.
3. Forge recommends a gate and writes a proposal.
4. A human or responsible coding agent reviews and edits the proposal.
5. Approval activates the contract.
6. Future audits or configured commands enforce it.

## Propose

```bash
python3 Emotivus-Forge/forge.py learn . --action propose --input .forge/learn/defect.json
```

Required input fields:

- `title`
- `invariant` or `approved_behavior`

Recommended evidence:

- `symptom`
- `root_cause`
- `fix`
- `severity`
- `category`
- `affected_paths`
- `regression`

Supported automated regressions:

- `file_exists`
- `file_contains`
- `file_not_contains`
- `json_value`
- `graph_node`
- `command`

`manual` contracts are allowed when behavior cannot yet be automated, but they remain explicit checklist work rather than pretending to be a passing automated test.

## Approve or reject

```bash
python3 Emotivus-Forge/forge.py learn . --action approve --id learn-example-12345678
python3 Emotivus-Forge/forge.py learn . --action reject --id learn-example-12345678 --reason "The invariant was too implementation-specific."
```

Approved static contracts are evaluated during Forge audit. Approved command contracts are added to the selected Quick, Section, or Release Gate. Learned-contract violations cannot be hidden by the inherited-debt baseline.

## Files

- `.forge/learn/proposals/`
- `.forge/policies/learned-contracts.json`
- `.forge/LEARNED-MANUAL-CHECKLIST.md`
