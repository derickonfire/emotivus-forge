# Third-Party Notices

## YesMem 2.3.5

Selected secret-detection patterns and neutral regression vectors in `emotivus_forge/core/secret_screening.py` and `tests/test_secret_screening.py` are adapted from YesMem 2.3.5, copyright Papoo Software & Media GmbH, under the Apache License 2.0.

Forge modifies the upstream behavior substantially: Forge reports redaction-safe BLOCK, REVIEW, and INFORMATIONAL findings; retains no matched values; never edits scanned bytes; treats synthetic fixtures and placeholders explicitly; and does not include upstream email, phone, public-IPv4, or arbitrary long-hex defaults.

The exact reviewed upstream archive and source-member identities are governed by the development-only Third-Party Capability Intake contract. The YesMem runtime, daemon, proxy, database, sessions, agents, scheduler, binaries, and complete source archive are not included in Forge distributions.

License text: `THIRD-PARTY-LICENSES/YesMem-Apache-2.0.txt`.
