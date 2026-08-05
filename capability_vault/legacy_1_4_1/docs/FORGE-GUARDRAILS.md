# Forge Guardrails

Forge can convert a resolved structural anomaly into an inactive Learn proposal. It never activates the rule automatically.

## Supported events

- `zero-byte-file`
- `hostile-filename`
- `required-artifact`
- `forbidden-artifact`
- `required-content`
- `forbidden-content`

Example event:

```json
{
  "type": "zero-byte-file",
  "path": "dist/stray-file",
  "symptom": "A zero-byte artifact entered a prior delivery.",
  "root_cause": "A packaging command created an unintended path.",
  "resolution": "The artifact was removed.",
  "severity": "error",
  "gate": "release"
}
```

Propose, review, and approve:

```bash
python3 Emotivus-Forge/forge.py guardrail . --action propose --input guardrail-event.json
python3 Emotivus-Forge/forge.py guardrail . --action list
python3 Emotivus-Forge/forge.py guardrail . --action approve --id <proposal-id>
```

Forge generates the narrowest supported invariant, such as `file_not_exists` or `file_nonempty`. The proposal remains editable and inactive until approval. Project-specific guardrails remain project-specific unless deliberately promoted into a reusable adapter or Forge Core after independent review and regression testing.
