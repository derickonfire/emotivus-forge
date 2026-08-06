# First Contact

Forge is a separate project-continuity and assurance layer. Place the intact `Emotivus-Forge/` folder beside the host-project source. Do not merge Forge files into the application.

## User instruction

> **Run Forge.**

## AI or human sequence

1. Fully extract the target project and Forge.
2. Work from the host-project root.
3. Run Forge with no command:

```bash
python3 Emotivus-Forge/forge.py
```

4. Forge automatically performs Adopt + Resume, Resume, or Quick Check + Resume according to the current state.
5. Read `.forge/passport/resume.md` before editing.
6. Read only the task-relevant source and durable records identified by Resume.
7. Run Forge again after returning to the project; changed files automatically trigger Quick Check.
8. Use explicit `forge ship .` only when creating a delivery.

Forge should inventory, remember, scope, and evidence the project. The active human or AI still interprets intent and writes the product code.

## Safety

The zero-command startup never Ships, deploys, deletes data, applies production migrations, repairs the environment, or bypasses a failed check.

## Existing tools

First contact inventories existing project tools without removing them. Tool adoption, replacement, or quarantine is an advanced reviewed operation, not an automatic side effect of Run Forge or Adopt.
