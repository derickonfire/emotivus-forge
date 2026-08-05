# Portable Forge State

Projects exchanged as ZIP files need Forge's project memory to travel between sessions. `Forge-State.zip` carries assurance state separately from the public deployment package.

## Export

```bash
python3 Emotivus-Forge/forge.py state . --action export --output Forge-State.zip
```

The archive contains the Forge project contract, agent contract, Graph evidence, learned contracts and proposals, baselines, setup decisions, tool inventory, reports, Doctor evidence, and Brief evidence. Forge excludes quarantined legacy tools, Lab workspaces, state backups, and secret-like material.

## Inspect

```bash
python3 Emotivus-Forge/forge.py state . --action inspect --input Forge-State.zip
```

Forge verifies the manifest, declared members, safe paths, and SHA-256 hashes.

## Adopt

```bash
python3 Emotivus-Forge/forge.py state . --action adopt --input Forge-State.zip
```

Existing state is backed up before adoption. A project-name mismatch blocks adoption unless `--force` is used after deliberate review.

`Forge-State.zip` is an internal continuity artifact. Forge adds it to deployment exclusions automatically.
