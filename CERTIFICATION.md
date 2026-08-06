# Forge 0.564 certification

Forge is certified for **532 focused public-neutral regressions** across 55 deterministic isolated modules; the certified suite grows additively, as 0.564 extends instance-binding to artifact provenance: a recorded deliverable lineage is a signed event, and the scoped Check asserts CONFIRMED only when that event is instance-bound, so a byte-matching but unsigned or imported provenance record is honest as current yet not asserted as authenticated provenance. One regression was added; no existing behavior test was changed or removed.

Final certification must execute from source, standalone public bytes, development-edition bytes, and the website-embedded runtime. It does not establish owner authorization, release readiness, independent review, physical-device evidence, or product efficacy.
