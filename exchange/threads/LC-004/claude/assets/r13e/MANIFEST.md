# LC-004 codex/0061 Completed-view projection (r13e) — complete exact-head E1-E8 package

Closes `codex/0061`: the visible **Completed** Tasks filter is now populated by a
strictly read-only projection of authoritatively completed Task records. This is
the single complete exact-head E1-E8 owner-facing render package; it supersedes
`r13d` (which was accepted at the pre-Completed head `60b643a`). Every surface
here is re-rendered at the exact replacement head so the whole package is one head.

| Field | Value |
|---|---|
| LineCheck exact head | `097b82da92f74a3b9b58d642fb7b1b6e3d87b3ed` (PR #14, draft) |
| Supersedes | `r13d` (accepted at `60b643a`); r13d frames remain valid for E1/E2/E4-E8, which are byte-identical at this head — the only behavioral delta is the populated Completed view |
| Local battery | 80 PASS / 0 FAIL / 0 SKIP |
| Exact-head green — authority/web-doc consistency | `31242320494` (success) |
| Exact-head green — controlled runtime gate | `31242320490` (success, no SKIP) |
| Forge asset commit (blob-pin) | `be4802073da8a7962d0564368e91e8905364afa2` |
| Actors | Evidence Staff (staff) · Evidence Manager (manager) |
| Viewports | 320x844, 390x844, 800x1280 portrait @ deviceScaleFactor 2 · dark+light · 125% root text on the primary flows · portrait only |
| Capture | headless Chromium (Playwright), fullPage, dSF 2; all 55 frames overflow-free |

## What codex/0061 required, and where it is proven

- **Populated, read-only projection** — `lc_tdb_completed_for()` / `lc_qdb_completed_tasks()` list finished Tasks the actor may already see (same WHERE + row-security as the open read); `routine.php` merges them into the queue pool as status `done`, so `lc_queue_filter` routes them into Completed alone. No write path, status transition, reward, review, or reopening was added.
- **Newest-first, null-last, deterministic ties** — the accepted `lc_queue_sort_completed` comparator (codex/0055) now has a real source. Fixture completion chronology conflicts with title and due-date order: **Zebra 11:20 -> Aardvark 09:00 -> Mango 07:40**, and the rendered order matches (see `e3-completed` frames).
- **Read-only presentation** — completed cards offer only **View**; never Claim, Start, Continue, or the authored OPEN. Proven in `smoke.php` (queue/0061) and visible in every `e3-completed` frame.
- **Authorization scope** — a person-assigned done Task belonging only to the manager (`Nutmeg`) is **absent** from the staff actor's Completed view; the projection reuses `lc_rsadb_allowed_facts(..,'queue')`.
- **Actionable views unchanged** — All/Mine/Team/Assignments/Fixes keep urgent/late-first ordering and exclude the completed projection (queue/0061 + existing filter regressions).
- **No new narrow-width risk** — the populated state is overflow-free at 320x844 and at 125% root text (title wraps, nothing clipped): `e3-completed_320x844_dark`, `e3-completed_390x844_{dark,light}_125`, `e3-completed_800x1280_dark_125`.

## Frames — grouped by surface (commit-pinned blob URLs)

### e1

| Frame | SHA-256 | Link |
|---|---|---|
| `e1_390x844_dark.png` | `400b6273b56decea353ae0849028179c7fc4e5763c0f648bb9bbc57807f10b81` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e1_390x844_dark.png) |
| `e1_390x844_dark_125.png` | `41fe6cbe51035b06fde2bc990f535e3d31eae37907566794b10a1cd886fc817b` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e1_390x844_dark_125.png) |
| `e1_390x844_light.png` | `b4c4944d90ad3308a218d2d775a181fb5aeb2b758db72e896525dbf1a04025dd` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e1_390x844_light.png) |
| `e1_390x844_light_125.png` | `971f064c1b47fd2887cb5abe6f6350cf69a28aed27f037c7d2fb53fcef015ae8` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e1_390x844_light_125.png) |
| `e1_800x1280_dark.png` | `56d255056fe1483a218a7539b145d01441dbd9357866de325f40d30fd5c1d8ea` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e1_800x1280_dark.png) |
| `e1_800x1280_dark_125.png` | `f0630988f8fbedace367a9bd9d7062006efbdd55700afc880bc31c1ea8d965f9` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e1_800x1280_dark_125.png) |
| `e1_800x1280_light.png` | `a58bf3db096b00fa17da0879b25b5306dd532859a64393e73304b1c7ff1c5e51` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e1_800x1280_light.png) |

### e2-progress0

| Frame | SHA-256 | Link |
|---|---|---|
| `e2-progress0_390x844_dark.png` | `a335cd9d3ab584946c2d3c56faeaf9953e99a32afccf9f032f6a15dfe37aaccb` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e2-progress0_390x844_dark.png) |
| `e2-progress0_390x844_light.png` | `4d3c4b43d2ffd3bfb8a8240c3b9c376ffcc8e12326313db7e3313046a747d55b` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e2-progress0_390x844_light.png) |

