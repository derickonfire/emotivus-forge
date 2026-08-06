# Proxy-observation audit — Forge 0.543

Status: **COMPLETE — no additional false blocker found.**

Origin: the 0.542 cross-version doctor defect observed PATH `python3` and treated it as the
project's active interpreter even when Forge itself was running under a different, correctly
pinned interpreter. This audit asks where Forge observes an indirect proxy and might describe
it as the underlying subject.

## Method

The audit reviewed every active-core use of:

- executable discovery and subprocess execution;
- inherited environment values;
- file and directory existence;
- project-owned declarations and receipts;
- remote release retrieval;
- generated package facts;
- model/session context supplied to the optional Run Forge adapter.

Search scope: `emotivus_forge/**/*.py`, excluding the frozen capability vault. The review was
bounded to observation identity and claim wording; it was not a general security or correctness
audit.

## Results

| Observation | Actual subject | Classification | Result |
|---|---|---|---|
| `sys.executable --version` | The interpreter executing Forge | Direct runtime observation | Correct after 0.542 correction. |
| `shutil.which("python3")` | PATH-resolved alternate Python candidate | Proxy, explicitly secondary | Correct: it cannot override a matching running interpreter. |
| PATH Node/PHP lookup | The executable the current Forge process environment would launch | Environment-bound candidate | Correctly limited to doctor diagnosis; it does not claim production runtime identity. |
| Native gate command | Exact declared command executed with the recorded environment | Direct bounded execution | Correct; PASS remains scoped to parsed native evidence. |
| `os.environ` inheritance | Current Forge process environment | Direct local process context | Correct; it is never described as deployment or production configuration. |
| Project-owned JSON/Markdown | Exact local file bytes | Direct byte observation plus declared meaning | Correct; authority and identity remain declared, not authenticated. |
| Filesystem existence | Exact observed path at check time | Direct local observation | Correct; future presence and semantic correctness remain excluded. |
| Remote release URL | Retrieved response bytes from an authority-bounded HTTPS origin | Direct retrieval through network infrastructure | Correctly excludes future availability, CDN authorship, and signer custody. |
| ZIP manifest/version | Exact member bytes inside the observed archive | Direct package observation | Strengthened in 0.543 with same-name/version collision detection. |
| Session-context adapter | Caller-supplied distilled context | Declared transient input | Correctly rejected when raw transcript/message arrays are supplied and never treated as provider-authenticated truth. |
| Build attestation | Signature over exact external build-manifest bytes | Cryptographic key-control evidence | Correctly excludes human identity, source causality, and release authorization. |

## Corrections made by this cycle

The audit relies on and confirms three corrections already implemented in the 0.543 workstream:

1. workspace seal candidates now bind exact content rather than timestamps;
2. observed artifact identities now use exact ZIP bytes rather than version labels alone;
3. build attestation says only that the holder of an external key signed exact manifest bytes.

No new proxy-based blocker requiring a code correction was found. PATH observations remain
explicitly environment-bound candidates; they are not promoted to production-runtime facts.

## Truth boundary

This audit establishes that the reviewed active-core observation sites distinguish direct local
facts, environment-bound candidates, project declarations, and cryptographic evidence in their
current code and wording. It does not prove that every future integration preserves that
boundary, that external declarations are true, or that Forge is free of unrelated defects.
