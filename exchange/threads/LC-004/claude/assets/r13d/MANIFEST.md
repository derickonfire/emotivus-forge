# LC-004 codex/0059 disclosure-chevron correction (r13d) — manifest

Closes codex/0059 (owner visual gate): conventional disclosure grammar — closed = right-facing outlined chevron, open = down-facing, one code-native shape rotated 90 degrees.

| Field | Value |
|---|---|
| LineCheck exact head | `60b643a467530a42ec4f826e9c4f4acc0f94f6b3` (PR #14, draft) |
| Local battery | 80 PASS / 0 FAIL / 0 SKIP |
| Exact-head green — authority/web-doc consistency | `31232105538` |
| Exact-head green — controlled runtime gate | `31232105537` (clean, no SKIP) |
| Forge asset commit (blob-pin) | `a6d610534020a0ae894074c820afc8d93f85ff05` |
| Geometry probe (390×844, dSF2) | Settings + Show Tasks: closed=rotate(0)=RIGHT, open=rotate(90deg)=DOWN; reserved box 40px in a 48px row = ratio 0.833 (~80%); row height IDENTICAL with the chevron hidden (unchanged); summary target 48px (>=48, compliant) |
| Actors | Evidence Staff (staff) · Evidence Manager (manager) |
| Viewports | 320×844, 390×844, 800×1280 portrait @ deviceScaleFactor 2 · dark+light · 125% root (e1,e2,e7,e8-teamdir) · portrait only |
| Capture | headless Chromium (Playwright), fullPage, dSF 2; all 51 frames overflow-free |

## Chevron proof frames (codex/0059)
- E8 all-sections-collapsed 390 dark+light → right-facing chevrons: e8-collapsed_390x844_{dark,light}
- E8 Team Directory open 390 dark+light → down-facing: e8-teamdir_390x844_{dark,light}
- E7 Notifications open 390 dark+light → down-facing: e7_390x844_{dark,light}
- E3 Show Tasks closed 390 dark+light → right-facing: e3_390x844_{dark,light}
- E3 Show Tasks open 390 dark+light → down-facing: e3-open_390x844_{dark,light}
- 320px densest affected (dark): e8-collapsed_320x844_dark, e3-open_320x844_dark

## Frames — grouped by surface and theme (commit-pinned blob URLs)

### E1 — staff Home

| Frame | SHA-256 | Link |
|---|---|---|
| `e1_320x844_dark.png` | `725f6c7d078e735261bdbacdff7c265dd3ff9594fd6d4ea65cfc1b8526e7dcc5` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e1_320x844_dark.png) |
| `e1_390x844_dark.png` | `36003301497265a7735218e4d9ef1cd10ed5d4f1531e7e36998f840747e58304` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e1_390x844_dark.png) |
| `e1_390x844_dark_125.png` | `fcf611dcc61854f0ef4c0693ae7e009823af4760c9e34da4e9f9d6e93e445cc9` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e1_390x844_dark_125.png) |
| `e1_390x844_light.png` | `23961f7c8858e6913e6a31a78a5a45ca3cc85a368424ba17017914a57b647d0e` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e1_390x844_light.png) |
| `e1_800x1280_dark.png` | `cbe94d49606e7f2e1280db308955a3deef74b159f0724e00293a733b4d349be0` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e1_800x1280_dark.png) |
| `e1_800x1280_dark_125.png` | `db7efffc547eda7a0575858be8507e4d2d3488115224aa2eed4e38765e345e6e` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e1_800x1280_dark_125.png) |
| `e1_800x1280_light.png` | `118e509307b025e416f3815badc855638bd25bbec1fe214235d066dc6f28a796` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e1_800x1280_light.png) |

### E2 — Routine

| Frame | SHA-256 | Link |
|---|---|---|
| `e2_320x844_dark.png` | `cf615c4f90198fe0987e7d1dfad30a41b2d2a91a165103a25780e3e39715eef6` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e2_320x844_dark.png) |
| `e2_390x844_dark.png` | `3f0a5b4055654faa90a6835b9b55adcba991f42b57561cf6b150a1650309da84` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e2_390x844_dark.png) |
| `e2_390x844_dark_125.png` | `2b54c6a0c6a6dbf623c7bc32646ec694da764f881edd96d54c375cf12eeee5b6` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e2_390x844_dark_125.png) |
| `e2_390x844_light.png` | `f3742ea9735a940e44594fd043596e5cfbbe3b9f5425271a0e2cfe76a8996917` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e2_390x844_light.png) |
| `e2_800x1280_dark.png` | `0756b7886bd3aa97ec87f0ea7fa2b1e1e87ba24d7d124d831c050cad3f25592f` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e2_800x1280_dark.png) |
| `e2_800x1280_dark_125.png` | `4cb4b1774af675b8acd5d00dd5d83c5cbb04398e1defb781d911e11acd8b02b5` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e2_800x1280_dark_125.png) |
| `e2_800x1280_light.png` | `cc3f1797d19bef7e9ac16439fa78e750299d4692cdcc784e8d7ac78094dd3756` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e2_800x1280_light.png) |

