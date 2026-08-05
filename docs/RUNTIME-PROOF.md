# Content-Aware Runtime Proof

Forge Runtime Proof is a **contract-gated, clean-room HTTP capability**. It exists to answer a narrow question:

> Did this declared HTTP surface return the minimum expected content, rather than merely returning a status code?

It is inactive by default and loads only when all of the following are true:

1. the project owns an activation contract;
2. the contract names exact allowed origins and bounded recipe files;
3. the required focused regressions are declared;
4. the owner explicitly activates `runtime-proof` through Adopt;
5. Check explicitly requests `--run-capability runtime-proof`.

## Supported assertions

Each recipe must declare:

- expected HTTP status values;
- accepted content types;
- a minimum response size;
- at least one required content marker;
- forbidden error or placeholder markers;
- an exact response byte limit;
- an exact timeout;
- the verification tier and exclusions.

A `200` response by itself is structurally insufficient. A 32-byte error page, missing application marker, fatal-error string, unexpected content type, oversized response, timeout, cross-origin redirect, or disallowed origin blocks the recipe.

## Security and authority boundary

The active implementation:

- supports GET only;
- requires exact allowed origins;
- rejects credentials in URLs;
- rejects authorization, cookie, API-key, and arbitrary request headers;
- follows redirects only inside the allowed origin set;
- stores no response body;
- records only status, final URL, content type, byte count, response digest, assertion results, timing, and truth state;
- performs no repair or configuration mutation.

## What it does not prove

Runtime Proof does not execute JavaScript, inspect layout, take screenshots, authenticate, exercise browser storage, verify database state, prove migrations, establish deployment completeness, or certify release readiness. A recipe may be labeled `sandbox`, `staging`, or `production` only because project authority declared the target; the tier does not imply other checks ran.

## Example

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --activate-capability runtime-proof \
  --capability-contract forge-runtime-proof-contract.json

python3 Emotivus-Forge/forge.py check . \
  --run-capability runtime-proof
```

See:

- `examples/runtime-proof-activation.example.json`
- `examples/runtime-proof-recipe.example.json`

## Runtime-state integration

A Runtime Proof recipe may support an authority-recorded runtime-state scenario only when it runs in the same Check and its verification tier is at least the scenario tier. See `RUNTIME-STATE-MATRIX.md`. This binding does not turn HTTP evidence into deployment or database proof.
