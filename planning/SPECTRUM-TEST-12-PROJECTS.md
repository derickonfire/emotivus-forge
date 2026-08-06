# Broad-spectrum field test — Forge 0.555 on 12 projects

Twelve parallel agents ran Forge cold on a deliberately broad spectrum: five real
Git repos (Python `click`, JS `slugify`, Go `hey`, Rust `anyhow`, PHP
`laravel/laravel`) and seven synthetic scenarios (vibe-coded slop with a planted
secret, a secrets stress repo, a monorepo, a near-empty project, the full
objective→change→Check lifecycle, a data-science layout, a static site). Each
graded Forge honestly against one bar: on first contact, does it tell a cold model
**what** the project is, **how** it's built, **how** to run/test it, and **what**
to watch for.

## Aggregate

| Signal | Result |
|---|---|
| Ran without crashing | **12 / 12** |
| Mean usefulness for a cold model | **1.83 / 5** (ten 2s, two 1s) |
| Architecture understanding above "shallow" | **0 / 12** |
| Objective detected | **0 / 12** — including a case with an explicit `## Objective` heading |
| Blocked on "confirm your objective" before value | **11 / 12** |
| Change detection (where tested) | **worked** (1/1) |
| Planted secrets caught | **1 of 2 partially; the hardcoded-key case fully missed** |

## What genuinely works (the stable base)

- **Robustness.** 12/12 ran in 16–137 ms with zero crashes across five languages
  and every degenerate case (1-file project, binary blobs, broken links). Forge is
  a solid, non-crashing foundation — these are fixable gaps, not a rewrite.
- **Identity from a manifest.** Correct name + source fingerprint from
  `pyproject.toml`, `package.json`, `composer.json`.
- **Stack detection** across Python/JS/TS/Go/Rust/PHP/CSS/HTML.
- **Change detection actually works** (calc case): after editing a file,
  `forge check .` reported "1 path changed", scoped it, and ran real sub-checks
  (python-syntax, merge-marker). The pro-coder Check flow is real.
- **No false BLOCK alarms** on healthy repos; screening never stores secret values.
- **Honest self-limiting language** throughout.

## Critical defects (concrete, fixable)

### D1 — Secret screening reads zero bytes of ordinary source at orientation *(headline)*
A full content scanner **exists** (`secret_screening.screen_text`) and runs across
every file at **package/Ship time** (`build_forge_package.py:205-214`). But the
Run Forge orientation pass (`confidentiality_boundary.py:76,105`) only content-
scans files it *already* flagged by filename and path-screens the rest. Result:
- **Vibe-slop case: a hardcoded `OPENAI_API_KEY="sk-proj-…"` in `app.py` was
  missed entirely** — `files_examined:0`, `mode:metadata-only`. This is the #1
  target-user scenario (a non-expert ships AI code with a hardcoded key), and
  Forge's advertised "secret screening" gave it a clean pass.
- **Fix (high value, low cost):** wire the existing packaging-grade content scan
  into orientation, bounded by size/count. The capability is already written.

### D2 — Even filename-triggered screening is incomplete
Secrets stress case: caught `id_rsa` as **BLOCK** and `.env` inline creds (real
wins), but **missed `aws-credentials` (AKIA… key) and `config.json` (api_token)
entirely** (only 2 of 5 files examined), and **downgraded live `sk_live_…` and
`DB_PASSWORD` to "placeholder" (INFORMATIONAL)**. Non-standard credential
filenames and live-secret shapes need coverage.

### D3 — No orientation (universal)
On all 12, Forge never says what the project *is*, its layout/entry points, or how
to run/test it — even when `README`, `Makefile`, `pyproject`, `phpunit.xml`,
`go test`, `npm test` are right there. It emits labels (name + stack), not
understanding.

### D4 — Objective detection is broken
The calc case handed Forge an explicit `## Objective` heading in `ROADMAP.md`;
Forge reported `objective.text=""`, `status=unknown`, and made "objective not
confirmed" its top blocker. The one signal handed to it on a plate was ignored.

### D5 — Identity falls back to the directory name without a recognized manifest
`hey` (Go) was named **"proj"** (the temp dir) — `go.mod`'s
`github.com/rakyll/hey` was never read. The near-empty project was named "proj"
too — the `# my-thing` README H1 was ignored. Identity needs a fallback chain:
manifest → `go.mod`/`Cargo.toml` → README H1 → dir name last.

### D6 — Friction on healthy projects
11/12 lead with "Stop before changing the project — confirm your objective" before
offering any orientation, and `self_currency` reports **WARN** on pristine
clones — a false alarm.

## Product implication (sharpens the observed miss)

The Flask finding generalizes: Forge is a robust governance shell with thin
project intelligence and a **safety feature that doesn't fire where it matters
most**. The highest-leverage fixes, in order:

1. **Wire the existing content secret scanner into Run Forge orientation** (D1/D2).
   Cheapest, highest-value change — turns the biggest failure into a killer
   feature for the primary user, using code that already exists.
2. **Add a first-contact orientation** (D3): what / layout+entry points / run+test
   commands, read from the project.
3. **Fix identity fallback** (D5) and **fix or drop objective-blocking** (D4/D6):
   orient first, ask for an objective only when about to change files.

Change detection and robustness are assets to build on, not fix.

*Reproduction: each case cloned/created under
`scratchpad/spectrum/<n>-<slug>/proj` and run with `python3 forge.py`.*
