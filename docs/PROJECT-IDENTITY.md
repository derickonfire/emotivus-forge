# Owner-Controlled Project Identity

Forge can record one project-owned identity document for systems whose server, web surface, mobile player, schema, or contracts move on different release clocks.

Forge **does not choose or increment project versions**. The project authority owns every identity value. Forge validates the shape, fingerprints the source, preserves prior monotonic values, and requires renewed authority when the source changes.

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --record-identity forge-project-identity.json
```

See `examples/project-identity.example.json`.

## Identity model

A schema-1 document contains:

- a stable `identity_id`;
- the declaring authority;
- an immutable project `build_id`;
- an optional release train;
- independently versioned components;
- component contract versions;
- optional monotonic platform identifiers;
- a declared baseline;
- an optional literal-copy policy;
- an explicit truth boundary.

An absent component uses `version: null`. Forge rejects placeholder values such as `0.0.0` for something that does not yet exist.

## Monotonic protection

Values such as an Android `versionCode` may never decrease after Forge records them. A lower replacement is blocked before the new identity is accepted. This protects only the recorded integer relationship; it does not prove that an application package was built or installed.

## Single-source literal scan

A project may opt into exact-literal scanning by declaring `literal_policy.scan_paths`. Forge then warns when the build ID or a present component version is copied into those paths instead of being derived from the canonical identity. Intentional history or compatibility copies belong in `exception_paths`.

The scan is exact-string, path-bounded, and file-limited. It does not prove every consumer derives identity correctly.

## Resume and token conservation

The full identity stays in `.forge/settings.json` and the Ledger. Compact Resume reports only:

- identity status;
- build ID;
- present component count.

Detailed component, contract, baseline, and monotonic values are loaded only when requested or relevant.
