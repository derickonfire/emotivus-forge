# Artifact Provenance and the Delivery Perimeter

Forge separates two questions:

1. **Evidence:** what check ran, against which project state and environment, and what it reported.
2. **Provenance:** whether the artifact currently present still matches the exact output, inputs, generator source, and baseline recorded by project authority.

They are never interchangeable.

## Record provenance

Create a project-owned schema-1 contract and record it through Adopt:

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --record-artifact-provenance forge-artifact-provenance.json
```

The contract declares:

- a stable provenance ID and authority;
- the artifact path;
- the declared generator command and optional generator-source paths;
- exact input paths or bounded glob patterns;
- an optional owner-declared baseline build ID;
- whether the artifact is a deliverable;
- the explicit truth boundary.

Forge records SHA-256 digests for the artifact, expanded input manifest, generator source, and current baseline observation. It does **not** execute the generator command.

## Check behavior

Every scoped Check re-evaluates active records. It blocks when:

- the artifact is missing or its bytes changed;
- any declared input changed;
- generator source changed;
- the owner-declared baseline no longer matches;
- the contract changed or disappeared after authority approval.

Deliverable-shaped files such as ZIP, TAR, wheel, JAR, APK, or AAB files without a current record produce a warning:

> **Forge —** Found 1 deliverable-shaped artifact outside registered provenance; delivery assurance is unavailable.

The warning does not pretend the artifact is defective. It states that Forge has no registered lineage for it.

## Retirement

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --retire-artifact-provenance product-package \
  --artifact-provenance-reason "The package is no longer distributed."
```

Retirement preserves the Ledger history and stops the provenance obligation. A remaining artifact may then appear as an unregistered perimeter warning.

## Token boundary

Exact file manifests and hashes remain in local structured state. Compact Resume output reports only active, attention, retired, and unregistered counts.

## Truth boundary

Current provenance proves only that current bytes still match the authority-recorded relationship. It does not prove:

- that the declared generator command actually ran;
- that the artifact functions correctly;
- that it was delivered or deployed;
- that a release is ready;
- or that Ship may proceed.
