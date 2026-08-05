# Forge Brief

`forge understand brief` (advanced alias: `forge brief`) creates a deterministic session-start digest for humans and AI coding agents.

```bash
python3 Emotivus-Forge/forge.py brief .
```

It reports the project and target version, declared next action, latest green Gate, whether the source fingerprint changed, Graph size, active learned contracts, Doctor status, and exact commands to regain a green working state.

Outputs:

- `.forge/brief/brief.json`
- `.forge/brief/brief.md`

Forge Brief does not infer intent or diagnose causes. It assembles current evidence so the active AI session can reason from durable state rather than reconstructing project history from memory.
