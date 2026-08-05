# Forge Web Documentation

Forge maintains a generated public website at `https://forge.emotivus.com`.

## Purpose

The site provides:

- clear product positioning;
- the exact “Run Forge” first-target workflow;
- the five public commands;
- Project Passport documentation;
- development status and limitations;
- roadmap and changelog;
- trust, privacy, and neutrality boundaries;
- current public download, release notes, and checksums.

## Canonical data

`FORGE-PRODUCT.json` controls the site’s public facts. `docs-site/build_site.py` renders the static pages and supporting files.

## Required release behavior

Every development release must rebuild the website and verify:

- version consistency;
- `forge.emotivus.com` canonical URLs;
- Help, Adopt, Resume, Check, and Ship as the public interface;
- “Run Forge.” as the canonical first instruction;
- accurate limitations and roadmap status;
- correct download and checksum references;
- no private or customer project information;
- accessible responsive navigation and readable mobile layout.

## Public deployment

The standalone website export is intended for the document root of `forge.emotivus.com`. The full development source must not be placed in the public web root.