### E3 — Show Tasks CLOSED (right chevron)

| Frame | SHA-256 | Link |
|---|---|---|
| `e3_320x844_dark.png` | `554e47d2c0ab1600014e29b55edba3211aadbefae9dfb7164d136e8ad6b63272` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e3_320x844_dark.png) |
| `e3_390x844_dark.png` | `2f4564cc57527b0bb398da4dda662fc22387c929aab4c1c524761263f651eb66` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e3_390x844_dark.png) |
| `e3_390x844_light.png` | `11fb00ac6f737f2307ac8a95814d5ab63a481e4c12b89e92a693e9719a0da6ad` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e3_390x844_light.png) |
| `e3_800x1280_dark.png` | `64536e75168f480bdfc6fcdf0aa4e71d1559b8dfaa86a344ae06135f3a9b6857` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e3_800x1280_dark.png) |
| `e3_800x1280_light.png` | `4a23a13b499c4660dacecb6b87eb07c32c7b1fbc490f233cd1c79877fb0a7160` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e3_800x1280_light.png) |

### E3 — Show Tasks OPEN (down chevron)

| Frame | SHA-256 | Link |
|---|---|---|
| `e3-open_320x844_dark.png` | `dc387ac4e73f1daf08e513e7d7a2c08e6da172f06c6d34ae8335c0cf9c180667` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e3-open_320x844_dark.png) |
| `e3-open_390x844_dark.png` | `1af423f9a127d56bef29b37617475f619e85b712d5aea4fa583e3b5aa750befc` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e3-open_390x844_dark.png) |
| `e3-open_390x844_light.png` | `93bb700c1300d800ef39e5e4c881409ea4a12faea85c1f95a4f506aa4987ee71` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e3-open_390x844_light.png) |

### E3 — Fixes card (authored OPEN)

| Frame | SHA-256 | Link |
|---|---|---|
| `e3-fixes_390x844_dark.png` | `17c6ac454c9567d3ef0f38cffd8615c53776b62e75a32079690493c228a32499` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e3-fixes_390x844_dark.png) |
| `e3-fixes_390x844_light.png` | `208cf86ff8043776f18b6c260ae1b435e1d5f6ac8ff6811320bd8a04186fbaab` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e3-fixes_390x844_light.png) |

### E4 — manager Dashboard

| Frame | SHA-256 | Link |
|---|---|---|
| `e4_390x844_dark.png` | `4ffdc01755fc0b87f03fdc63096d062091f7715bee2b0ecded1175645121421e` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e4_390x844_dark.png) |
| `e4_390x844_light.png` | `019442f0054651c790f0ebb5e924b9ea81a66679a0150eb2bbbd30b28f2e569e` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e4_390x844_light.png) |
| `e4_800x1280_dark.png` | `c6c0234735aaf7166f14a040daa0f593fc2b809fedf7997af8aed2a1364f967b` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e4_800x1280_dark.png) |
| `e4_800x1280_light.png` | `06cd8497140bdbed1f1f39556cae6991e91574100b1a3c5c3dd6356a56f13283` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e4_800x1280_light.png) |

### E5 — manager review

| Frame | SHA-256 | Link |
|---|---|---|
| `e5_390x844_dark.png` | `263f4204585cf08e0ef143825f70ffb56556377b3c709712ba721c7ab862fbc3` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e5_390x844_dark.png) |
| `e5_390x844_light.png` | `21bbd605fe16364884b77650c4d208dd7409ea08e4973fdf82336dd4cabf1dfe` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e5_390x844_light.png) |
| `e5_800x1280_dark.png` | `11d00b4addb25431c79a5dbeee82c95cb8ab2eb2a0a7ab9ae33b1e8710d02f16` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e5_800x1280_dark.png) |
| `e5_800x1280_light.png` | `1fe7518b2ef78164b364ed0cc9667e346f9fbcadb893dfae835946ec8381efd4` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e5_800x1280_light.png) |

