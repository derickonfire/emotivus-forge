# LC-004 codex/0052 cross-surface revision (r13) — evidence manifest

| Field | Value |
|---|---|
| LineCheck exact head | `0f344b7a32aa5bc59337ef469dabf2e9c61b823a` (PR #14, draft) |
| Local battery | 80 PASS / 0 FAIL / 0 SKIP |
| Exact-head green run — authority/web-doc consistency | `31230085190` |
| Exact-head green run — controlled runtime gate | `31230082567` |
| codex/0055 (Completed newest-first) | ordering contract + gate-enforced regression proof in smoke (`queue/0055`): a fixture whose completion chronology conflicts with title AND due-date order is newest-completed-first, the same pool under the actionable sort stays due-first, null sorts last, tie-breaker deterministic. The images below are unchanged by codex/0055 (it reorders the Completed list only, no visual change to the rendered surfaces); the live Completed view is currently unpopulated because the Task-source reads fetch open rows only — see claude/0048 for the scope note. |
| Actors | Evidence Staff (role: staff) · Evidence Manager (role: manager) |
| Fixture | real MariaDB (schema + all migrations, candidate schema 74); seeded Opening/Closing side work (3-of-8 mid-progress), a Both pair, a claimable Deep Clean, standalone + stale Tasks, per-channel consent |
| Viewports | 320×844, 390×844, 800×1280 (tablet portrait) @ deviceScaleFactor 2 |
| Themes | dark + light |
| Text scaling | 125% root text on 390 and 800×1280 (e1, e2) |
| Orientation | portrait only (no landscape, per §8) |
| Capture | headless Chromium (Playwright), fullPage, deviceScaleFactor 2; all frames overflow-free (scrollWidth ≤ innerWidth) |

## Frames

Naming: `<surface>_<cssW>x<cssH>_<theme>[_125].png` — surfaces: e1 staff Home, e2 staff Routine, e3 staff Tasks, e4 manager Dashboard, e6 staff fail-closed refusal, e8 staff Settings.

| File | SHA-256 |
|---|---|
| `e1_390x844_dark.png` | `f9ef81c49b64c191c50790beadeeb021c853c0df5249a0e26ea9d81233dc4863` |
| `e1_390x844_dark_125.png` | `180a6043e50f559707828ed0735656a1652a3a636cf716aad64cd7cb7b5e22e3` |
| `e1_390x844_light.png` | `0650d69505e07f0d0be2d04a0c097029f9d9645539e3f02dbbeec6be9abe5bb4` |
| `e1_800x1280_dark.png` | `9857bc084ae1ab262c2bc0c795f0d9bc00c4d1bb3f8ceb0cb2dc9d64a7ef91f7` |
| `e1_800x1280_dark_125.png` | `337c46b941214a48beb2a27431f95bc70fbfb0ee3648c0eca924e12d00ed9738` |
| `e1_800x1280_light.png` | `03a2cc6b2a07ded8d6542436ce2d9f65e4fa67cb5bdb550c1a1de069ddd34a94` |
| `e2_320x844_dark.png` | `0c7bc91174dc6f82d141cfbbb6ce3a094ee8d4d8310b7d08f6180d64dd2d300a` |
| `e2_390x844_dark.png` | `3f0a5b4055654faa90a6835b9b55adcba991f42b57561cf6b150a1650309da84` |
| `e2_390x844_dark_125.png` | `54991a3a2e6b335f97f85120f1bef22734cf7b9adf88e5219af28bf3974e725d` |
| `e2_390x844_light.png` | `d2868e22da2e35a0c3eeade90ef1599f79a88508b3c41a8c1ed80afed211789e` |
| `e2_800x1280_dark.png` | `29fd63059e5ad94a5a15d620c9282468b72a0f1b7f5a3b247646fb0b679ca983` |
| `e2_800x1280_dark_125.png` | `f28921934199fc1e46c343048644ae40b0f3911b18b46d32466469e571c91145` |
| `e2_800x1280_light.png` | `b09700e2ad3631c24769a29095abfb4f013f770cbfdb5a4913729b5a06254266` |
| `e3_320x844_dark.png` | `a8b162ec96e2da751be42c4e302d935e214d8f5e94430d37047ce4651138a4f7` |
| `e3_390x844_dark.png` | `11d33a44e881c00a1c052f92af101b57f369c0a1dfb225bf52c897c9691d4392` |
| `e3_390x844_light.png` | `e788342a218d270746471ca4366310d44bfea51aa0e275b89e7b76fa34754b2f` |
| `e3_800x1280_dark.png` | `d02c8c6925e0e6176de5635c3f6c89c85461e977447a7697e6232aaa27a777fa` |
| `e3_800x1280_light.png` | `8f5cabdbb2d12ebf7f89320f02d9bb5292a8e409f19c2d264034beed3f1705cc` |
| `e4_800x1280_dark.png` | `45aac33c303685f30e392cdb3b39e3e166b89f34c2c6e448465429b5117194e4` |
| `e4_800x1280_light.png` | `c59e6f0c85ba5b41529938c58617bc25099331def9395a0bd643be581d29eb87` |
| `e6_390x844_dark.png` | `94532ee1fa0556c1b3c0e5310029260a0783f3307b6f9c4cb2198312a4294564` |
| `e6_390x844_light.png` | `5611d95858efa128d33f8cd6ae7e99a4e7eaa568d2adbae8a26fcb07efe0cfcc` |
| `e8_390x844_dark.png` | `28cd420a100655d0b261e10763f07acfc4c16f0d0156163789351e5510b81e1b` |
| `e8_390x844_light.png` | `a7eae6a2827333557ad19a45dfcdb52cd844b778e0f3c66d96742526d614e736` |
| `e8_800x1280_dark.png` | `9f9dbb1bba08ebbd2340f07d33c507d53d2fbb77b6c8558d884b2e067788dbf5` |
| `e8_800x1280_light.png` | `12c26baa65f0c761b4df06e6c5a890f00c04c2d740f13f3d003cd3323ac666d0` |
