# PC-C1 Management Hubs standing-gate exact-head review request

- Stable id: `LC-OPS-CONSOLIDATION/codex/0029`
- Attention event: `ATTN/codex/0012`
- Product PR: `derickonfire/linecheck-acceptance#31`
- Exact base: `dff5d0139f2aa1319e10289805abdeae2fafc71d`
- Exact head: `7ce38fcb97c7ef50a5cc153932ea1c2ca9a3e3c6`
- State: `PENDING_INDEPENDENT_REVIEW_AND_WORKFLOWS`

This bounded PC-C1 slice wires the already-shipped, mirrored Management Hubs authorization checker into both canonical runners. It also corrects the checker’s stale build-label text, updates the canonical check-group fact/table (including the previously uncatalogued CSS class group), and refreshes exact manifest hashes. It makes no product-runtime, schema, migration, archive, release, or deployment change.

## Evidence

- clean site checker: `PASS — 17 assertions, 0 failures`;
- mirrored toolset checker against the same site root: `PASS — 17 assertions, 0 failures`;
- deliberate negative fixture removing `shift.create` from the Build navigation gate: exit `1`, exact failure `Build nav gate must match child permissions`;
- exact registration count: one invocation in each runner;
- site/toolset checkers byte-identical; site/toolset runners byte-identical;
- canonical document facts: 4 declared facts across 243 live documents agree with code;
- staged Git-byte manifest: all 853 entries exact;
- integrated `--fast`: Management Hubs PASS, documentation facts PASS, overall `69 PASS / 9 FAIL / 4 SKIP`.

The nine failures and four skips are inherited current-main/environment conditions. This slice introduces no new failing group. Both standard GitHub workflows must complete at the exact head before acceptance.

Claude should independently review PR #31 at exact head `7ce38fcb97c7ef50a5cc153932ea1c2ca9a3e3c6`, verify the runner placement, mirror parity, fail-closed negative proof, fact reconciliation, exact manifest, base relationship and workflows, then return an immutable acknowledgement naming `ATTN/codex/0012` or bounded gaps. The PR remains draft and unmerged; a distinct exact-head owner merge authorization remains required.