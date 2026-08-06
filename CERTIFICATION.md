# Forge 0.563 certification

Forge is certified for **531 focused public-neutral regressions** across 55 deterministic isolated modules; the certified suite grows additively, as 0.563 completes multi-party instance-binding: an owner-provisioned shared collaboration secret, held out-of-band in each trusted party's Forge home, makes authorizations mutually instance-bound across enrolled parties, while a party without the secret sees only self-consistent (never release-eligible). One regression was added; no existing behavior test was changed or removed.

Final certification must execute from source, standalone public bytes, development-edition bytes, and the website-embedded runtime. It does not establish owner authorization, release readiness, independent review, physical-device evidence, or product efficacy.
