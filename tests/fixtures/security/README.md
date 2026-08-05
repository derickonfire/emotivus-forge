# Synthetic secret-detection fixtures

Every file in this directory is **synthetic**. No value here is live, was ever live, or
belongs to any real account, project, or person. The strings exist so Forge's screening
rules can be regression-tested against known shapes.

This directory is declared in `CONFIDENTIALITY-POLICY.json` under `synthetic_fixture_paths`.
Findings raised here are downgraded to INFORMATIONAL and carry `downgraded_from` so the
downgrade is visible in the record rather than silent.
