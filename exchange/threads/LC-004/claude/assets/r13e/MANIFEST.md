# LC-004 codex/0061 + codex/0063 Completed view (r13e) — complete exact-head E1-E8 package

The visible **Completed** Tasks filter is populated by a strictly read-only
projection of authoritatively completed Task records (`codex/0061`), rendered as
**settled history** (`codex/0063`): realistic titles, quiet recessed cards, a
restrained secondary View, and one truthful accountability line. This is the
single complete exact-head E1-E8 owner-facing package; it **supersedes r13d**
(accepted at the pre-Completed head `60b643a`). Every surface is re-rendered at
the exact replacement head so the whole package is one head.

| Field | Value |
|---|---|
| LineCheck exact head | `276b3525d7f123d5751bcb016f118b190e9c3960` (PR #14, draft) |
| Supersedes | `r13d` (accepted at `60b643a`) — r13d frames remain valid for E1/E2/E4-E8; the only behavioral delta is the populated, settled Completed view |
| Local battery | 80 PASS / 0 FAIL / 0 SKIP |
| Exact-head green — authority/web-doc consistency | `31243106840` (success) |
| Exact-head green — controlled runtime gate | `31243106834` (success, no SKIP) |
| Forge asset commit (blob-pin) | `c78e9b188e1b2f8befde56b694430bf2f28a866a` |
| Actors | Evidence Staff ("You") · Maya (teammate) · Evidence Manager |
| Viewports | 320x844, 390x844, 800x1280 portrait @ deviceScaleFactor 2 · dark+light · 125% root text on the primary flows · portrait only |
| Capture | headless Chromium (Playwright), fullPage, dSF 2; all 55 frames overflow-free |

## codex/0063 visual revision — what changed and where it is proven

- **Realistic titles, no test mechanics** — "Wipe the Window Ledges", "Restock
  Straws", "Refill the Napkins". Newest-first is proven by authoritative
  `completed_at` and stable ids in the fixture probe (DOM id order
  `971 → 970 → 972` for completion `11:20 → 09:00 → 07:40`), never by title wording.
- **Settled, not three primary actions** — completed cards recede onto the page
  ground with a neutral accent (`.qcard-settled`), drop the saturated status pill,
  and open with a **restrained secondary View** (`btn-ghost`, ≥48px, visible label)
  instead of a full-width primary call. Active Tasks/Side Work keep the stronger
  hierarchy; history no longer competes with them.
- **Truthful accountability, not an ambiguous MINE pill** — one quiet line from the
  record's own facts: **"Completed by You · 11:20 AM"** and **"Completed by Maya ·
  7:40 AM"**. Shown only when actor/time exist; never inferred. The `Mine` tag is
  gone from settled cards.
- **Still read-only + authorization-scoped** — no completion control; the
  manager-only person-assigned record is absent from the staff actor's view.

## codex/0061 core (unchanged, still proven)

- Read-only projection (`lc_tdb_completed_for` / `lc_qdb_completed_tasks`): same
  WHERE + row-security as the open read; routed into Completed alone via status
  `done`; excluded from every actionable view (smoke queue/0061). No write path.
- Newest-first, null-last, deterministic ties (`lc_queue_sort_completed`, codex/0055).

## Frames — grouped by surface (commit-pinned blob URLs)

### e1

| Frame | SHA-256 | Link |
|---|---|---|
| `e1_390x844_dark.png` | `7c31140897dd258d6a80cc560761add30c4def44020391108b16141b921c8cca` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e1_390x844_dark.png) |
| `e1_390x844_dark_125.png` | `07b27accae7cbd273d835a7a8d5c5f6bc75b4dc9805ee8b54b90b6db4bedff9f` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e1_390x844_dark_125.png) |
| `e1_390x844_light.png` | `df6261e1c00f2f9a885960677a30264abfbf90b0bbdd55ddcfffb3c4fd9358c1` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e1_390x844_light.png) |
| `e1_390x844_light_125.png` | `a207c6a77977c7b326dcbe696678981cf4af7f49bda365cfcbdebc52ee1af174` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e1_390x844_light_125.png) |
| `e1_800x1280_dark.png` | `b81a829438baf6d45e424b464002f9e9a20d546c134a400e40f1a8f16e4e6cd4` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e1_800x1280_dark.png) |
| `e1_800x1280_dark_125.png` | `2ed5bb69a078d126ab39b72e98d13db786d3616d36fb801112fc5cd9f78bdd62` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e1_800x1280_dark_125.png) |
| `e1_800x1280_light.png` | `009f85fc7124545edf33b0e97b030e3d9e1f23108c74adbae12a8ce0d3c00cc8` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e1_800x1280_light.png) |

### e2-progress0

| Frame | SHA-256 | Link |
|---|---|---|
| `e2-progress0_390x844_dark.png` | `a335cd9d3ab584946c2d3c56faeaf9953e99a32afccf9f032f6a15dfe37aaccb` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e2-progress0_390x844_dark.png) |
| `e2-progress0_390x844_light.png` | `4d3c4b43d2ffd3bfb8a8240c3b9c376ffcc8e12326313db7e3313046a747d55b` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e2-progress0_390x844_light.png) |

