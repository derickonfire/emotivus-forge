# Forge Help

`forge help` is the fifth primary command and the explicit read-only guide. The natural first instruction is **“Run Forge.”**

## Purpose

A new user or coding agent should not need to remember Forge architecture or guess which operation comes next. Help safely reads the local project state and returns:

- whether the project is adopted;
- the current objective;
- the number of paths changed since the last Forge observation;
- the strongest current proof claim;
- the current project token-equivalent baseline after adoption;
- one exact recommended next command;
- the reason for that recommendation.

Help is read-only. It does not create state, run checks, alter source, or build an artifact.

## Commands

```bash
forge help
forge help --project .
forge help adopt
forge help resume
forge help check
forge help ship
forge help advanced
forge help --project . --json
```

Running `forge` without a command starts the safe automatic launcher: Adopt + Resume for a new project, Resume for an unchanged project, or Quick Check + Resume when files changed. This launcher is not a sixth public command. Use `forge help` when read-only guidance is specifically desired.

## Recommendation rules

- No Forge configuration: recommend Adopt.
- Forge configuration without a Passport: recommend Adopt.
- Source changes since the last observation: recommend Quick Check.
- No changes: preserve the Project Passport's current next action, normally Resume or a deeper Check.

## Interface contract

Normal users learn only five commands: Help, Adopt, Resume, Check, and Ship. Advanced engines may grow without expanding the normal vocabulary. The canonical launcher is `forge`. The optional `frg` alias exists only for local command-name conflicts and does not change the five-command interface.
