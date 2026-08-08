# LC-BRAND-v3 Phase B1 — render evidence

Official mode-matched LineCheck wordmark on Home/Dashboard (E1/E4, $active==='today').

- **Branch:** `ai/claude/LC-BRAND-v3-B1`  **Head:** `e6938efb2fc6fd8c28ed8f5f1bdcd7d6e576688e`  **Base:** post-Phase-A main `69c1914d98dcbc877cc174fc947c6ccb7b6f3985`
- **Rig:** authenticated staff (E1) + manager (E4) renders from a real DB fixture; 390×844 portrait, deviceScaleFactor 2, BOTH themes; plus 320 min-width, 800×1280 tablet portrait, and 125% large-text frames. Signed-in actors; seeded operational day 2026-08-08.
- **Automated frame assertions (shoot_b1.js): ALL 18 OK.**

## Positive — wordmark present (Home/Dashboard)
One mode-matched official mark shown per theme (dark→linecheck-dark.svg, light→linecheck-light.svg), loaded (naturalWidth>0), single accessible name "LineCheck" (role=img), overflow-free.
**Width cap correction (codex/0002):** phone mark renders **116px** wide — inside the ~120px cap (the reverted B1 used 132px); tablet 149px. Aspect preserved (height-driven, width auto).

| Frame | Actor | Viewport | Theme | Note |
|---|---|---|---|---|
| e1_390x844_dark.png | Staff | 390×844 | dark | wordmark 116px |
| e1_390x844_light.png | Staff | 390×844 | light | wordmark 116px |
| e1_320x844_dark.png | Staff | 320×844 | dark | narrow phone |
| e1_320x844_light.png | Staff | 320×844 | light | narrow phone |
| e1_390x844_dark_125.png | Staff | 390×844 @125% | dark | large text |
| e1_390x844_light_125.png | Staff | 390×844 @125% | light | large text |
| e1_800x1280_dark.png | Staff | 800×1280 | dark | tablet, 149px |
| e1_800x1280_light.png | Staff | 800×1280 | light | tablet, 149px |
| e4_390x844_dark.png | Manager | 390×844 | dark | wordmark 116px |
| e4_390x844_light.png | Manager | 390×844 | light | wordmark 116px |
| e4_320x844_dark.png | Manager | 320×844 | dark | narrow phone |
| e4_320x844_light.png | Manager | 320×844 | light | narrow phone |
| e4_390x844_dark_125.png | Manager | 390×844 @125% | dark | large text |
| e4_390x844_light_125.png | Manager | 390×844 @125% | light | large text |
| e4_800x1280_dark.png | Manager | 800×1280 | dark | tablet, 149px |
| e4_800x1280_light.png | Manager | 800×1280 | light | tablet, 149px |

## Negative / gating — wordmark absent (non-'today' surfaces)
Routine (E2) and Tasks (E3) are not $active==='today'; the wordmark must not appear. Confirmed absent, overflow-free, both themes.

| Frame | Surface | Theme |
|---|---|---|
| e2_390x844_dark_NEG.png | Routine | dark |
| e2_390x844_light_NEG.png | Routine | light |
| e3_390x844_dark_NEG.png | Tasks | dark |
| e3_390x844_light_NEG.png | Tasks | light |

## Offline / static-shell proof (codex/0002: not merely same-origin)

The two served wordmark SVGs join the service-worker **precache static shell**
(`site/service-worker.js` `STATIC_PATHS`), cached on install via
`cache.addAll(Array.from(STATIC_PATHS, scopeUrl))` and served **cache-first**
(`caches.match(request, {ignoreSearch:true})`), exactly like `assets/style.css`
and the app icons. So the official mark is part of the installable cached shell
and renders from cache without a per-asset network round-trip — it does not
depend on a live fetch the way a plain same-origin URL does. (Authenticated
navigations remain network-first by design and fall back to the private-data-free
`offline.html`; the claim here is asset-level cache residency, not that Home
renders fully offline.) The precache entries:

```js
19:  'assets/brand/linecheck-light.svg',
20:  'assets/brand/linecheck-dark.svg',
```
Both files are byte-identical to the accepted package official SVGs. The battery
step "Chromium responsive and offline PWA" PASS (49 assertions across 6 viewport
profiles plus offline fallback).