### e2

| Frame | SHA-256 | Link |
|---|---|---|
| `e2_320x844_dark.png` | `df00eab8f6bf4d159333b2a74b4da77b6f944ebf205faf84aa1d5e854da6ed1c` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e2_320x844_dark.png) |
| `e2_390x844_dark.png` | `c5fee937ade2729cc998576179cee5f1926e7c8cc3583119b224b05ace051ed9` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e2_390x844_dark.png) |
| `e2_390x844_dark_125.png` | `6db15d113745ee34124e64b82f028332ab396d6d0518bf3bcf84be89204132af` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e2_390x844_dark_125.png) |
| `e2_390x844_light.png` | `7da81ff7751b5fd7d732846bbd21e3b166d9546edacda3de3d35598545c5358c` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e2_390x844_light.png) |
| `e2_390x844_light_125.png` | `3797a47d23dcb0b0de3e009f6adc2235c830fd93117b73d60fa6e8f3d85e087f` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e2_390x844_light_125.png) |
| `e2_800x1280_dark.png` | `c60a4bf16d700244f249bf6b848b08bdcb081ff83f3815691a669665f5910069` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e2_800x1280_dark.png) |
| `e2_800x1280_dark_125.png` | `7f1cac8b26e0cda1660f2c12d7bf37f5ae3e14316d1faeefbc2e216c29dff13d` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e2_800x1280_dark_125.png) |
| `e2_800x1280_light.png` | `84a00c7e2b0e37168d32033e21dd255de12c3cfb61518292f3bbe79e906355cf` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e2_800x1280_light.png) |

### e3-completed

| Frame | SHA-256 | Link |
|---|---|---|
| `e3-completed_320x844_dark.png` | `94db4d253ab253d73de4212968eb1d1d4b1598b4ef616ca36f1886987fd81de9` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e3-completed_320x844_dark.png) |
| `e3-completed_390x844_dark.png` | `3119b3107b83a379823c642b8f881ddf9081e749ad3dde62fea10348d8782427` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e3-completed_390x844_dark.png) |
| `e3-completed_390x844_dark_125.png` | `d446035e832eb8b26e62f5084c9a98955f9ad98a92c02b08553b066f95e710c7` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e3-completed_390x844_dark_125.png) |
| `e3-completed_390x844_light.png` | `4b30aadae318b7a5265ead2ce1311d4c93b36fa19a2734d6971a02ae5ae789a4` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e3-completed_390x844_light.png) |
| `e3-completed_390x844_light_125.png` | `08c5cb654d59a9eb6c55517bd9edf9196b350bde969d528e974feea57a0cebc3` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e3-completed_390x844_light_125.png) |
| `e3-completed_800x1280_dark.png` | `ee53b475b8a064a6684b481f0fabdc074455790285c88ee7c17e7fd28bf5db2b` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e3-completed_800x1280_dark.png) |
| `e3-completed_800x1280_dark_125.png` | `0636db98d47b123cba9ce8d38a910e34a01847fa2732ce9fb3e45b736dbbbc21` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e3-completed_800x1280_dark_125.png) |
| `e3-completed_800x1280_light.png` | `a62598f72d33b326c63441d7bf8d17e19bccda8f942f55a74c374ed1ed4ed992` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e3-completed_800x1280_light.png) |

### e3-fixes

| Frame | SHA-256 | Link |
|---|---|---|
| `e3-fixes_390x844_dark.png` | `08eb83dd899865131fe1e52d7d158f966478bc2c6464963474fcc7c958e10901` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e3-fixes_390x844_dark.png) |
| `e3-fixes_390x844_light.png` | `2784d75342841010cefb5cc0c0a615c0f4b8c71f867d9c5621fff977c796a166` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e3-fixes_390x844_light.png) |

### e3-open

| Frame | SHA-256 | Link |
|---|---|---|
| `e3-open_390x844_dark.png` | `1af423f9a127d56bef29b37617475f619e85b712d5aea4fa583e3b5aa750befc` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e3-open_390x844_dark.png) |
| `e3-open_390x844_light.png` | `93bb700c1300d800ef39e5e4c881409ea4a12faea85c1f95a4f506aa4987ee71` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e3-open_390x844_light.png) |

### e3

