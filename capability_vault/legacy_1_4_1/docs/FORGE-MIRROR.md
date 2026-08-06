# Forge Mirror

Forge Mirror is the mandatory production-certification system for Emotivus Forge itself. It exists because unit tests and fixture-project acceptance do not prove that Forge can govern its own source tree or that the final distribution retains the behavior verified before packaging.

## Trust model

Mirror uses two layers:

1. **Forge Bootstrap** — a deliberately small standard-library validator that imports no Forge modules. It compiles Python, validates JSON, verifies canonical paths and version agreement, launches the CLI, and inspects distribution archives.
2. **Forge self-hosting** — an isolated copy of Forge is initialized as a strict Forge project and must pass tool identity, Graph, Impact, Learn, Lab, Quick, Section, and Release evidence.

This prevents circular trust. Forge performs the sophisticated certification only after the independent bootstrap establishes that Forge is intact enough to begin.

## Production command

```bash
python3 forge.py prove mirror . \
  --baseline 1.0.2 \
  --release 1.0.3 \
  --output deploy/Emotivus-Forge-1.0.3-Internal.zip
```

Optional `--changed` values improve the Impact report. `--preserve-workspace` retains the isolated self-hosting tree after a failure for diagnosis.

## Required sequence

1. Bootstrap-validate the source without trusting Forge Core.
2. Copy Forge into an isolated workspace.
3. Detect Forge identity and its canonical Python version source.
4. Initialize the copied tree with Strict assurance and no inherited-warning baseline.
5. Inventory existing tooling while recognizing active Forge Core as retained first-party tooling.
6. Build Forge Graph and calculate release blast radius.
7. Enforce the committed contracts in `self/learned-contracts.json`.
8. Run Forge-specific CLI lifecycle, documentation, and bootstrap Labs plus the complete self-test Gate.
9. Pass fresh Quick, Section, and Release Gates.
10. Build the portable distribution from `FORGE-MANIFEST.json`.
11. Inspect and bootstrap-validate the archive.
12. Extract the archive and rerun the full self-test suite.
13. Use the extracted release to initialize and check a fresh neutral project.
14. Write JSON and text Mirror reports with the final SHA-256.

## Security fixtures

Forge no longer treats the literal text of its own security detector as private-key material. It looks for actual PEM block structure. Synthetic credential values must live in a configured fixture path or be declared with a narrow adjacent annotation:

```text
# forge: synthetic-secret
```

or:

```text
# forge: synthetic-private-key
```

These declarations suppress only the adjacent synthetic example; they do not exempt a file or directory from security scanning.
