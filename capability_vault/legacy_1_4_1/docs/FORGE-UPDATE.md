# Forge Update

Forge Update upgrades an installed `Emotivus-Forge/` directory without merging Forge into the host application.

## Safety sequence

1. Inspect and hash the incoming Forge distribution.
2. Preview added, modified, removed, and preserved paths.
3. Back up the current Forge installation and project configuration.
4. Stage the incoming release outside the active installation.
5. Preserve configured private extension paths, such as `policy-packs/`.
6. Swap the installation.
7. Migrate the project configuration with a recorded backup.
8. Run the incoming bootstrap validator, self-tests, Doctor, and the configured post-update Gate.
9. Automatically restore the previous installation and configuration when any required check fails.

## Commands

```bash
python3 Emotivus-Forge/forge.py update . \
  --action preview \
  --source Emotivus-Forge-New.zip

python3 Emotivus-Forge/forge.py update . \
  --action apply \
  --source Emotivus-Forge-New.zip

python3 Emotivus-Forge/forge.py update . \
  --action rollback \
  --transaction <transaction-id>
```

Update backups and transaction evidence live under `.forge/update/`. Binary backups are excluded from portable Forge State.
