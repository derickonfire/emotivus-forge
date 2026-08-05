# Run Forge Experience and Session Reconciliation

Forge 0.543 restores **Run Forge** as the primary product hook.

## Operating model

Run Forge performs one bounded active pass, normally targeting one to five minutes of project work, then enters passive sidecar mode.

The active pass performs these phases:

1. exact project identity and persisted-state integrity;
2. current continuity, authority, lineage, migration, package, and evidence orientation;
3. optional review of one transient distilled session-context file;
4. changed-path and affected-surface inspection;
5. safe bounded checks already authorized by the project;
6. request, AI-claim, code-path, and evidence reconciliation;
7. one concise Forge Brief.

After the Brief, Forge becomes passive until a meaningful checkpoint, package import, migration, unexpected mutation, Session Close, or Ship request.

## Session context boundary

The active AI may provide a small JSON digest:

```json
{
  "schema": "forge-session-context/1",
  "source_kind": "active-ai-distilled",
  "objective": "Repair remembered login.",
  "requested_items": ["Fix login persistence in login.py"],
  "ai_claims": ["Login persistence was completed in login.py"],
  "decisions": ["Keep the existing session architecture"],
  "rejected_options": ["Do not add a hosted identity provider"],
  "next_action": "Run the browser persistence fixture."
}
```

```bash
forge run . --session-context session-context.json
```

Forge rejects raw `messages`, `transcript`, `conversation`, or `chat` fields. The digest is reviewed transiently and is not copied into the eight-file continuity unit.

## Reconciliation truth boundary

Forge may find that a request or claim refers to changed or checked paths. That is orientation evidence only. It does not prove semantic completion, browser behavior, database correctness, or release readiness.

AI claims remain claims until separate project evidence supports them.

## Session Close

A successful Check plus Session Close now regenerates compact `resume.md` automatically. The operator no longer needs to run a separate Resume command merely to make the just-closed session visible to the next AI.

## Public model

The engine retains Help, Adopt, Resume, Check, and Ship for compatibility and explicit control. The normal product experience is:

- **Run Forge** — active orientation and reconciliation, then passive sidecar;
- **Check** — explicit meaningful verification checkpoint;
- **Ship** — exact-package release assessment.

Adopt and Resume remain available as advanced lifecycle operations and artifacts rather than equal first-contact choices.
