# Spectrum batch 1 — 15 projects on Forge 0.557

15 parallel agents ran Forge cold on 7 real repos (Python/JS/Go/Rust/PHP/Ruby/Java)
and 8 synthetic scenarios, grading usefulness for pro- vs vibe-coders and recording
the single most valuable missing capability per case.

## Confirmed wins (the 0.556–0.557 work holds)

- **Objective detection: 5/5 present → 5/5 detected** — including a `## Goal`
  heading. The 0.557 fix generalizes.
- **Blocked-before-value: 0/15.** The orient-before-blocking change holds
  everywhere.
- **Architecture understanding: 11 partial, 3 good, 1 shallow** (was 0 above
  shallow before the layout summary).
- **Secrets: 2/3 caught-all, 1 partial** (see the .npmrc gap below).
- **Token economics line present on all; no crashes on any of the 15.**

Mean usefulness: **pro-coder 2.07, vibe-coder 2.40** (separate scales, tough
graders). The ceiling is ~3 because of one dominant, systemic gap.

## The dominant finding: ecosystem coverage is incomplete and mis-dispatches

Almost every miss traces to `orientation.derive_orientation`'s hardcoded, strict
if/elif language dispatch and its shallow per-ecosystem knowledge:

| Project | Bug |
|---|---|
| laravel (PHP+Vite) | `run="npm run dev"` (WRONG — should be `php artisan serve`); `test=""` despite composer `test`; `primary_source_dir="config"`; description truncated mid-word. Cause: has `package.json`, so the **node branch wins** over PHP. |
| commons-cli (Java) | identity `"proj"` (pom.xml `artifactId` unread); description grabbed the Apache license header; no `mvn` build/test; false stacks (css/html/js). |
| sinatra (Ruby) | no run/test/entry; `primary_source_dir` hallucinated as a vendored sub-lib; objective taken from a sub-README `Goals` heading; description ends with a stray colon. |
| slugify (JS) | `tests count = 0` despite a 257-line root `test.js` (test discovery only scans a `tests/` dir). |
| hey (Go) | `entry_points=[]` though `hey.go` has `func main()`; `primary_source_dir="requester"` (helper pkg, not the main package). |
| anyhow (Rust) | lib crate should suggest `cargo test`/`cargo doc`, not a bare build. |
| static cafe | description empty and identity `"proj"` despite `<title>Little Luna Cafe</title>`. |
| calc | `check` reported 1 changed path but resume then says `0 path(s)`; spurious migration WARNING on a pure-python toy. |
| secrets-everywhere | `.npmrc` `_authToken=` planted secret **missed**. |
| tiny-thing (empty) | heavy sidecar + `self_currency WARN` on a 2-line project. |

## Roadmap implication (strong, specific)

**Build a real language/ecosystem resolver.** The agents independently converged on
this: a per-ecosystem module that, for Python/JS/TS/Go/Rust/Java/Ruby/PHP, knows the
identity source (pyproject/package.json/go.mod/Cargo.toml/pom.xml/gemspec/composer),
the canonical run + test commands, entry-point discovery, and test-file globs — and
that **ranks the primary language** so a polyglot/framework project (Laravel, a
Java repo with a JS asset pipeline) isn't mis-dispatched.

Note: Forge already ships an `adapters/` directory (`python.json`, `node.json`,
`php.json`, `javascript.json`, `apache.json`, `css.json`) from the original design.
The resolver should be **data-driven from those adapters** rather than the current
hardcoded if/elif — reviving intent that already exists.

Secondary, cheap wins the batch argues for:
- Test discovery beyond `tests/`: root `test.js`, `*_test.go`, `*.spec.*`.
- Entry-point discovery for libraries + `main`-function scan (Go/Rust/Python).
- `.npmrc`/`.pypirc`/`.netrc`/`.dockercfg` credential rules.
- Description hygiene: skip license headers, don't truncate mid-word, strip trailing punctuation.
- Empty/stub-project detector: suppress sidecar ceremony + the `WARN`.
- Static-site broken-local-reference resolver; `<title>` as an identity fallback.
- Notebook/data-science recognizer (requirements + `*.ipynb` → jupyter run).
- The `check`→resume "0 paths" contradiction and the spurious migration WARNING.

*Data source: `scratchpad/spectrum50/*`; workflow batch 1 (15 agents).*