### e2

| Frame | SHA-256 | Link |
|---|---|---|
| `e2_320x844_dark.png` | `4485904f7638481d01026efa90933b4bb469b5b5123b1f6d7327c38a061a3a04` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e2_320x844_dark.png) |
| `e2_390x844_dark.png` | `16d8e2bbe54a212931a5ee340c6e5635ae0a6e63a74ff6d9331eecc585010cfd` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e2_390x844_dark.png) |
| `e2_390x844_dark_125.png` | `a704a834446de09e4ae9d18b1b57c8cdf86db831385b356fac42f761dec4757d` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e2_390x844_dark_125.png) |
| `e2_390x844_light.png` | `215e5ced288161e52509b2a0537e7cafbfafeaeb742dfc67dc25eb9057790214` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e2_390x844_light.png) |
| `e2_390x844_light_125.png` | `cf05c4751e46e38c5f60de5165e1635c1e248808d5654fd39899587b9c863646` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e2_390x844_light_125.png) |
| `e2_800x1280_dark.png` | `fb72d634acabcbb9870fb203ef258d359ee2332a8bdd3a269dc6ffc4f2ceff66` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e2_800x1280_dark.png) |
| `e2_800x1280_dark_125.png` | `28e4452c38a13215c2dde042c4fd74d2459173806614895b6ce99152b069a65c` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e2_800x1280_dark_125.png) |
| `e2_800x1280_light.png` | `84a00c7e2b0e37168d32033e21dd255de12c3cfb61518292f3bbe79e906355cf` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e2_800x1280_light.png) |

### e3-completed

| Frame | SHA-256 | Link |
|---|---|---|
| `e3-completed_320x844_dark.png` | `d31341397adbdb8822c278cfa59dc10173228f1642d73bdfa9b4ea3d731733b2` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e3-completed_320x844_dark.png) |
| `e3-completed_390x844_dark.png` | `eaee5cae6fd8b3ff44fdb3ed5787797cdab2e7ad90c8d53abeaf094db92841c0` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e3-completed_390x844_dark.png) |
| `e3-completed_390x844_dark_125.png` | `496a16730f9ae154ee44dadd0c6623d84829fb1923ef851f500411d36f8a269c` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e3-completed_390x844_dark_125.png) |
| `e3-completed_390x844_light.png` | `cb9c1de8bdb61c5be1a81166e21fe5a0190307bb444e44404e9ac770ccc0afbd` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e3-completed_390x844_light.png) |
| `e3-completed_390x844_light_125.png` | `2b311edddcffd18c54bb34d493d42ac44d0b85dcae67bf3c713d4d06c29a9158` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e3-completed_390x844_light_125.png) |
| `e3-completed_800x1280_dark.png` | `fe34915e0bea5f545477ec25d132cc7a0f8a3add9416d27ab01a5b4a29628f57` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e3-completed_800x1280_dark.png) |
| `e3-completed_800x1280_dark_125.png` | `c1dcc6be1af119beb3484ecebd95679fdf49a7ede7fcc0fabbc315eab049ac4e` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e3-completed_800x1280_dark_125.png) |
| `e3-completed_800x1280_light.png` | `c2746c8503aa4f5ef66f34b525f4fbb5393a41b869e83a80737ad307311e3ee5` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e3-completed_800x1280_light.png) |

### e3-fixes

| Frame | SHA-256 | Link |
|---|---|---|
| `e3-fixes_390x844_dark.png` | `08eb83dd899865131fe1e52d7d158f966478bc2c6464963474fcc7c958e10901` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e3-fixes_390x844_dark.png) |
| `e3-fixes_390x844_light.png` | `2784d75342841010cefb5cc0c0a615c0f4b8c71f867d9c5621fff977c796a166` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e3-fixes_390x844_light.png) |

### e3-open

| Frame | SHA-256 | Link |
|---|---|---|
| `e3-open_390x844_dark.png` | `1af423f9a127d56bef29b37617475f619e85b712d5aea4fa583e3b5aa750befc` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e3-open_390x844_dark.png) |
| `e3-open_390x844_light.png` | `93bb700c1300d800ef39e5e4c881409ea4a12faea85c1f95a4f506aa4987ee71` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e3-open_390x844_light.png) |

### e3

