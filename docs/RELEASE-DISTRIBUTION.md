# Signed and Remotely Verified Release Distribution

Forge 0.525 verifies detached RSA PKCS#1 v1.5 SHA-256 signatures for the exact final package and its release-channel manifest, then may freshly verify required remote artifact bytes during explicit Ship.

```bash
forge adopt . --record-release-distribution forge-release-distribution.json
forge ship .
```

Forge requires project-owned public keys and detached base64 signatures. Private signing keys remain external and are never requested, read, or stored.

A signed channel manifest binds:

- release package ID;
- owner-controlled build ID;
- exact package digest;
- detached artifact-signature digest;
- declared release-channel URI and digest.

Project-owned publication receipts must first agree with the signed manifest and exact package. An optional `remote_verification` contract then authorizes Ship-only retrieval:

```json
{
  "schema": 1,
  "allowed_origins": ["https://downloads.example.com"],
  "timeout_seconds": 20,
  "max_artifact_bytes": 250000000,
  "truth_boundary": "A passing result proves only that a fresh bounded HTTPS GET returned exact package bytes at assessment time; it does not prove future availability or release readiness."
}
```

Remote verification is credential-free, HTTPS-only, origin-bound, redirect-constrained, and budgeted. Forge streams the artifact, compares exact byte length and SHA-256, and retains no response body.

A PASS does not prove future availability, continuous CDN integrity, signer custody, or release readiness.
