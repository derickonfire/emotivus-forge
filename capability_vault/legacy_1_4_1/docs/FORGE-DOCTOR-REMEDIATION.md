# Forge Doctor Remediation

Forge Doctor continues to measure the machine and workspace without modifying either by default. v1.0.6 adds reviewed, reversible repair proposals for narrow filesystem conditions declared by the project.

Supported automated repair types:

- Create a declared directory.
- Create a declared file from explicit project-supplied content.
- Append explicit missing lines to a declared file.

Forge Doctor will not install runtimes, create credentials, change services, provision databases, or infer secret values.

```bash
python3 Emotivus-Forge/forge.py doctor . --action propose
python3 Emotivus-Forge/forge.py doctor . --action apply --id <proposal-id> --confirm
python3 Emotivus-Forge/forge.py doctor . --action rollback --transaction <transaction-id>
```

Every applied repair receives a transaction record and backup sufficient for rollback.