| Frame | SHA-256 | Link |
|---|---|---|
| `e3_320x844_dark.png` | `1c268eaf54861318bd99e96dea4648ffc146f8ff46d1f39d175c823cbc8b0464` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e3_320x844_dark.png) |
| `e3_390x844_dark.png` | `efffeaf242fcb24bc764a583d186227599a473f6a46f668c16496876f876dd46` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e3_390x844_dark.png) |
| `e3_390x844_dark_125.png` | `be6260369cc054269a6366c8a0d071281029a982bfe682ae62637835718efd74` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e3_390x844_dark_125.png) |
| `e3_390x844_light.png` | `b091922bc64c400b06ae67628445512bdd6ba5926c00a9e4c57fb3d672b5b15a` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e3_390x844_light.png) |
| `e3_390x844_light_125.png` | `b33f9db7bd3b427aef366943aa1104bc5c63c8c2873071c885c45cb187f4a7e0` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e3_390x844_light_125.png) |
| `e3_800x1280_dark.png` | `2f9d622a88bb0d9a5421ea663f5e510fb5de0e6f1e3f28fa0c89eff89c61eec4` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e3_800x1280_dark.png) |
| `e3_800x1280_dark_125.png` | `27306230d2236bfdac2180fc3a9cd33661f7ea10029d9e3b4edd45faa8ac3f05` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e3_800x1280_dark_125.png) |
| `e3_800x1280_light.png` | `6955835031b9c24e326428b0395e0399b72beafbc09361e0fdaca3d12c8e1e07` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e3_800x1280_light.png) |

### e4

| Frame | SHA-256 | Link |
|---|---|---|
| `e4_390x844_dark.png` | `66985f51b0a69c1b78d0c6afa664b6ba0948481734d2748e6708a4f625cda410` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e4_390x844_dark.png) |
| `e4_390x844_light.png` | `23d80857c64422b928ce57dacd15011a207f886dc0e3535f7e0f957af2929b6b` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e4_390x844_light.png) |
| `e4_800x1280_dark.png` | `ad2a6e824447b87ae16aff9806499f29b01a600dfe8b1f570f2b0b65912c0687` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e4_800x1280_dark.png) |
| `e4_800x1280_light.png` | `c2a4e1aef846bba78e7b18d9a3ff5b7945f5adb6839c233655c2378106a3baa2` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e4_800x1280_light.png) |

### e5

| Frame | SHA-256 | Link |
|---|---|---|
| `e5_390x844_dark.png` | `00e67a598d8d4ef14418eb63f19c87c20f1a42782b85551d6f97ffd2bec54e55` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e5_390x844_dark.png) |
| `e5_390x844_light.png` | `e618c9709f6957afb48a022cd83e128e55ee20741eeb9e688af4e9534ad5e854` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e5_390x844_light.png) |

### e6

| Frame | SHA-256 | Link |
|---|---|---|
| `e6_390x844_dark.png` | `94532ee1fa0556c1b3c0e5310029260a0783f3307b6f9c4cb2198312a4294564` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e6_390x844_dark.png) |
| `e6_390x844_light.png` | `5611d95858efa128d33f8cd6ae7e99a4e7eaa568d2adbae8a26fcb07efe0cfcc` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e6_390x844_light.png) |

### e7

| Frame | SHA-256 | Link |
|---|---|---|
| `e7_390x844_dark.png` | `1191516ad50112fee6e5ba4547cab938734dc23eb1be6d47c9fbbc177057b503` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e7_390x844_dark.png) |
| `e7_390x844_light.png` | `e07ba00cb352d26fe48b5f6c4435fe323fa550c7ffcbf24f5d0c2ba91fba208b` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e7_390x844_light.png) |

### e8-collapsed

| Frame | SHA-256 | Link |
|---|---|---|
| `e8-collapsed_390x844_dark.png` | `047bb1bc1e4b911de82c70df2bebbd6a16ceca77ff992d70380a460aa7bbb6a0` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e8-collapsed_390x844_dark.png) |
| `e8-collapsed_390x844_light.png` | `18fb70d586e76ed747410d8822de8c8c99d7d2f9cb038d8cc600a705a7d19f50` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e8-collapsed_390x844_light.png) |

### e8-teamdir

| Frame | SHA-256 | Link |
|---|---|---|
| `e8-teamdir_390x844_dark.png` | `a4607b268f61c714138f905fa08b6500b4b45f67b58888f23e4bfbdf94fc43f2` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e8-teamdir_390x844_dark.png) |
| `e8-teamdir_390x844_light.png` | `c08d3231a3b8bf274f14a2ad26dc12588ed54ab79caa72c3eb17d2ffcf6ca270` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e8-teamdir_390x844_light.png) |

### e8

| Frame | SHA-256 | Link |
|---|---|---|
| `e8_390x844_dark.png` | `f6956bd4e86dc31de6d37995d0f255669982be8f25f35cc297f0916ed29438ef` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e8_390x844_dark.png) |
| `e8_390x844_light.png` | `7575920ff3e0f5882a3f9b03678eed724df65212cbf48f9cf2df7856afc8fa42` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e8_390x844_light.png) |
| `e8_800x1280_dark.png` | `61ad7268301d824bdee2e4c2350a55ce2b67810d38917dc4c8eb2b055f5f6b37` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e8_800x1280_dark.png) |
| `e8_800x1280_light.png` | `089346f2be7ec8ecb929b2711a9a050e60498e418f59bfa69a6fcb602d9ec7d8` | [view](https://github.com/derickonfire/emotivus-forge/blob/c78e9b188e1b2f8befde56b694430bf2f28a866a/exchange/threads/LC-004/claude/assets/r13e/e8_800x1280_light.png) |
