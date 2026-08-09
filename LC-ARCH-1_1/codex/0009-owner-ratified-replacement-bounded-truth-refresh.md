# LC-ARCH-1_1/codex/0009 — owner-ratified replacement held for bounded truth refresh

**Thread:** LC-ARCH-1_1  
**Human title:** Architecture v1.1 Ratification & Baseline Mapping  
**Product PR:** derickonfire/linecheck-acceptance#27  
**Reviewed exact head:** `f6c1e4e27dc5a235814e42ca7d95195f0b5d0806`  
**Current product main/base:** `0f12b0de1362292f338e34ca2835c9cc2a20369e`  
**GitHub review:** `4891354017`  
**State:** `CODEX_HELD` — bounded documentation/receipt corrections only  
**Authority:** General's DQ-A1 through DQ-A9 planning-direction ratification is accepted and recorded. Merge, Packet B, Packet C, runtime, schema, migration, release, and product-main actions remain separately held.

## Review outcome

The architectural content is sound:

- DQ-A1 through DQ-A9 are represented, including the owner-ratified DQ-A5 transition.
- The verbatim received-source charter is unchanged (same blob identity).
- The effective diff remains planning/governance only and is based on current main.
- AMEND_AND_CONTINUE remains correct; LC-OPS does not restart.
- Both standard workflows are green on the reviewed exact head.
- PR #27 remains draft.

## Bounded replacement required

1. Refresh the PR body: it still names `main@1780e3b`, head `48633cc`, unratified/candidate status, queued owner decisions, old workflow evidence, and the prior manifest count. Bind it to current base/head, ratified planning status, current exact-head runs, and refreshed deterministic counts.
2. Refresh `Planning/ARCHITECTURE/README.md` and `BASELINE-GAP-MAP-v1_1.md`: both still call `1780e3b` current main.
3. Resolve DQ-A5 throughout `WORKFORCE-CREDENTIAL-MODEL-v1_1.md`: §2.3 still says the issue is undecided. State the ratified transition exactly—temporarily retain and document reversible manager-visible PIN compatibility, then move to opaque credentials whose managers reset rather than view during the accepted identity migration—and align held-test wording.
4. Sweep remaining ratification-state prose such as “proposed,” “after ratification,” “candidate,” and owner-decision-pending. Preserve all separate execution and merge holds.

Refresh deterministic artifacts, run the full battery and both standard exact-head workflows, update the PR body, and return one replacement exact head with a four-part receipt binding:

- exact product head,
- GitHub review/result,
- Forge message,
- state token.

Do not begin Packet B, Packet C, runtime work, or merge. Return to Codex first.
