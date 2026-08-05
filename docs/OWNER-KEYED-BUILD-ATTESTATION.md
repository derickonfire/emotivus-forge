# Portable Owner-Keyed Build Attestation

Forge 0.549 retains the portable ceremony for one exact Forge ZIP, its exact schema-2 build manifest, a standalone verifier,
public-key and detached-signature templates, and fixed instructions into a deterministic ceremony kit.
The kit contains no private key and cannot sign anything.

## Build the kit

First build the package and schema-2 build manifest, then bind both exact files:

```text
python3 tools/build_attestation_kit.py build \
  --root . \
  --package deploy/RUN-FORGE-0.549.zip \
  --build-manifest deploy/RUN-FORGE-0.549.build.json \
  --output deploy/Emotivus-Forge-0.549-Attestation-Kit.zip
```

Verification checks archive hygiene, deterministic timestamps, every payload digest and byte length,
package version and edition, package member count, schema-2 build-manifest identity, and the exact
packaged `FORGE-MANIFEST.json` digest.

## Prepare with public material only

After extraction:

```text
python run-attestation.py verify
python run-attestation.py prepare \
  --public-key owner-public-key.json \
  --output-dir ceremony
```

Preparation precommits the exact public-key bytes, key ID, canonical fingerprint, package digest,
build-manifest digest, kit identity, and a stable ceremony ID. It writes no signature and reports
`AWAITING_SIGNATURE`.

## Sign outside Forge

The owner or controller signs the exact build-manifest bytes using RSA PKCS#1 v1.5 with SHA-256.
Forge accepts only the public key and returned base64 detached signature. The private key must never
be copied into the kit, project, Forge state, or delivery archive.

## Finalize and reverify

```text
python run-attestation.py finalize \
  --ceremony-dir ceremony \
  --signature returned-signature.b64

python run-attestation.py verify-receipt \
  --ceremony-dir ceremony
```

Finalization refuses a changed public key, changed kit, changed package or manifest, wrong or replayed
signature, incomplete input, or receipt drift. A stable receipt binds all exact identities and retains:

- `private_key_retained: false`;
- `owner_identity_authenticated: false`;
- `release_authorized: false`.

## Truth boundary

A cryptographic PASS proves that the supplied public key verifies a detached signature over the exact
precommitted build-manifest bytes. Forge does not authenticate the human controller of the key,
prove private-key custody, prove source reproducibility, authorize release, or claim release readiness.
The delivered 0.549 kit remains `NOT_RUN` until an external signature is actually supplied.

## Returning a completed ceremony for source-owned review

Forge 0.549 adds `package-return` to the standalone ceremony runner. The command creates a
deterministic allowlisted archive containing only the request, public key, detached signature, and
attestation receipt, bound to the exact original kit. The source-owned reviewer then reopens the
original kit, re-verifies its exact package and build manifest, and independently verifies the
signature before emitting a bounded review receipt. See `docs/EXTERNAL-EVIDENCE-REVIEW.md`.

New ceremonies use the same newline-free canonical public-key fingerprint as Forge core. The reviewer
also recognizes the prior 0.546 portable newline profile solely to preserve verification compatibility
for already sealed material; it does not change the normalized fingerprint emitted by 0.549.
