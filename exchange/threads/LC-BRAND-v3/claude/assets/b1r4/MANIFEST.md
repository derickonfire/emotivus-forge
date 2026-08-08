# LC-BRAND-v3 B1 r3 — E2 Refresh containment proof (codex/0010)

Head `675252d584224a0330ecf5d68e469058186b29e8` (supersedes cce8299). Phone clock is now clean centred text (no box); the box is tablet-only.

## Full containment assertion (shoot_e2_contain.js, codex/0010 §5) — ALL 8 OK
Per frame: title/clock/Refresh each non-zero visible geometry; Refresh display/visibility/opacity active and box ≥48×48; all three fully inside the viewport AND the topbar; title & Refresh outer insets ≥12px; no pair intersects. Root font-size measured to confirm 125%.

| Frame | rootFs | Refresh | insetL | insetR | in viewport | in topbar | no intersect |
|---|---|---|---|---|---|---|---|
| e2_320x844 (dark/light) | 16px | 48×48 visible | 28 | 28 | yes | yes | yes |
| e2_320x844 @125% (dark/light) | 20px | 48×48 visible | 28 | 28 | yes | yes | yes |
| e2_390x844 (dark/light) | 16px | 48×48 visible | 28 | 28 | yes | yes | yes |
| e2_390x844 @125% (dark/light) | 20px | 48×48 visible | 28 | 28 | yes | yes | yes |

## E1 / E4 unchanged
Diff vs cce8299 is `style.css .topbar-has-refresh` only (+12/-7). Home (E1/E4) renders are byte-identical; accepted evidence + hashes stand at `../b1r2/`.

## Verification
- Full battery **81 PASS / 0 FAIL / 0 SKIP**; MANIFEST-SHA256.txt refreshed in-commit; web-doc.zip and tools unchanged.

## Frame hashes (sha256)
```
1fa2e96a91fcf4c5d90dfaf693578a5c52873f935ca69a3b03e17fe6b0c68bdd  e2_320x844_dark.png
20b8129fe959e01edb2949dc5c127482211f68c835958d21d5094b7aa50ff84a  e2_390x844_light_125.png
20d9454ebe29eb648c7363be760b2346792d26ee66c3990b12f14b32c217e1e4  e2_390x844_dark_125.png
30711093a12ba3db371c54700e9ef25adf709430c89ba532e830d13c4d18be54  e2_390x844_light.png
722ea8c434be020a5672930352b183bc8b98bfc8f94884d7b0fafd19a69c0d08  e2_320x844_light_125.png
bed935791cdc072fa6404060005f1e42cbbc07b2aa11b3db0e6207b67a6989e1  e2_320x844_light.png
c80bf2e41f7fdb658b0631bda72af27e781c53cd3b4aa09f36ee9e2a08008241  e2_320x844_dark_125.png
dffbe53ff50cd4e4ba15a5504f00c02b179d6460cacee22adf4223b914fddff5  e2_390x844_dark.png
```
