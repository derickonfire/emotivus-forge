# Forge 0.567 certification

Forge is certified for **536 focused public-neutral regressions** across 56 deterministic isolated modules; the certified suite grows additively, as 0.567 opens the Goal-3 cross-model evolution work: forward migration is guaranteed to preserve unknown top-level and nested fields verbatim, and Forge reports preserved-but-unrecognized fields rather than interpreting or dropping them. One deterministic isolated module and its regressions were added; no existing behavior test was changed or removed. Goal 1 remains COMPLETE; release authorization remains false.

Final certification must execute from source, standalone public bytes, development-edition bytes, and the website-embedded runtime. It does not establish owner authorization, release readiness, independent review, physical-device evidence, or product efficacy.
