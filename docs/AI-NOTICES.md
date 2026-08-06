# Forge Notices

Forge should be visible when it changes the user’s understanding or protects the project—not when it merely reads state.

## AI response contract

Run, Adopt, Resume, Check, and blocked Ship JSON may include:

```json
{
  "ai_notice": {
    "schema": 1,
    "id": "notice-…",
    "level": "notice",
    "summary": "Checked 6 changed paths; runtime, deployment, and release assurance were not proven.",
    "category": "check",
    "speak": true,
    "repeated": false,
    "mode": "standard",
    "details": {}
  }
}
```

When `speak` is `true`, the active AI appends exactly one short line:

> **Forge —** Checked 6 changed paths; runtime, deployment, and release assurance were not proven.

When `speak` is `false`, omit the line. Do not paraphrase the notice into a stronger claim, invent an interaction, or replace the underlying findings with the branding line.

## Levels

- `silent` — no user-facing line;
- `notice` — meaningful learning, scoped success, or preserved handoff;
- `warning` — uncertainty, stale continuity, or unresolved attention;
- `blocker` — unsafe partial work, failed checks, corrupt state, or blocked Ship.

## Modes

Set `notice_mode` in `.forge/settings.json`:

- `quiet` — warnings and blockers only;
- `standard` — meaningful notices, warnings, and blockers;
- `visible` — reserved for integrations that want all meaningful notices. Forge still suppresses no-op and repeated events.

Stable notice IDs are retained inside `state.json`; the same event is not announced repeatedly.

## Guided continuation prompt

`recommended_prompt` is separate from `ai_notice`. The notice reports what Forge did; the recommended prompt tells the AI what to do next.

The active AI should render the copy-ready prompt exactly when present:

> **Forge recommends this prompt —** Continue this project from the exact next action: …

Do not expand it with detailed evidence unless the user asks. Do not use it to bypass blockers, native execution authority, decision authority, or the stated verification boundary.
