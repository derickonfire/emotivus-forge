# Forge Graph

Forge Graph creates a neutral, machine-readable architecture model before Forge attempts blast-radius reasoning.

## What it maps

- Source files, entry points, templates, styles, tests, migrations, configuration, webhooks, and scheduled jobs
- Relative PHP, JavaScript, HTML, and Python dependencies
- Routes and handlers detected from common framework-neutral patterns
- Environment variables
- External service hosts
- Database, authentication, upload, webhook, and scheduling indicators
- Test-to-source relationships inferred from imports, references, and naming

## Build the graph

```bash
python3 Emotivus-Forge/forge.py graph .
```

Outputs:

- `.forge/graph/project-graph.json`
- `.forge/graph/project-graph.md`

Graph output is evidence, not omniscience. Dynamic imports, generated routes, reflection, runtime dependency injection, and remote infrastructure may require a project policy pack or manual correction.

## Blast-radius analysis

```bash
python3 Emotivus-Forge/forge.py impact . --changed src/auth/login.php --changed assets/login.js
```

When `--changed` is omitted, Forge tries Git's staged, unstaged, and untracked paths. The impact report identifies:

- Direct and transitive dependencies
- Important nodes in affected subsystems
- Risk score and level
- Targeted test files
- Recommended Forge Gates
- Live checks suggested by the affected systems

Outputs:

- `.forge/graph/impact-report.json`
- `.forge/graph/impact-report.md`

The default dependency depth is two and is configurable through `graph.impact_depth`.
