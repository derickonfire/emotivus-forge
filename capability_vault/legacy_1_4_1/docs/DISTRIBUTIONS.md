# Forge Distribution Editions

Forge development and public editions must be generated from the same certified source.

## Development edition

Contains Forge Core, complete tests, Mirror contracts, internal roadmap, implementation report, certification requirements, internal-use notice, public documentation source, and release evidence.

```bash
python3 tools/build_forge_package.py . --edition development --output deploy/Emotivus-Forge-Development.zip
```

## Public edition

Contains the neutral runtime, adapters, self-tests, Mirror contracts, examples, public human documentation, and AI bootstrap guidance. It excludes internal reports, internal roadmap material, and the internal-use license.

```bash
python3 tools/build_forge_package.py . --edition public --output deploy/Emotivus-Forge.zip
```

The current public edition remains a technical preview until the owner selects and approves the public software license. Packaging does not make that legal decision.

Both editions must pass independent bootstrap validation. Forge Mirror must build and retest the public edition before release.

## Project handoffs

Forge distributions are not the same as a host project's owner-facing handoff. Host projects use `prove deliver --profile handoff` to register every artifact, execute generators under Forge observation, fingerprint inputs and outputs, build the exact outer bundle, and rerun the Release Gate against that completed delivery.
