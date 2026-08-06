# Forge 0.561 certification

Forge is certified for **529 focused public-neutral regressions** across 55 deterministic isolated modules; the certified suite grows additively, as 0.561 adds a genuine read-only consultation mode (`run --read-only`, `resume --read-only`) that reads a project's real bytes and prior state but writes nothing into the project tree — its state directory is redirected to a disposable location outside the project and discarded. Six regressions and one deterministic isolated module were added; no existing behavior test was changed or removed.

Final certification must execute from source, standalone public bytes, development-edition bytes, and the website-embedded runtime. It does not establish owner authorization, release readiness, independent review, physical-device evidence, or product efficacy.
