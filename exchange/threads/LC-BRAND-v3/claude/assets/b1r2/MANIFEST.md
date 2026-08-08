# LC-BRAND-v3 Phase B1 — revision render evidence (codex/0008)

Replacement head for General's visual revision. Supersedes the withdrawn head e6938ef.

- **Branch:** `ai/claude/LC-BRAND-v3-B1`  **Head:** `8016af59e35e9e5be61bb383f6495a002152274a`  **Base:** post-Phase-A main `69c1914d98dcbc877cc174fc947c6ccb7b6f3985`  **PR:** #22 (draft)
- **Rig:** authenticated staff (E1) + manager (E4) + Routine (E2) renders from a real DB fixture; portrait, deviceScaleFactor 2, BOTH themes, at 320×844, 390×844, 800×1280, plus 390×844 @125% text. No landscape.
- **Automated per-frame assertions (shoot_rev.js): ALL 24 OK** — overflow-free; exactly one page-title and one clock (no duplicate title/date/refresh); Home shows exactly one mode-matched wordmark (loaded), title hidden on phone / visible on tablet, no Refresh; Routine shows the in-header Refresh (48×48) and no wordmark; the bottom-nav badge is the green --ok family (dark rgb(140,224,180) / light rgb(20,102,58)).

## Requirement → evidence

| codex/0008 | Where | Frames |
|---|---|---|
| §1 title "Today"→"Home" (title/heading/AT), internal 'today' kept | home.php $pageTitle='Home'; layout_top h1 | e1/e4 tablet (visible "Home"), e1/e4 phone (clipped, AT-only) |
| §1 phone: title hidden, wordmark centred own row ~232px clamped, date/time box beneath | style.css .page-today grid; --lc-wm-w=min(232px,100%) | e1/e4 320 + 390 (+125%) |
| §1 tablet: wordmark left, Home title + date/time box right cluster, clamp balance | style.css .page-today @700 grid | e1/e4 800 |
| §1 store-local date+time, one spoken value, LC_TZ/minute updates | lc_shell_date_block, data-lc-clock, sr-only spoken | all e1/e4 |
| §2 Routine header 1fr auto 1fr: title · centred clock · Refresh, one line @320 & @125% | style.css .topbar-has-refresh; layout_top topbar-refresh | e2 320, 390, 390@125% |
| §2 Refresh contract (48×48, focus, GET link, aria, no dup, messages below) | layout_top + freshness.php ($lcTopbarRefresh) + app.js doc-scope | e2 all (refresh=1) |
| §3 green actionable counts (nav badge, section counts, picker counts) | style.css .nav-badge/.segment-count/.tasks-picker-count → --ok/--on-ok | e2 (Side Work/Tasks green), all (green bottom-nav badge) |

## Positive frames
| Surface | 320 | 390 | 800 | 390@125% |
|---|---|---|---|---|
| E1 staff Home | dark+light | dark+light | dark+light | dark+light |
| E2 Routine | dark+light | dark+light | dark+light | dark+light |
| E4 manager Home | dark+light | dark+light | dark+light | dark+light |

## Verification
- Full battery **81 PASS / 0 FAIL / 0 SKIP** (incl. design-token, CSS class coverage, static accessibility incl. no colour-only status, PWA static boundary, page-title R-30/R-36, terminology, Chromium responsive/offline PWA).
- Deterministic MANIFEST-SHA256.txt refreshed in-commit; web-doc.zip unchanged (no Brand/ change); no site/tools or toolset/tools change.
- Served light/dark wordmark SVGs remain byte-identical to the official Brand Guide v3 assets (unchanged this revision).

## Frame hashes (sha256)
```
04ab48de5d680309400354fecb2dc6842d71abdd3f8e4f58bbb89b054a69340a  e1_320x844_dark.png
0cdfe52fe43733cbb789478063898a22ff179a39a0ae6bcba8b57effee8decd3  e1_390x844_dark_125.png
15ad480ff64847f7726e996bb261efc109585ab267e3de827304463eb6d3b2df  e4_800x1280_dark.png
15be476794096d52f6841d5295b7d232d223488a005ec6be060af4b99cb8720f  e2_800x1280_light.png
192899ce9303b5898f3f597c88ace29470011cd64e023597bfb97a7bc8cd50b1  e2_320x844_dark.png
2b9ae2d75c772db4dc64c6f9f9fa505b9f6f99a3075c63bf75f7752427567fd3  e4_390x844_dark_125.png
2d5739883b13440b63db6ff50d34a27ad795797231cba1c4d6fcc745b7069da9  e1_390x844_light_125.png
33f7e70f8eb8149d532054f7d0254e4539942acc76aa5ad6db266f0d7188817b  e4_320x844_dark.png
36b3b23c69061a09d2b1e5523fda32f89cdce991cb4de9de0496f839ea47672f  e2_390x844_dark_125.png
5ce8501310a6426df18f00e0c9b1a06a07360c80f945801417c3f35aa4bec95d  e4_390x844_light_125.png
7ed7a8eb03bbb5f4e11854327379e747a42c0c805d464f7d91eeb83aadda5ebd  e4_390x844_dark.png
95701cc86ea29a8c47ce55c8b2272df1b7ffff77dcd3ce00e526d5696a4cfe0c  e4_320x844_light.png
a97324f86f9c54bac9d294ae0ce92d5a08ae5034a36f4043e90b76147488abde  e1_390x844_dark.png
a9fdfed5c9df67eb3a24dd668ce6e8caef0461e82164d2e487552349e22ecc80  e2_390x844_light_125.png
b4710d2ffe98735939906f229e49dbe906eb8062b0895f1dca76a1bd71cd6f40  e1_320x844_light.png
bdba887af96bfe57502edb89495610eac568604cfd28793eeecd7aaca00b85c8  e2_800x1280_dark.png
d7cf7c8fc648cc2e77b4b375be9c15e0334668c89fb7b6d5ff04ac5faa9e1ef9  e1_800x1280_dark.png
dcea933b7755aade5ffcf51bae80ad6a45283a992d732dcae314cfe2cb722da3  e2_320x844_light.png
e04af513f6ab28adfb1d705a9426fd3fde58641600ad3bdf146a61f84c05c884  e2_390x844_light.png
e2b90f5f37627a45a6e635f2177858dc97272c696eacf8ff9eae13d16313c934  e4_390x844_light.png
e4f63cca98d0dc38fb19441fc8db869d0175f2719b419f82f122d2d37c0c2607  e4_800x1280_light.png
eb37e883b0d111dcd79e36a29ecba4a93c4100fa051104cb37fddd709b7c5961  e1_800x1280_light.png
ebe4f4a47bccc94374e26f6e18302932a34bdfcdf1c421abd81845d81c242a0d  e1_390x844_light.png
f0cc3e39e0030e655b19113536249775f8c6519c19af6c8a155506037e9063f4  e2_390x844_dark.png
```
