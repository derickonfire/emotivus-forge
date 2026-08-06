# Initial-Run Configuration

Forge v1.0.2 turns initialization into a recorded configuration process rather than a single opaque command.

## Guided mode

```bash
python3 Emotivus-Forge/forge.py init . --guided
```

Guided mode asks for:

1. Project name
2. Assurance preset
3. Deployment target
4. Versioning strategy
5. Test requirement
6. Documentation requirement
7. New-warning policy
8. Inherited warning/info baseline policy
9. Existing-tool handling
10. Required files in every deployment package
11. Live systems requiring manual verification

## Presets

### Prototype

Optimizes for iteration speed while preserving non-baselinable safety blockers.

### Balanced

Recommended default for active internal projects. Existing projects may baseline inherited warning and informational debt, while blockers and errors remain active.

### Strict

Requires tests and documentation, fails on new warnings, and does not automatically baseline inherited advisories.

### Legacy

Designed for established projects with substantial inherited structure. It records debt without treating it as newly introduced.

## Answers file

```json
{
  "project_name": "My Project",
  "preset": "balanced",
  "deployment": "cpanel",
  "versioning": "semver",
  "tests": "required",
  "documentation": "optional",
  "warnings": "allow",
  "baseline": "auto",
  "existing_tools": "audit",
  "required_files": [".htaccess"],
  "live_checks": ["browser", "database", "cron", "api"]
}
```

Run it with:

```bash
python3 Emotivus-Forge/forge.py init . --answers forge-setup.json
```

The resulting decisions are saved to `.forge/SETUP-DECISIONS.json`. This file is evidence of intent and should be reviewed before changing the project contract.

## v1.0.2 intelligence choices

Initial setup also records whether Forge Graph is enabled, whether Forge Learn defect memory is active, and whether Forge Lab is disabled, planned, or required for release. Inferred lab recipes remain manual unless explicitly assigned to a profile.
