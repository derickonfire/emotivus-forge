# Forge 0.562 certification

Forge is certified for **530 focused public-neutral regressions** across 55 deterministic isolated modules; the certified suite grows additively, as 0.562 begins cryptographic instance-binding: authority-baseline authorizations are signed with a per-instance key stored outside any project tree, and corroboration is tri-state — only an authorization signed by a key this instance trusts is instance-bound and release-eligible, so an imported package cannot spoof in-instance authority. One regression was added; no existing behavior test was changed or removed.

Final certification must execute from source, standalone public bytes, development-edition bytes, and the website-embedded runtime. It does not establish owner authorization, release readiness, independent review, physical-device evidence, or product efficacy.
