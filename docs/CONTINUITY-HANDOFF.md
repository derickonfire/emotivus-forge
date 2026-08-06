# Portable Forge Continuity Handoff

Forge state is development continuity, not deployable application code. A portable handoff therefore travels as a separate private companion ZIP.

## Export

A completed Session Close is required:

```bash
forge check . \
  --checkpoint \
  --close-session \
  --summary "Completed the current increment." \
  --next-action "Continue the next approved increment." \
  --export-continuity Forge-State.zip \
  --development-package Project-Development.zip
```

The bundle contains:

- all eight top-level Forge state files;
- bounded structured `result.json` evidence manifests;
- an integrity manifest;
- the digest of the optional development package.

It excludes raw stdout/stderr logs, response bodies, credentials, project source, and deployable application files.

## Import

Import only into a project that has no existing Forge state:

```bash
forge adopt . \
  --import-continuity Forge-State.zip \
  --continuity-development-package Project-Development.zip
```

Forge verifies every bundled digest and, when the handoff is package-bound, verifies the supplied development-package digest before restoring state. It refuses to overwrite an existing continuity record.

## Privacy and delivery boundary

The bundle is project-private. It may contain decisions, risks, objectives, and evidence metadata. Review it before sharing.

The separate bundle is intentionally not a deployable package. Its integrity proves only that the restored continuity bytes match the export manifest; it does not prove the project code, package, evidence, or release is correct.
## Roadmap status

Portable development handoff is approximately **90% complete**. Export, integrity binding, package binding, and import are implemented; repeated cold-agent field validation remains.