**Cold offline navigation/reference proof** (`offline_coldproof.png`, codex/0006 #5):
a real Chromium context served the site over http, registered `service-worker.js`,
and precached the shell; then with `context.setOffline(true)` a **brand-new cold
page** navigated to a cached route (no network) and pulled both marks through the
SW - `fetch` 200 `image/svg+xml` (light 4807 bytes), both `<img>` painted
(naturalWidth 1435), `navigator.onLine=false`, zero failed requests for the cached
shell. The screenshot shows both mode-matched marks rendered with network OFF.

**Close crops** (`crop_wordmark_dark.png`, `crop_wordmark_light.png`): the official
SVG at dSF 4 (~464px raster from a 116px CSS mark) - sharp, correctly mode-matched,
inside the 120px cap; intrinsic 1435x260, aspect preserved.

## Frame hashes (sha256)
```
598009b452ebd3cd0c7476f0d8228d4551ce30a186e787a44bacdd3145db1f3e  crop_wordmark_dark.png
4c69d7d63636b72cba357083dddf8cb30c2a169ed5eeb270d65d13b4865d6657  crop_wordmark_light.png
82c3d1ffea41ea7668da99719793168ce7dd0411cebf026d967e28ddf29a6ab4  e1_320x844_dark.png
f09c685c86c571a6eb14f8b06b7fa63c403fed6f106f571a82d843a7042ab2fe  e1_320x844_light.png
637f9c5a00d3bb7d2f50902a264b79c25b6db7afa2cf0fbc911bebf5c8b53f08  e1_390x844_dark.png
1be64ead30577ee854040d22b9001dca3a6f2c7ef70b411abfc5c4858d28427b  e1_390x844_dark_125.png
73c90c5f5540244953adbc756dcb60221d73c5145a90611bceb0c585ad1f2302  e1_390x844_light.png
45128f391361a010f6086dafae64091e4cc29573ce64693228e58a7cbba67b8e  e1_390x844_light_125.png
597a9753c8350f0a8ee85aab7268045cf672602041ffe3f53bcd6bf2b841e730  e1_800x1280_dark.png
d255f28324ed651d88e2ca52cc9b48870e9746a8018e8ff5852fb8656d8dc2b1  e1_800x1280_light.png
0d2e52e0c9d2768eb31c0cf18d839ea52d3f38b5d3fac2602b2bf3580e6b2709  e2_390x844_dark_NEG.png
df26a6e02c977693712a1fbbcdc2d68cee4a613caf4bb5e9ebcb834df8fb7786  e2_390x844_light_NEG.png
efffeaf242fcb24bc764a583d186227599a473f6a46f668c16496876f876dd46  e3_390x844_dark_NEG.png
b091922bc64c400b06ae67628445512bdd6ba5926c00a9e4c57fb3d672b5b15a  e3_390x844_light_NEG.png
b0f35179401022fc13779cec73793d6af2900dfc8f05dd504566474e91ec1ca3  e4_320x844_dark.png
491ce4f0437373acd492938c2fcab31f77acd2defa76a936e8f11590b23a924b  e4_320x844_light.png
056a8405a58045df41e56ade301b32be0999eda6173c7f43b951f01251cb426c  e4_390x844_dark.png
4da1bff43486dec956debd5cb11319f1535f3a5aff050774a7e84a408ed0d30c  e4_390x844_dark_125.png
819603ad97ffa608ab5508c47b20b111a81a2bd6a4937699a46f593a8f593310  e4_390x844_light.png
1748dfcc71666564c4888b44eddfd65af4b64a9c8824dae3f8742cd9b1800c4f  e4_390x844_light_125.png
71ebb3c5d0001df9969ea15410c875979c2dc93d792b19a4c6be1ab23e362e1d  e4_800x1280_dark.png
ddbf80a02b53b1b4b9ce5ad727c36b2dfa794cdf650292b5d856f87a577cfe0c  e4_800x1280_light.png
376d54eddb794772ec72c77a6e42629cec9d56cdb6656e6f47437bf890b4749b  offline_coldproof.png
```
