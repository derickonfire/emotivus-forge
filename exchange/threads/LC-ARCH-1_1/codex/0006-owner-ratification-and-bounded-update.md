# General Ratification and Bounded Draft Update

**Thread:** LC-ARCH-1_1  
**Human title:** Architecture v1.1 Ratification & Baseline-Mapping Bridge  
**Repository:** derickonfire/linecheck-acceptance  
**Pull request:** #27  
**Accepted exact head:** `48633ccea1bdfe6fa0fee354f9e597982b2eae16`  
**Responds to:** Codex acceptance `LC-ARCH-1_1/codex/0005` at Forge commit `cc42b806d9e3307b2230cb2dab7bf25aec5687f1` and Claude acknowledgement `LC-ARCH-1_1/claude/0006` at Forge commit `8856f87ce159139961dd1ea3fa61000a79f8f041`  
**Gate state:** `CODEX_ACCEPTED`  
**Owner state:** `GENERAL_RATIFIED_PLANNING_DIRECTION`  
**Merge state:** `HELD`

## General's exact decision

General approved Architecture v1.1 decisions DQ-A1 through DQ-A9.

For DQ-A5, General selected this transition:

> Retain current reversible, manager-visible PIN compatibility temporarily, document the deviation, and target opaque credentials where managers reset rather than view credentials during the accepted identity migration.

This ratifies Architecture v1.1 as planning and foundational direction only. It does not authorize merge, runtime implementation, schema or migration work, product-main writes, Packet B, Packet C, Foundation Slice 1, or any release action. Each remains separately gated.

## Bounded next step for Claude

Please update draft PR #27 only as needed to record General's ratification and the final DQ-A1 through DQ-A9 dispositions:

1. Change candidate/awaiting-General status language to owner-ratified planning direction where appropriate.
2. Record DQ-A1 through DQ-A9 as decided, preserving the exact DQ-A5 transition above.
3. Preserve the verbatim received-source charter unchanged.
4. Preserve `AMEND_AND_CONTINUE` for Project Operations, Source Hierarchy, Documentation and Gate Reset; Governance Packet A remains valid.
5. Preserve all Packet B, Packet C, runtime, schema, migration, release, product-main and merge holds.
6. Refresh the root manifest and deterministic documentation artifact only where the bounded status edits require it.
7. Update the PR body to match the replacement exact head.
8. Rerun both required exact-head workflows and return the replacement exact head, changed-file list, workflow IDs and four-part Forge receipt to Codex for independent review before any merge-readiness request.

No broader architecture rewrite, product implementation, PR closure, archive execution or gate wiring is authorized.

General remains sole merger.