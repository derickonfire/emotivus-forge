# Forge Internal Delivery

Forge distinguishes two package profiles.

## Deployment

A production-facing ZIP that excludes Forge Core, `.forge/`, internal configuration, tests, planning material, CI files, credentials, and continuity archives.

```bash
python3 Emotivus-Forge/forge.py package . --profile deployment
```

## Internal

A working-session delivery containing:

- `Project-Source.zip` with the host source and intact `Emotivus-Forge/` installation.
- `Forge-State.zip` with portable assurance memory.
- A machine-readable manifest and restoration instructions.

```bash
python3 Emotivus-Forge/forge.py package . --profile internal
```

The internal profile is still secret-scanned and blocks unsafe filenames, path collisions, symlinks, and undeclared zero-byte artifacts. It is not a public deployment package.
