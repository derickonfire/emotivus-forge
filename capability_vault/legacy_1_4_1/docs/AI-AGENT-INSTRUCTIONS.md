# Forge Instructions for Coding Agents

Treat `Emotivus-Forge/` as a separate local control and assurance system. Do not merge its files into the host application.

## Before editing

When the operator says **“Run Forge,”** do the following without asking them to choose a Forge command:

1. Ensure the target project and Forge are fully extracted.
2. Work from the target-project root.
3. Run:

```bash
python3 Emotivus-Forge/forge.py
```

4. Read `.forge/passport/passport.md` and `.forge/passport/resume.md`.
5. Report material blockers, uncertainty, and the current objective before modifying source.

The zero-command launcher may automatically Adopt, Resume, or perform Quick Check. It must never automatically Ship, deploy, delete, run production migrations, apply environment repairs, or bypass a blocker.

## While changing code

- Keep work bounded to the current objective or explicitly update the durable project record.
- Preserve accepted decisions, confidentiality boundaries, migrations, runtime contracts, and learned regressions.
- Use advanced controls only when the task requires them.
- Do not infer that missing evidence passed.
- Run explicit Check after meaningful work when a deeper or chosen profile is required.

```bash
python3 Emotivus-Forge/forge.py check . --profile quick
```

A Quick Check pass is scoped. It does not imply upgrade, target-environment, final-artifact, staging, or production proof.

## Before delivery

```bash
python3 Emotivus-Forge/forge.py ship .
```

Ship requires explicit operator intent. Never invoke it merely because Forge recommends a future delivery step.

## Permanent boundary

Forge remembers, inventories, measures, and evidences. The coding agent interprets evidence and repairs or extends the host project. Never weaken a check, enlarge a baseline, retire a contract, suppress evidence, or alter a claim merely to finish the task.

## Confidential host-data boundary

- Treat host source, datasets, fixtures, reports, credentials, and private policies as host-owned.
- Do not copy host content into Forge Core, examples, tests, documentation, or distributions.
- Use project-relative paths, hashes, typed relationships, and evidence references for continuity.
- Never weaken confidentiality findings merely to complete a package.
