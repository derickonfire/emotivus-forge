# Forge 0.571 certification

Forge is certified for **545 focused public-neutral regressions** across 57 deterministic isolated modules; the certified suite grows additively, as 0.571 adds verified replacement invariants: a component replace can declare structured invariant checks (a scoped-Check subject and required truth-state) that Forge verifies against the actual Check truth records, reporting each preserved or violated. One regression was added; no existing behavior test was changed or removed. Goal 1 remains COMPLETE; release authorization remains false.

Final certification must execute from source, standalone public bytes, development-edition bytes, and the website-embedded runtime. It does not establish owner authorization, release readiness, independent review, physical-device evidence, or product efficacy.
