# External Evidence Return and Review

Forge 0.549 adds a bounded intake boundary for evidence produced by the portable owner-attestation
and evidence kits. It does not make the operator, reviewer, provider report, or administrative
independence trustworthy merely because a ZIP can be verified.

## Workflow

1. Execute an exact sealed 0.549 kit on the other machine or under the other operator.
2. Package only the workflow allowlist:

```bash
# Owner-attestation kit
python3 run-attestation.py package-return \
  --ceremony-dir /path/to/ceremony \
  --kit-archive /path/to/Emotivus-Forge-0.549-Attestation-Kit.zip \
  --output owner-attestation-return.zip

# Portable evidence kit: writer trial
python3 run-evidence.py package-writer-return \
  --workspace /path/to/writer-workspace \
  --kit-archive /path/to/Emotivus-Forge-0.549-Evidence-Kit.zip \
  --output writer-return.zip

# Portable evidence kit: matched handoff
python3 run-evidence.py package-benchmark-return \
  --packet-dir /path/to/benchmark-packet \
  --kit-archive /path/to/Emotivus-Forge-0.549-Evidence-Kit.zip \
  --output matched-handoff-return.zip
```

3. Review the returned ZIP from the Forge source tree against the exact original kit:

```bash
python3 tools/review_external_evidence.py review \
  --kit /path/to/original-kit.zip \
  --return-bundle /path/to/returned-evidence.zip \
  --reviewer "named technical reviewer assertion" \
  --output review-receipt.json
```

4. Supply prior review receipts when duplicate or conflicting submissions must be classified:

```bash
python3 tools/review_external_evidence.py review \
  --kit /path/to/original-kit.zip \
  --return-bundle /path/to/returned-evidence.zip \
  --reviewer "named technical reviewer assertion" \
  --prior-review prior-review.json \
  --output next-review.json
```

5. Recheck the content identity and truth flags of a saved review receipt:

```bash
python3 tools/review_external_evidence.py verify-review --review review-receipt.json
```

Receipt verification proves only that the receipt has not changed. A later reviewer who needs the
underlying technical conclusion must retain and review the original sealed kit and return bundle.

## Archive boundary

A return bundle must have one root, fixed ZIP timestamps, no duplicate names, unsafe paths, symbolic
links, encrypted members, oversized content, undeclared payloads, or private-key material. Each
workflow has an exact payload allowlist. The return manifest binds every payload by SHA-256 and byte
length and binds the exact original kit by SHA-256, byte length, member count, kit ID, Forge version,
and schema.

The reviewer independently recomputes the workflow result:

- owner attestation: exact package/build-manifest binding and detached RSA signature;
- writer trial: before/after bytes, challenge, runtime, raw Ship result, `DRIFTED`, and false
  `release_ready`;
- matched handoff: immutable task, admissible arm records, isolated workspaces, and the exact paired
  comparison.

## Duplicate lifecycle

- `FIRST_SEEN`: no valid prior receipt has the same subject or exact submission.
- `DUPLICATE_EXACT`: a valid prior receipt binds the same exact submission.
- `CONFLICTING_SUBMISSION`: a valid prior receipt binds the same subject but different returned bytes.

These labels do not retire, approve, or authorize anything. Invalid prior receipts are surfaced as
review problems rather than silently ignored.

## Truth boundary

A passing review verifies exact files and bounded workflow semantics. It does not authenticate a
human, prove private-key custody, authenticate administrative independence, authenticate provider
billing records, generalize a benchmark sample, authorize a release, or establish release readiness.
Every review receipt preserves:

- `reviewer_identity_authenticated: false`
- `owner_identity_authenticated: false`
- `independent_evidence_claimed: false`
- `release_authorized: false`
- `release_ready: false`
- `private_key_retained: false`