| Frame | SHA-256 | Link |
|---|---|---|
| `e3_320x844_dark.png` | `1c268eaf54861318bd99e96dea4648ffc146f8ff46d1f39d175c823cbc8b0464` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e3_320x844_dark.png) |
| `e3_390x844_dark.png` | `efffeaf242fcb24bc764a583d186227599a473f6a46f668c16496876f876dd46` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e3_390x844_dark.png) |
| `e3_390x844_dark_125.png` | `be6260369cc054269a6366c8a0d071281029a982bfe682ae62637835718efd74` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e3_390x844_dark_125.png) |
| `e3_390x844_light.png` | `b091922bc64c400b06ae67628445512bdd6ba5926c00a9e4c57fb3d672b5b15a` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e3_390x844_light.png) |
| `e3_390x844_light_125.png` | `b33f9db7bd3b427aef366943aa1104bc5c63c8c2873071c885c45cb187f4a7e0` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e3_390x844_light_125.png) |
| `e3_800x1280_dark.png` | `2f9d622a88bb0d9a5421ea663f5e510fb5de0e6f1e3f28fa0c89eff89c61eec4` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e3_800x1280_dark.png) |
| `e3_800x1280_dark_125.png` | `27306230d2236bfdac2180fc3a9cd33661f7ea10029d9e3b4edd45faa8ac3f05` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e3_800x1280_dark_125.png) |
| `e3_800x1280_light.png` | `6955835031b9c24e326428b0395e0399b72beafbc09361e0fdaca3d12c8e1e07` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e3_800x1280_light.png) |

### e4

| Frame | SHA-256 | Link |
|---|---|---|
| `e4_390x844_dark.png` | `18bdd012e9c529a79d5a46c2c6bee007b94f3e14f040dd12a30558d9003efb15` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e4_390x844_dark.png) |
| `e4_390x844_light.png` | `49c3feefccc2d02bd60ca15c62882ae417a21d980736b6677d5c9c5984a3064a` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e4_390x844_light.png) |
| `e4_800x1280_dark.png` | `6fb067c1375fca905f02722f9c57d2c4dd52521457ca4149c84ae2ccb7a6b49b` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e4_800x1280_dark.png) |
| `e4_800x1280_light.png` | `bf5ce1666ee8e6dc678b9851546c0ca669032612e50f6c7f9a97adb2cd583085` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e4_800x1280_light.png) |

### e5

| Frame | SHA-256 | Link |
|---|---|---|
| `e5_390x844_dark.png` | `bf21228795e790865db50de6bdb7127de2d2b7180c6ea9400dfa5ab7e33dbe73` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e5_390x844_dark.png) |
| `e5_390x844_light.png` | `26e3671b6143c5980c6cc2de8e059529bdae8de07b2f261116f392d5543cf96b` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e5_390x844_light.png) |

### e6

| Frame | SHA-256 | Link |
|---|---|---|
| `e6_390x844_dark.png` | `94532ee1fa0556c1b3c0e5310029260a0783f3307b6f9c4cb2198312a4294564` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e6_390x844_dark.png) |
| `e6_390x844_light.png` | `5611d95858efa128d33f8cd6ae7e99a4e7eaa568d2adbae8a26fcb07efe0cfcc` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e6_390x844_light.png) |

### e7

| Frame | SHA-256 | Link |
|---|---|---|
| `e7_390x844_dark.png` | `1191516ad50112fee6e5ba4547cab938734dc23eb1be6d47c9fbbc177057b503` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e7_390x844_dark.png) |
| `e7_390x844_light.png` | `e07ba00cb352d26fe48b5f6c4435fe323fa550c7ffcbf24f5d0c2ba91fba208b` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e7_390x844_light.png) |

### e8-collapsed

| Frame | SHA-256 | Link |
|---|---|---|
| `e8-collapsed_390x844_dark.png` | `047bb1bc1e4b911de82c70df2bebbd6a16ceca77ff992d70380a460aa7bbb6a0` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e8-collapsed_390x844_dark.png) |
| `e8-collapsed_390x844_light.png` | `18fb70d586e76ed747410d8822de8c8c99d7d2f9cb038d8cc600a705a7d19f50` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e8-collapsed_390x844_light.png) |

### e8-teamdir

| Frame | SHA-256 | Link |
|---|---|---|
| `e8-teamdir_390x844_dark.png` | `a4607b268f61c714138f905fa08b6500b4b45f67b58888f23e4bfbdf94fc43f2` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e8-teamdir_390x844_dark.png) |
| `e8-teamdir_390x844_light.png` | `c08d3231a3b8bf274f14a2ad26dc12588ed54ab79caa72c3eb17d2ffcf6ca270` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e8-teamdir_390x844_light.png) |

### e8

| Frame | SHA-256 | Link |
|---|---|---|
| `e8_390x844_dark.png` | `e489bc4fd0a2e3406fa1dac85b5977763530d2de8bea3bf78ba19471c5cbd17c` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e8_390x844_dark.png) |
| `e8_390x844_light.png` | `bb9ea205c3a73d79124c2b8d14df3f2dd1aef96513fc2287a8d2b3b94bd385d3` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e8_390x844_light.png) |
| `e8_800x1280_dark.png` | `01b0dc93f5cbd540adb19bd891fe3004a1eee1d32bf48433285d6cd0cb976dba` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e8_800x1280_dark.png) |
| `e8_800x1280_light.png` | `28af58bb63b0498c1ef4f59755a8aaf4658101ee24fc5eff9f42db5af037428d` | [view](https://github.com/derickonfire/emotivus-forge/blob/be4802073da8a7962d0564368e91e8905364afa2/exchange/threads/LC-004/claude/assets/r13e/e8_800x1280_light.png) |