### E6 — fail-closed refusal

| Frame | SHA-256 | Link |
|---|---|---|
| `e6_390x844_dark.png` | `94532ee1fa0556c1b3c0e5310029260a0783f3307b6f9c4cb2198312a4294564` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e6_390x844_dark.png) |
| `e6_390x844_light.png` | `5611d95858efa128d33f8cd6ae7e99a4e7eaa568d2adbae8a26fcb07efe0cfcc` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e6_390x844_light.png) |

### E7 — Notifications open (down chevron)

| Frame | SHA-256 | Link |
|---|---|---|
| `e7_320x844_dark.png` | `af51f593c2837d32ae107202e33779a1e0604ccca256f4636ef144e58c4fc6a3` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e7_320x844_dark.png) |
| `e7_390x844_dark.png` | `1191516ad50112fee6e5ba4547cab938734dc23eb1be6d47c9fbbc177057b503` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e7_390x844_dark.png) |
| `e7_390x844_dark_125.png` | `f2a0ef78c36bcd1654d033947605d6a89cd9e34c1b7c1058646182c8504ff9ba` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e7_390x844_dark_125.png) |
| `e7_390x844_light.png` | `e07ba00cb352d26fe48b5f6c4435fe323fa550c7ffcbf24f5d0c2ba91fba208b` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e7_390x844_light.png) |
| `e7_800x1280_dark.png` | `7cd07e72e7b3cf2acaafcf0c556c920119b84920b2960851f33ceb71d092dd54` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e7_800x1280_dark.png) |
| `e7_800x1280_light.png` | `2769ee6c15432201093d0065a7be8970405ff5cff29906437f5708a11aa11439` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e7_800x1280_light.png) |

### E8 — Settings collapsed (right chevrons)

| Frame | SHA-256 | Link |
|---|---|---|
| `e8-collapsed_320x844_dark.png` | `5a9225a6c3a285d264a9e088663b5c3af26902e55dcdc0c3df6ffb5a321d97ab` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e8-collapsed_320x844_dark.png) |
| `e8-collapsed_390x844_dark.png` | `047bb1bc1e4b911de82c70df2bebbd6a16ceca77ff992d70380a460aa7bbb6a0` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e8-collapsed_390x844_dark.png) |
| `e8-collapsed_390x844_light.png` | `18fb70d586e76ed747410d8822de8c8c99d7d2f9cb038d8cc600a705a7d19f50` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e8-collapsed_390x844_light.png) |
| `e8-collapsed_800x1280_dark.png` | `e49932fd47150fba6de837861937edfbecf62a3679be3a044d034380f6ff1cf1` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e8-collapsed_800x1280_dark.png) |
| `e8-collapsed_800x1280_light.png` | `a68a116cc70122e5de539bdeda119452cd1ac5e473bd2c0b0fc6a3753de93352` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e8-collapsed_800x1280_light.png) |

### E8 — Team Directory open (down chevron, per-channel consent + SAVE)

| Frame | SHA-256 | Link |
|---|---|---|
| `e8-teamdir_320x844_dark.png` | `88d791c18efcb067ed228c405167dda5dd90339137ae64ae330be60851577018` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e8-teamdir_320x844_dark.png) |
| `e8-teamdir_390x844_dark.png` | `a4607b268f61c714138f905fa08b6500b4b45f67b58888f23e4bfbdf94fc43f2` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e8-teamdir_390x844_dark.png) |
| `e8-teamdir_390x844_dark_125.png` | `5b6f02d4feb9cf39bf11571e856f8a4e07bb22abbf12e85ed7695cde5f734d66` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e8-teamdir_390x844_dark_125.png) |
| `e8-teamdir_390x844_light.png` | `c08d3231a3b8bf274f14a2ad26dc12588ed54ab79caa72c3eb17d2ffcf6ca270` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e8-teamdir_390x844_light.png) |
| `e8-teamdir_800x1280_dark.png` | `61ea4661599377d45b03fd3a84f3b5c5c7977acca023990332d5472f96fff774` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e8-teamdir_800x1280_dark.png) |
| `e8-teamdir_800x1280_light.png` | `0bb40a74caae7edef5b432f808b7cba2a9ffc5754174e506127bd660e4f983be` | [view](https://github.com/derickonfire/emotivus-forge/blob/a6d610534020a0ae894074c820afc8d93f85ff05/exchange/threads/LC-004/claude/assets/r13d/e8-teamdir_800x1280_light.png) |
