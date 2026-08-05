# YesMem Secret-Pattern Adaptation — Working Findings

Status: recorded before correction in the post-0.542 working tree. This file is not a release authorization.

## F-0543-01 — contradictory roadmap average

The sealed 0.542 session state reports axis values 90 / 100 / 96 / 88 / 99 / 58 / 76 and an audited average of 86.7%, approximately 87%. The packaged source `ROADMAP.md`, `README.md`, `planning/README.md`, and website accuracy record still say approximately 85%. The axis values and prose therefore disagree.

Correction boundary: regenerate current narrative values from the canonical seven axes. Do not rewrite historical changelog statements that accurately describe older builds.

## F-0543-02 — intake contract points to retired Forge paths

`research/YESMEM-2.3.5-INTAKE.json` declares the planned secret adaptation against `emotivus_forge/core/confidentiality.py` and `tests/test_confidentiality_screening.py`, but the 0.542 implementation uses `emotivus_forge/core/secret_screening.py` and `tests/test_secret_screening.py`.

Correction boundary: bind the implemented candidate to the actual public files and neutral regressions, then re-run exact Third-Party Capability Intake against the sealed upstream archive.

## F-0543-03 — selected upstream shapes not represented faithfully

The current Forge screener already covers AWS access IDs, generic provider tokens, JWT-like values, bearer headers, URL credentials, and private-key headers, but it misses or under-specifies several selected reviewed vectors: Anthropic keys, modern OpenAI prefixes, exact GitHub PAT length, AWS secret keys in JSON, ordinary JWT second segments, standalone bearer tokens, and PGP private-key block headers.

Correction boundary: add report-only BLOCK/REVIEW/INFORMATIONAL classifications without retaining values or mutating bytes. Reject upstream email, phone, public-IPv4, and arbitrary 32–128 hex patterns from Forge defaults because they would create disproportionate false positives and would classify ordinary contact data, documentation IPs, and SHA-256 evidence as secrets.
## F-0543-04 — detector matched its own literal rule source

The first focused adaptation run failed `test_forge_source_tree_screens_clean_under_packaged_policy`: the exact PGP private-key header appeared contiguously inside the new regex source and the scanner correctly treated its own module as BLOCK.

Correction boundary: represent the same compiled regex through adjacent source literals so real input still matches while the detector implementation does not contain the complete secret marker as scan text. Do not exempt the engine source or weaken the actual rule.

