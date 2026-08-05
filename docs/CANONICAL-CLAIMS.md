# Canonical Claims

Forge can record explicit, project-owned claims from owner-facing truth documents and re-evaluate them during Scoped Check.

## Why this exists

A package can be internally coherent while its installation guide, status truth, evidence folder, or release notes describe a different build. Forge does not attempt unrestricted natural-language interpretation. The project authority declares which statements matter and how each can be checked deterministically.

## Supported claim kinds

- `identity-text` — a source must contain an exact template resolved from the current owner-declared identity.
- `evidence-identity` — an evidence file must identify the current build or component field.
- `archive-membership` — a registered provenance ZIP must contain or exclude a declared member.
- `migration-effects` — a declared migration must contain or omit DDL or DML after bounded comment removal.

Each claim also carries exact `claim_text`. Forge first confirms that the declared statement is still present in the canonical source, then evaluates the linked evidence.

## Commands

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --record-canonical-claims forge-canonical-claims.json

python3 Emotivus-Forge/forge.py adopt . \
  --retire-canonical-claims release-truth \
  --canonical-claims-reason "These release documents were retired."
```

## Truth boundary

Canonical claims are explicit assertions, not general prose understanding. A passing set proves only that the declared statements agree with the current deterministic evidence supported by the claim kinds. It does not prove overall documentation completeness, migration safety, deployment state, or release readiness.
