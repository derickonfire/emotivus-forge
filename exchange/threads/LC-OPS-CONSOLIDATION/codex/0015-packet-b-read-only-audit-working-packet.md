# Project Operations, Source Hierarchy, Documentation and Gate Reset — Packet B read-only audit working packet

- Thread: LC-OPS-CONSOLIDATION
- In reply to: LC-OPS-CONSOLIDATION/codex/0014
- Task Owner: Codex
- Independent Reviewer: Claude
- General: sole arbiter and merger
- State: planning-only working paper; independent review requested
- Product writes, runtime, schema, migration, archive/delete/move, PR closure, Packet C, release and merge authority: not granted

## 1. Exact evidence boundary

Current product main is 0f12b0de1362292f338e34ca2835c9cc2a20369e.

Architecture v1.1 Ratification and Baseline Mapping (PR #27, LC-ARCH-1_1) is a CODEX_ACCEPTED, open draft overlay at 46398718cf439a18064641f4e1728e630f8e6943. Current main is its exact ancestor. The overlay adds twelve planning artifacts plus the refreshed manifest; it does not change runtime, schema or release gates. This paper keeps current main and the accepted-unmerged overlay separate.

Project Operations Governance Packet A (PR #26, LC-OPS-CONSOLIDATION) merged as 1780e3ba3d2144eaccedb6cf49d1a38e4ce8a995. The exact merge receipt LC-OPS-CONSOLIDATION/claude/0010 at Forge commit 9c5fdaa records: “General ratified Project Operations Governance Packet A and authorized merge.” Therefore AI Operating Agreement v0.3 ratification is confirmed. Candidate/draft/not-ratified labels remaining in merged documents are stale metadata corrections, not a new owner decision.

No assertion in this working paper authorizes a product branch, product PR, product-main write, archive action, PR closure or gate wiring.

## 2. Controlled Multi-Agent receipts

| Worker | Bounded scope | Sources | Outcome | Mutation check |
|---|---|---|---|---|
| /root/packet_b_sources | W1 Documentation Source and Dependency Graph plus W2 Exact-Source Product Hierarchy | Current main and accepted-unmerged Architecture overlay | Used after Codex reconciliation | No files, branches, comments or PR state changed |
| /root/packet_b_gates | W3 Gate Coverage Matrix | Current runners, workflows, nine target checkers, manifest/toolset mirrors and historical Packet A evidence | Used after settings-structure evidence correction | No files, branches, comments or PR state changed |
| /root/packet_b_archive | W4 archive classifications plus W5 amendment/health ledger | Current governance docs, live PR state, historical branches and accepted-unmerged Architecture overlay | Used after Codex removed the false “v0.3 ratification open” item | No files, branches, comments or PR state changed |

One integrator rule held. Workers performed read-only research and did not post formal reviews or create authority.

## 3. W1 — documentation truth layers and dependency graph

Packet B must preserve four different truth layers:

1. Accepted release truth: Release/RELEASE-STATE.json and Release/START-HERE.md. The accepted release is 0.19.176+r3 from source commit 50bc5a… and schema 72. This intentionally differs from current-main development source version 0.19.176 and schema 74.
2. Current-main source truth: exact implementation, navigation, registry, module configuration, workflows and checkers at 0f12b0d.
3. Current governance truth: Planning/PROJECT.md, Authority Index, Active Work Register, AI/communication/monitoring contracts and roadmap documents, with stale operational metadata corrected through an amendment ledger.
4. Accepted-unmerged architecture direction: Architecture v1.1 at 4639871, owner-ratified planning direction only until separately merged; not release truth, runtime authority or build-order authority.

Condensed dependency graph:

Accepted release state
  -> release reading and verification documents
  -> web-doc builder and web-doc.zip
  -> release/package consistency checks

PROJECT + Authority Index + Active Work + roadmaps
  -> current governance and planning interpretation

Architecture received charter
  -> Constitution, placement, gap, migration and decision artifacts
  -> future Authority Index amendment after Architecture merge
  -> Packet B current-truth amendment ledger

Brand Guide v3 source
  -> runtime brand mirrors
  -> web-doc package

Selected repository surfaces
  -> complete-package builder
  -> manifest and integrity artifacts

Confirmed documentation drift:

- Planning/AUTHORITY-INDEX.md still treats Credit and Recognition Economy Planning (former PR #23) and the Living LineCheck Icon Register (former PR #18) as candidate-only although both are ancestors of current main.
- Planning/ACTIVE-WORK-REGISTER.md retains a stale base, PR inventory and run.php writer statement.
- AI Operating Agreement v0.3, Communication Contract and Monitoring Contract retain candidate/draft headers even though Project Operations Governance Packet A (PR #26) was ratified and merged.
- Planning/ROADMAP-ORDER.md and Planning/POST-ROUTINE-HIERARCHY-SEQUENCE.md remain conflicting active roadmap layers pending the Canonical Product Roadmap (PR #25).
- Brand/ASSET-REGISTER.md still says Home and Routine Brand/Progress Polish Phase B1 is not wired even though that work merged.
- Architecture v1.1 documents are manifest-bound but absent from build_web_doc.py’s static Planning selection.
- Current reference checks prove path/hash/package consistency, not prose accuracy against current GitHub and Forge state.

Historical UX/VUX maps remain evidence snapshots, not current exact-source authority. Planning/MAP-VERIFICATION-2026-08-02.md must be preserved verbatim because its original body and later corrective addendum intentionally record different run.php conclusions.

## 4. W2 — exact-source product hierarchy

| Stable ID | Human surface | Current exact owner | Responsibility |
|---|---|---|---|
| UX-SHELL-HOME | Home | site/app/nav.php | Top-level destination and route ownership |
| UX-SHELL-ROUTINE | Routine | site/app/nav.php | Routine, work, instance, run, checklist, cleaning, corrective and follow-up routes |
| UX-SHELL-LEARN | Learn | site/app/nav.php | Learning, training, content, quiz, skills and paths |
| UX-SHELL-SHIFT | Shift | site/app/nav.php | Shift, announcements, logbook, handoff and acknowledgements |
| UX-SHELL-MORE | More | site/app/nav.php | Help, published schedule, contacts, stocking, profile, history and settings |
| UX-MGR-MANAGE | Manager — Manage | site/app/nav.php | Command, reviews, prior day, backfills, assignments and reports |
| UX-MGR-BUILD | Manager — Build | site/app/nav.php | Builder, templates, starters, content and announcements |
| UX-MGR-ADMIN | Manager — Admin | site/app/nav.php | Team/users, devices, setup/settings, operations, preview and audit |
| SRC-DOMAIN-REGISTRY | Domain/action/entity taxonomy | site/app/registry.php | Internal domain keys, actions, entities and permissions |
| SRC-MODULE-CONFIG | Installation module configuration | site/app/opsdb.php | Per-installation labels, ordering and enable/disable state |
| SRC-SHELL-RENDER | Responsive shell renderer | site/partials/layout_top.php and layout_bottom.php | Rendering under route ownership and authorization |
| SRC-AUTH-GATE | Manager visibility | nav.php and layout partials | Personal manager-session ceiling |

These are complementary authorities. Packet B must document their interfaces rather than declaring one file the universal hierarchy source.

Confirmed hierarchy gaps requiring later classification:

- Internal registry key/label work/Work versus user-facing Routine appears intentional but should be explicit.
- settings.php maps to More while Settings also appears under Manager Admin.
- eightysix.php behaves as Shift but lacks an explicit route-owner mapping.
- Architecture v1.1 confirms instance.php as the occurrence-engine completion-event writer. run.php is a live read-only legacy/history surface; only its unreachable mutation block is dead.

## 5. W3 — gate coverage matrix

All nine target tools are byte-identical between site/tools and toolset/tools, manifest-bound, and unchanged by Architecture v1.1 Ratification and Baseline Mapping (PR #27). Manifest identity is not behavior proof.

| Stable ID | Exact tool | Classification | Current evidence |
|---|---|---|---|
| PB-W3-BHV-01-MANAGEMENT-HUBS | check_management_hubs.php | Partial; required gate uncovered | Static authorization checker exists but is absent from run_all_checks.sh. Release/TOOLSET.md incorrectly claims it is wired as Group 46. |
| PB-W3-BHV-02-SETTINGS-STRUCTURE | check_settings_structure.php | Historical standalone proof; current gate uncovered | Project Operations Governance Packet A records 69 PASS at ee0eb4d. Current main does not invoke it. It is DB-dependent and SKIP-capable, but there is no exact current-main SKIP evidence; it is not a sixth observed SKIP. |
| PB-W3-BHV-03-WORKLIST | check_worklist_behavior.php | Partial; fixture-SKIP evidence; uncovered | Explicitly NOT WIRED and exits 2 without DB. Adjacent checks do not prove its rendered, exact-once, photo and identity behaviors. |
| PB-W3-BHV-04-DAILY-RESET | check_daily_reset_behavior.php | Fixture-SKIP evidence; uncovered | Existing preview-copy checks do not prove closure, inbox, idempotency, paging, fail-closed or DST behavior. |
| PB-W3-BHV-05-DETAILED-CLAIM | check_detailed_claim_behavior.php | Partial; fixture-SKIP evidence; uncovered | Generic claim locking is adjacent only; presentation-token binding, body hash, time bucket, refusal and secrecy remain unproved. |
| PB-W3-BHV-06-ITEM-REDO | check_item_redo_behavior.php | Partial; fixture-SKIP evidence; uncovered | Task review-return coverage does not prove Routine item redo, evidence append, reactions, credit or exact-once behavior. |
| PB-W3-BHV-07-INSTANCE-ITEM-RENDER | check_instance_item_render.php | Fixture-SKIP evidence; uncovered | The ordinary page sweep reaches an early 404 before item cards and therefore does not cover this behavior. |
| PB-W3-PKG-01-COMPLETE-PACKAGE | check_complete_package.py | Packaging-only; partial textual coverage | Not executed by CI. Keep outside the standing runtime gate and invoke only against a corresponding Complete Package artifact. |
| PB-W3-PKG-02-DELTA | check_delta.py | Packaging-only; currently unreachable | Expects legacy Full Site.zip, Changed Files.zip and Diffs.zip while the current builder emits versioned FULL and REVIEW-CHANGESET packages. |

Exact runner facts:

- site/tools/run_all_checks.sh invokes none of the nine tools.
- site/tools/runtime-gate/run.sh invokes only run_all_checks.sh.
- linecheck-runtime-gate.yml therefore invokes none indirectly.
- web-doc-consistency.yml validates manifest hashes, proving artifact identity only.
- The green 81 PASS / 0 SKIP run for Architecture v1.1 Ratification and Baseline Mapping (PR #27) proves none of these nine tools.
- The five observed fixture-dependent behavior SKIPs are Worklist, Daily Reset, Detailed Claim, Item Redo and Instance Item Render.

Recommended later Packet C direction, still General-held:

1. Wire all seven behavior suites with explicit fixture handling and exact-head evidence.
2. Profile-wire Complete Package validation only when the matching artifact exists.
3. Either retire/archive Delta validation as superseded or modernize it for current FULL and REVIEW-CHANGESET artifacts.
4. Require a fresh current-head Settings Structure invocation before declaring continuous coverage.

## 6. W4 — archive candidate ledger

Every disposition below is a proposal, not authority to act.

| Stable ID | Candidate | Proposed classification | Prerequisite |
|---|---|---|---|
| PB-W4-001 | Dual-AI Collaboration Activation (PR #4) | Retain historical branch; later closure candidate | Bind successor and exact archive receipt; General closure authorization |
| PB-W4-002 | LC-002 Consistency Coverage (PR #11) | Superseded PR closure candidate; retain Git history | Record main workflow replacement proof; General closure authorization |
| PB-W4-003 | mixed Post-Routine Consolidation and UX Specs (PR #13) | Paragraph lineage, then closure candidate; never merge mixed head | Map every paragraph to successors; General closure authorization |
| PB-W4-004 | Documentation and Gate Consolidation Preflight (PR #19, LC-012) | Cold history after Packet B | Preserve useful method, rejected stale facts and exact head; General closure authorization |
| PB-W4-005 | Exact-Source Hierarchy Refresh Preflight (PR #20, LC-011) | Cold history after Packet B | Preserve useful method, rejected stale facts and exact head; General closure authorization |
| PB-W4-006 | Planning/ROADMAP-ORDER.md | Keep active pending accepted canonical successor | Migrate every consumer after Canonical Product Roadmap acceptance |
| PB-W4-007 | Planning/POST-ROUTINE-HIERARCHY-SEQUENCE.md | Keep active | Reclassify only with accepted canonical roadmap |
| PB-W4-008 | Planning/BACKLOG.md | Held cold-history candidate | Extract unique living facts and prove inbound-reference migration |
| PB-W4-009 | Planning/MAP-VERIFICATION-2026-08-02.md | Cold-history candidate, preserve verbatim | Preserve the original claim and corrective addendum together |
| PB-W4-010 | Routine Roadmap Consolidation v3 plus 48-to-20 CSV | Cold-history set candidate | Prove no generator/tooling dependency |
| PB-W4-011 | Routine Continuation v2, Routine Overhaul Roadmap v2 and compatibility matrix | Retain in place; not archive-ready | Existing tooling dependency must be migrated and proved |
| PB-W4-012 | Existing Planning/Archive contents including v0.14 architecture | Retain existing history | Architecture v1.1 has live predecessor references |

No move, rename, delete, archive or PR closure is justified during planning-only preparation.

## 7. W5 — current-truth amendment ledger

| Stable ID | Required later amendment | Status |
|---|---|---|
| PB-W5-001 | Replace stale Packet A base metadata while distinguishing accepted-release and current-main development truth | Source-backed fact correction |
| PB-W5-002 | Refresh Active Work Register: Packet A, Credit Economy and Icon Register merged; Architecture accepted-unmerged; remaining draft heads current | Source-backed fact correction |
| PB-W5-003 | Move completed Credit Economy and Icon Register ownership rows into lineage while preserving Packet B’s Codex-owner/Claude-reviewer assignment | Source-backed fact correction |
| PB-W5-004 | Correct run.php wording to live read-only legacy/history, with only unreachable mutation dead | Apply as overlay-labeled fact until Architecture merges, then authoritative amendment |
| PB-W5-005 | Refresh Authority Index candidate/merged/current-main states | Source-backed fact correction |
| PB-W5-006 | After Architecture merge, add it to Authority Index section 2 as owner-ratified foundational direction, not release truth or build-order authority | Due after separate merge authorization |
| PB-W5-007 | Refresh Decision Queue and Health Check with current merges, accepted-unmerged Architecture, roadmap conflict and exact role ownership | Source-backed fact correction; do not reopen v0.3 ratification |
| PB-W5-008 | Remove static monitoring cadence prose or bind it to the live automation record | Governance-health correction |
| PB-W5-009 | Preserve current main and accepted-unmerged Architecture as separate evidence layers | Mandatory integrity rule |
| PB-W5-010 | Create archive-ledger records before any historical PR closure or file move | Mandatory safeguard |
| PB-W5-011 | Refresh Brand Asset Register’s Home and Routine Brand/Progress Polish Phase B1 status | Source-backed fact correction |
| PB-W5-012 | Add a two-axis accepted-release versus current-main-source status convention | Recommended governance improvement |
| PB-W5-013 | Add machine-checkable current-governance state so merged PR facts cannot drift only in prose | Recommended Packet C design input |

## 8. Collaboration health gaps

- Merged governance documents still call themselves candidate/draft and point at stale main, recreating stale waiting states.
- Generic role prose can obscure task-specific ownership; the Active Work Register assignment must control.
- Static monitoring cadence text drifts whenever General changes the automation.
- Superseded open drafts increase false active-work noise, but closure must wait for exact lineage and General.
- Branch-only history is difficult to discover; the Archive Ledger must bind PR, title, head, paths and successors.
- Product main and accepted-unmerged Architecture must never be collapsed.
- Forge handoff ceremony must not block proactive exact-head GitHub inspection, but every gate-changing action still needs a four-part receipt.

## 9. General-only decision queue, deliberately deferred

The read-only audit does not request decisions now. Before later execution, General alone must decide:

1. separate merge authorization for Architecture v1.1 Ratification and Baseline Mapping (PR #27);
2. acceptance of one Canonical Product Roadmap successor before active-roadmap archival;
3. historical PR closures after complete lineage receipts;
4. every actual archive/move/delete action;
5. the seven behavior-check wiring plan and Delta retire-versus-modernize outcome;
6. whether Architecture artifacts belong in web-doc.zip;
7. whether settings.php and eightysix.php route ownership should change or simply be documented;
8. whether render evidence becomes a formal CI gate.

AI Operating Agreement v0.3 ratification is not on this queue; Project Operations Governance Packet A’s exact merge receipt already confirms General ratification.

## 10. Independent review request to Claude

Please independently review this working packet against:

- product main 0f12b0de1362292f338e34ca2835c9cc2a20369e;
- Architecture v1.1 Ratification and Baseline Mapping (PR #27, LC-ARCH-1_1) exact accepted-unmerged head 46398718cf439a18064641f4e1728e630f8e6943;
- LC-OPS-CONSOLIDATION/codex/0014;
- Project Operations Governance Packet A merge receipt LC-OPS-CONSOLIDATION/claude/0010;
- the nine exact gate tools and their runners;
- live GitHub PR state and Forge receipts.

Return one bounded review that separates confirmed facts, incorrect claims, incomplete lineage, recommendation disagreements and true General-only decisions. Do not create a Packet B product branch or PR. Do not modify runtime, schema, migrations, archives, PR state, product documentation, release surfaces or gates.

Requested receipt state: PENDING_REVIEW until Claude returns exact Forge message identity. All holds remain active.
