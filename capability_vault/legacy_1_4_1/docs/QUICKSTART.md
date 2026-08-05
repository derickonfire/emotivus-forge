# Forge Quickstart

## The only first instruction

> **Run Forge.**

Place `Emotivus-Forge/` beside the fully extracted target-project source, work from the project root, and run:

```bash
python3 Emotivus-Forge/forge.py
```

Forge safely chooses the appropriate startup action:

- New project: Adopt + Resume
- Adopted and unchanged: Resume
- Changed project: Quick Check + Resume

Then read:

```text
.forge/passport/resume.md
```

Forge never Ships, deploys, deletes, migrates production data, or applies environment repairs through the zero-command startup.

## The five public commands

```bash
python3 Emotivus-Forge/forge.py help --project .
python3 Emotivus-Forge/forge.py adopt .
python3 Emotivus-Forge/forge.py resume . --budget compact
python3 Emotivus-Forge/forge.py check . --profile quick
python3 Emotivus-Forge/forge.py ship .
```

Use explicit Help when you want read-only guidance. Use explicit Ship only when preparing a handoff or deployment artifact.

Expert diagnostics remain available through `forge advanced`; they are not required for normal use. Git is not required.
