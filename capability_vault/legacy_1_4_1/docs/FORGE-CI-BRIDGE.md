# Forge CI Bridge

CI Bridge generates minimal integration that calls Forge Gates. It does not replace the host project's tests, linters, deployment scripts, or CI knowledge.

Supported providers:

- GitHub Actions
- GitLab CI include file
- Generic POSIX shell
- cPanel-oriented release shell

Preview before writing:

```bash
python3 Emotivus-Forge/forge.py ci . --provider github --action preview
python3 Emotivus-Forge/forge.py ci . --provider github --action write
```

Existing targets are never replaced without `--force`; a backup is written first. Generated CI files are excluded from public deployment packages by default.
