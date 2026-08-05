# Tiered Confidentiality and Secret Screening

Forge classifies every confidentiality finding into exactly one level.

| Level | Meaning | Effect on a distribution build |
|---|---|---|
| `BLOCK` | Material that must never leave a private boundary. | Build stops. |
| `REVIEW` | Secret-shaped but not proven live. A human decides. | Build continues; finding is printed and recorded. `--fail-on-review` makes it blocking. |
| `INFORMATIONAL` | Placeholders, templates, declared synthetic detector fixtures. | Recorded only, so a reader can see the scanner examined them rather than missed them. |

## Two absolute rules

1. **Forge never records a matched secret value.** Findings carry a path, a rule identity, and a redaction-safe descriptor. Every finding asserts `value_retained: false`.
2. **Forge never edits a file to remove a finding.** Screening reports; it does not redact. Certified package and evidence bytes are immutable. A finding against a sealed build is corrected in a *new* build, never by mutating the old one.

## Declared synthetic fixtures

Paths listed under `synthetic_fixture_paths` cannot produce BLOCK or REVIEW. Their findings are downgraded to INFORMATIONAL and carry `downgraded_from` plus a reason, so the downgrade is visible in the record rather than silent. This is how Forge holds a detector corpus without blocking its own build.

## Policy schema

The packaged `CONFIDENTIALITY-POLICY.json` is schema 2 and ships with **empty denylists by design**. Private project terms are supplied externally:

    FORGE_PRIVATE_POLICY=/path/to/private-policy.json \
      python3 tools/build_forge_package.py . --edition public --output deploy/RUN-FORGE.zip

Schema 1 policies remain accepted. Their single `forbidden_terms` list is treated as BLOCK.

## Precision

Screening that fires on ordinary code gets ignored, and an ignored screen is worse than no screen. Two rules keep the signal usable:

- A credential name must end in an exact segment such as `api_key`, `client_secret`, or `token`. Plurals are excluded, because `provider_input_tokens` is a usage count. Bare `key` is excluded, because `key = ...` is overwhelmingly a dict key.
- A value must be structurally capable of being a credential: not a type annotation, literal, dotted reference, call, or plain lowercase identifier, at least eight characters, and at least 2.5 bits per character of entropy.

A regression asserts the entire `emotivus_forge` source tree screens clean at BLOCK and REVIEW under the packaged policy.

## Truth boundary

A PASS means no configured rule matched. It does **not** prove a distribution is free of private information, and no finding proves a matched value is live. Shape-based screening catches shapes it was given. It cannot catch a private identifier nobody thought to name.
## Provenance-gated YesMem pattern adaptation

Forge adapts selected high-confidence secret shapes and neutral regression vectors from YesMem 2.3.5 under Apache-2.0 through an exact Third-Party Capability Intake. The public implementation recognizes provider API keys, GitHub access tokens, AWS key forms, JWTs, bearer tokens, inline URL credentials, and private-key block headers. Forge changes the upstream redaction model into report-only tiered findings: matched values are never retained and scanned bytes are never edited.

Forge deliberately does **not** enable upstream email, phone, public-IPv4, or arbitrary 32–128 character hexadecimal patterns by default. Those forms are common in public contact data, documentation, and exact SHA-256 evidence; default matching would create disproportionate false positives. Projects may still declare private terms and path rules through an external private policy.

See `THIRD-PARTY-NOTICES.md` and `THIRD-PARTY-LICENSES/YesMem-Apache-2.0.txt`.
