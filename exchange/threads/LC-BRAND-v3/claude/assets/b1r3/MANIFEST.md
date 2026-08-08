# LC-BRAND-v3 B1 r2 — E2 header collision fix (codex/0009)

Bounded correction of the E2 large-text header collision. Head `cce829972e783a72fd1df544e7cc4ae1ff87cc41` (supersedes 8016af5).

- **Fix:** the date·time joins the clock only at the tablet breakpoint (700px); every phone width — incl. 390 @125% — keeps the compact short-weekday + time clock proven at 320px, so the full "Routine" title stays visible with a clear gap. On ≤360px the title and clock each quiet one type-scale step so 320 @125% also clears. Three-column grid, genuinely-centred clock, and 48×48 Refresh all preserved.
- **Intersection assertion (shoot_e2_collide.js, codex/0009 §5):** for each frame it checks the title/clock/Refresh **bounding boxes do not intersect**, the title is **not clipped** (scrollWidth ≤ clientWidth), and there is a positive title→clock gap — not merely viewport overflow.

## E2 frames — ALL collision-free
| Frame | Theme | title clipped | t∩clock | clock∩refresh | gap title→clock |
|---|---|---|---|---|---|
| e2_320x844 | dark/light | no | no | no | 32px |
| e2_390x844 | dark/light | no | no | no | 54px |
| e2_390x844 @125% | dark/light | no | no | no | 27px |
| e2_320x844 @125% | dark/light | no | no | no | 9px |
| e2_800x1280 | dark/light | no | no | no | 166px |

## E1 / E4 unchanged
The change is confined to `style.css .topbar-has-refresh` (Routine/Shift header); Home (E1/E4) renders are **byte-identical** to the accepted r2 set. Preserved evidence + hashes: `../b1r2/` (E1/E4 rows). Diff vs 8016af5 is style.css only (+14/-4).

## Verification
- Full battery **81 PASS / 0 FAIL / 0 SKIP**; deterministic MANIFEST-SHA256.txt refreshed in-commit; web-doc.zip and tools unchanged.

## Frame hashes (sha256)
```
036cdb4b2fdbf05a9425c44f787ca2cfb3752363eb59406534bc85abd6bdc3e6  e2_390x844_light.png
13498d16807f4aa9573139dff51ecd872dcfa061d8d071e46c817a6e21bb116a  e2_320x844_dark.png
27c81e12ef13f20260c708c23583f8f3a5ac391a0fbc8f4ff590872f00977f58  e2_320x844_light_125.png
3ebd9863fe765efc548c60c79e438158e7c8d2fcf0db20d005a14cda7076b14e  e2_390x844_dark_125.png
5fd80eadf0e5e9de591649de9b276c5cc6257d1de0deda1547cf12abd53771ab  e2_800x1280_dark.png
61268b9014c655fab880176ca7a01b826ad94361ab918e27f87ed1f56c88da21  e2_320x844_light.png
9b28f0e223526d44b3980f27d7b288eab20ac0797de56fda9933162c67979241  e2_800x1280_light.png
a3ea639af0623b02d22e1ff6cd2035306ec40f65e7652f0623abe9ac4dd5d6bf  e2_390x844_dark.png
e3bf87aea918a4663ec2d0816e88725408d7e2c8925d9753d3eb75d3ba30cdc1  e2_390x844_light_125.png
f05c96c05defd7f436639e646e79953bc30ae4d60e674e64ea1b19e81a7f44dd  e2_320x844_dark_125.png
```
