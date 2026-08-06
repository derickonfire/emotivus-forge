# Forge Website Release Operations

The website is a first-class Forge release artifact.

## Canonical source

`FORGE-PRODUCT.json` is the source of truth for:

- version and release state;
- public commands;
- product positioning;
- limitations;
- roadmap;
- website domain and navigation;
- brand palette and identity meaning;
- current release highlights.

## Required build

```bash
python3 docs-site/build_site.py
```

For a standalone deployable website with the current public package:

```bash
python3 docs-site/build_site.py \
  --download /path/to/RUN-FORGE.zip \
  --release-notes /path/to/RELEASE-NOTES.md \
  --checksums /path/to/SHA256SUMS.txt
```

## Release gate

A Forge release is incomplete when the generated site contains:

- an old version;
- an old command model;
- stale roadmap status;
- outdated limitations;
- missing trust boundaries;
- a missing or mismatched download;
- an incorrect canonical domain.

## Deployment target

Upload the generated `docs-site/` contents to the document root for `forge.emotivus.com`. Preserve the directory structure and verify:

- `/`
- `/run/`
- `/docs/`
- `/roadmap/`
- `/trust/`
- `/changelog/`
- `/downloads/RUN-FORGE.zip`
- `/robots.txt`
- `/sitemap.xml`
