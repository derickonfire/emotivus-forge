# Exact-Package Release Authorization

Forge 0.528 adds a separate project-declared release authorization beneath the bounded `release-ready` claim. It is never inferred from project-tree authority, Check, signatures, remote availability, Release Proof, cold-session results, or roadmap percentages.

## Recording authority

The authorization must be a project-owned schema-1 JSON file outside `.forge/` and outside the Forge distribution. Record it in a separate Adopt operation:

```text
forge adopt . --record-release-authorization forge-release-authorization.json
```

The contract binds:

- one active `release_package_id`;
- exact package SHA-256 and byte length;
- current owner-declared build ID;
- the decision `authorize-public-release`;
- project-declared authority and authority source;
- authorization and expiration timestamps;
- named release channels;
- rationale, conditions, and a bounded truth statement.

Only one active authorization may exist. Source-file changes, package changes, build changes, expiration, retirement, or package-record invalidation remove the claim.

## Claim ladder

`owner-release-authorized` follows `cold-session-validated`. `release-ready` can pass only when every earlier cumulative level is current and this exact-package authorization also passes.

A bounded `release-ready` PASS means the project’s declared requirements are current and its declared authority authorized the exact package for the named channels. It does **not** authenticate the human, prove authorship or reviewer competence, establish universal correctness, satisfy undeclared legal or organizational approvals, or guarantee future package or channel state.
