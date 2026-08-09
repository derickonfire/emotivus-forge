# Active Runtime Reachability and Classification

**Forge version:** 0.575  
**Modules inventoried:** 94  
**Statically reachable:** 94  
**Statically unreachable:** 0  
**Report SHA-256:** `13561dfcd1062e46a44f43156d252ffc8652db3f6d40b0504f2352ae4404482a`

## Command observations

| Command | Trace | Exit | Modules observed |
|---|---|---:|---:|
| `run` | OBSERVED | 0 | 63 |
| `help` | OBSERVED | 0 | 7 |
| `adopt` | OBSERVED | 0 | 58 |
| `resume` | OBSERVED | 0 | 53 |
| `check` | OBSERVED | 1 | 41 |
| `ship` | OBSERVED | 1 | 34 |

## Module classification

| Module | Static | Observed commands | Classification |
|---|---|---|---|
| `emotivus_forge` | active | — | G2_SESSION_CONTINUITY |
| `emotivus_forge.cli` | active | adopt, check, help, resume, run, ship | G2_SESSION_CONTINUITY |
| `emotivus_forge.commands` | active | — | G2_SESSION_CONTINUITY |
| `emotivus_forge.commands.adopt` | active | adopt | G2_SESSION_CONTINUITY |
| `emotivus_forge.commands.bind` | active | — | G1_PROJECT_TRUTH |
| `emotivus_forge.commands.check` | active | check | G2_SESSION_CONTINUITY |
| `emotivus_forge.commands.common` | active | adopt, check, help, resume, run, ship | G2_SESSION_CONTINUITY, SHARED_RUNTIME |
| `emotivus_forge.commands.noticing` | active | adopt, check, resume, run | G2_SESSION_CONTINUITY |
| `emotivus_forge.commands.public` | active | help, resume, run, ship | G2_SESSION_CONTINUITY |
| `emotivus_forge.core` | active | — | SHARED_RUNTIME |
| `emotivus_forge.core.artifact_collision` | active | run, ship | G1_PROJECT_TRUTH |
| `emotivus_forge.core.attestation_kit` | active | — | G1_PROJECT_TRUTH |
| `emotivus_forge.core.authority_baseline` | active | adopt, check, resume, run, ship | G1_PROJECT_TRUTH |
| `emotivus_forge.core.authority_registry` | active | adopt, check, resume, run | G1_PROJECT_TRUTH |
| `emotivus_forge.core.bounded_retrieval` | active | adopt, resume, run | G3_EVOLUTION_KERNEL |
| `emotivus_forge.core.browser_evidence` | active | — | G1_PROJECT_TRUTH |
| `emotivus_forge.core.build_attestation` | active | — | G1_PROJECT_TRUTH |
| `emotivus_forge.core.canonical_claims` | active | adopt, check, resume, run | G1_PROJECT_TRUTH |
| `emotivus_forge.core.capabilities` | active | adopt, resume, run | G3_EVOLUTION_KERNEL |
| `emotivus_forge.core.change_ledger` | active | adopt, check, resume, run | G1_PROJECT_TRUTH |
| `emotivus_forge.core.changes` | active | adopt, check, resume, run, ship | G1_PROJECT_TRUTH |
| `emotivus_forge.core.check_qualification` | active | adopt, check, resume, run | G1_PROJECT_TRUTH |
| `emotivus_forge.core.code_orientation` | active | adopt, run | G1_PROJECT_TRUTH |
| `emotivus_forge.core.cold_session_validation` | active | adopt, resume, run, ship | G1_PROJECT_TRUTH |
| `emotivus_forge.core.common` | active | adopt, check, help, resume, run, ship | SHARED_RUNTIME |
| `emotivus_forge.core.confidentiality_boundary` | active | adopt, run | G1_PROJECT_TRUTH |
| `emotivus_forge.core.continuity_benchmark` | active | — | G3_EVOLUTION_KERNEL |
| `emotivus_forge.core.continuity_register` | active | adopt, resume, run, ship | G3_EVOLUTION_KERNEL |
| `emotivus_forge.core.decision_forks` | active | adopt, resume, run | G1_PROJECT_TRUTH |
| `emotivus_forge.core.deployable_boundary` | active | adopt, check, resume, run | G1_PROJECT_TRUTH |
| `emotivus_forge.core.evidence_kit` | active | — | G1_PROJECT_TRUTH |
| `emotivus_forge.core.evidence_validity` | active | check | G1_PROJECT_TRUTH |
| `emotivus_forge.core.external_evidence` | active | — | G1_PROJECT_TRUTH |
| `emotivus_forge.core.field_trials` | active | adopt, resume, run | G1_PROJECT_TRUTH |
| `emotivus_forge.core.forward_compat` | active | adopt, resume, run | G3_EVOLUTION_KERNEL |
| `emotivus_forge.core.gate_coverage` | active | — | G1_PROJECT_TRUTH |
| `emotivus_forge.core.gate_diff_monotonicity` | active | — | G1_PROJECT_TRUTH |
| `emotivus_forge.core.guardrails` | active | adopt, check, resume, run | G1_PROJECT_TRUTH |
| `emotivus_forge.core.guidance` | active | help | G2_SESSION_CONTINUITY |
| `emotivus_forge.core.handoff` | active | — | G2_SESSION_CONTINUITY |
| `emotivus_forge.core.instance_key` | active | — | G1_PROJECT_TRUTH |
| `emotivus_forge.core.knowledge` | active | adopt, run | G2_SESSION_CONTINUITY |
| `emotivus_forge.core.ledger` | active | adopt, check, resume, run, ship | G1_PROJECT_TRUTH |
| `emotivus_forge.core.ledger_assertions` | active | adopt, check, resume, run | G1_PROJECT_TRUTH |
| `emotivus_forge.core.lifecycle` | active | adopt, check, resume, run | G3_EVOLUTION_KERNEL |
| `emotivus_forge.core.lineage` | active | adopt, check, resume, run, ship | G1_PROJECT_TRUTH |
| `emotivus_forge.core.migration_identity` | active | adopt, check, resume, run, ship | G3_EVOLUTION_KERNEL |
| `emotivus_forge.core.models` | active | adopt, check, resume, run, ship | SHARED_RUNTIME |
| `emotivus_forge.core.narrative_integrity` | active | — | G1_PROJECT_TRUTH |
| `emotivus_forge.core.native_invocation` | active | — | G1_PROJECT_TRUTH |
| `emotivus_forge.core.native_tools` | active | adopt, check, resume, run | SHARED_RUNTIME |
| `emotivus_forge.core.notices` | active | adopt, check, resume, run, ship | SHARED_RUNTIME |
| `emotivus_forge.core.orientation` | active | adopt, check, resume, run, ship | G2_SESSION_CONTINUITY |
| `emotivus_forge.core.package_family` | active | adopt, check, resume, run, ship | G1_PROJECT_TRUTH |
| `emotivus_forge.core.passport` | active | adopt, run | G2_SESSION_CONTINUITY |
| `emotivus_forge.core.paths` | active | adopt, check, help, resume, run, ship | SHARED_RUNTIME |
| `emotivus_forge.core.presentation_profile` | active | adopt, resume, run | G3_EVOLUTION_KERNEL |
| `emotivus_forge.core.project_events` | active | check | G1_PROJECT_TRUTH |
| `emotivus_forge.core.project_identity` | active | adopt, check, resume, run, ship | G1_PROJECT_TRUTH |
| `emotivus_forge.core.provenance` | active | adopt, check, resume, run | G1_PROJECT_TRUTH |
| `emotivus_forge.core.recommended_prompt` | active | run | G2_SESSION_CONTINUITY |
| `emotivus_forge.core.relationships` | active | adopt, check, resume, run | G1_PROJECT_TRUTH |
| `emotivus_forge.core.release_authorization` | active | adopt, resume, run, ship | G1_PROJECT_TRUTH |
| `emotivus_forge.core.release_distribution` | active | adopt, resume, run, ship | G1_PROJECT_TRUTH |
| `emotivus_forge.core.release_facts` | active | adopt, resume, run, ship | G1_PROJECT_TRUTH |
| `emotivus_forge.core.release_package` | active | adopt, resume, run, ship | G1_PROJECT_TRUTH |
| `emotivus_forge.core.release_proof` | active | adopt, resume, run, ship | G1_PROJECT_TRUTH |
| `emotivus_forge.core.remote_release` | active | — | G1_PROJECT_TRUTH |
| `emotivus_forge.core.resume` | active | adopt, resume, run | G2_SESSION_CONTINUITY |
| `emotivus_forge.core.runtime_matrix` | active | adopt, check, resume, run | G1_PROJECT_TRUTH |
| `emotivus_forge.core.secret_screening` | active | adopt, run | G1_PROJECT_TRUTH |
| `emotivus_forge.core.self_currency` | active | adopt, check, resume, run, ship | G1_PROJECT_TRUTH |
| `emotivus_forge.core.semantic_state` | active | — | G1_PROJECT_TRUTH |
| `emotivus_forge.core.session_adapters` | active | adopt, check, resume, run, ship | G2_SESSION_CONTINUITY |
| `emotivus_forge.core.session_close` | active | adopt, check, resume, run, ship | G2_SESSION_CONTINUITY |
| `emotivus_forge.core.session_reconciliation` | active | run | G2_SESSION_CONTINUITY |
| `emotivus_forge.core.ship_claims` | active | ship | G1_PROJECT_TRUTH |
| `emotivus_forge.core.sidecar` | active | adopt, check, resume, run, ship | G2_SESSION_CONTINUITY |
| `emotivus_forge.core.source_anchored_release` | active | — | G1_PROJECT_TRUTH |
| `emotivus_forge.core.startup` | active | run | G2_SESSION_CONTINUITY |
| `emotivus_forge.core.state` | active | adopt, check, help, resume, run, ship | SHARED_RUNTIME |
| `emotivus_forge.core.state_transitions` | active | adopt, check, resume, run, ship | G1_PROJECT_TRUTH |
| `emotivus_forge.core.storage` | active | adopt, check, resume, run | SHARED_RUNTIME |
| `emotivus_forge.core.surface_coverage` | active | adopt, check, resume, run, ship | G1_PROJECT_TRUTH |
| `emotivus_forge.core.telemetry` | active | adopt, check, resume, run | SHARED_RUNTIME |
| `emotivus_forge.core.third_party_intake` | active | adopt, resume, run | G3_EVOLUTION_KERNEL |
| `emotivus_forge.core.truth` | active | adopt, check, resume, run, ship | G1_PROJECT_TRUTH |
| `emotivus_forge.core.workspace_integrity` | active | run, ship | G1_PROJECT_TRUTH |
| `emotivus_forge.services` | active | — | SHARED_RUNTIME |
| `emotivus_forge.services.doctor` | active | — | G2_SESSION_CONTINUITY |
| `emotivus_forge.services.native_gate` | active | — | G1_PROJECT_TRUTH |
| `emotivus_forge.services.runtime_proof` | active | — | G1_PROJECT_TRUTH |
| `emotivus_forge.services.scoped_check` | active | check | G1_PROJECT_TRUTH |
| `emotivus_forge.services.ship` | active | ship | G1_PROJECT_TRUTH |

## Active top-level path classification

| Path | Files | Dev | Public | Disposition | Classification |
|---|---:|---:|---:|---|---|
| `.deployignore` | 1 | yes | yes | KEEP | PACKAGING |
| `.forgeignore` | 1 | yes | yes | KEEP | G1_PROJECT_TRUTH, PACKAGING |
| `.gitignore` | 1 | no | no | KEEP | PACKAGING, REFERENCE |
| `CERTIFICATION.md` | 1 | yes | no | KEEP | G1_PROJECT_TRUTH, REFERENCE |
| `CHANGELOG.md` | 1 | yes | yes | KEEP | REFERENCE, G3_EVOLUTION_KERNEL |
| `CLAUDE.md` | 1 | no | no | KEEP | G2_SESSION_CONTINUITY, REFERENCE |
| `CONFIDENTIALITY-POLICY.json` | 1 | yes | yes | KEEP | G1_PROJECT_TRUTH, PACKAGING |
| `DEVELOPMENT-ROADMAP.md` | 1 | no | no | KEEP | G3_EVOLUTION_KERNEL, WEB_DOCUMENTATION |
| `FORGE-2029-VERDICT.md` | 1 | no | no | KEEP | G3_EVOLUTION_KERNEL, REFERENCE |
| `FORGE-MANIFEST.json` | 1 | yes | yes | KEEP | G1_PROJECT_TRUTH, PACKAGING |
| `FORGE-PRODUCT.json` | 1 | yes | yes | KEEP | G1_PROJECT_TRUTH, G2_SESSION_CONTINUITY, G3_EVOLUTION_KERNEL, WEB_DOCUMENTATION |
| `IMPLEMENTATION-REPORT.md` | 1 | yes | no | REFERENCE | REFERENCE |
| `LICENSE-INTERNAL.md` | 1 | yes | no | KEEP | REFERENCE |
| `PROGRESS-STATUS.md` | 1 | yes | yes | KEEP | G3_EVOLUTION_KERNEL, WEB_DOCUMENTATION |
| `PUBLIC-RELEASE-NOTICE.md` | 1 | yes | yes | KEEP | G1_PROJECT_TRUTH, WEB_DOCUMENTATION |
| `README.md` | 1 | yes | yes | KEEP | WEB_DOCUMENTATION, G2_SESSION_CONTINUITY |
| `ROADMAP-2029.md` | 1 | no | no | KEEP | G3_EVOLUTION_KERNEL, WEB_DOCUMENTATION |
| `ROADMAP.md` | 1 | yes | yes | KEEP | G3_EVOLUTION_KERNEL, WEB_DOCUMENTATION |
| `RUN-FORGE.md` | 1 | yes | yes | KEEP | G2_SESSION_CONTINUITY, WEB_DOCUMENTATION |
| `THIRD-PARTY-LICENSES/` | 1 | yes | yes | KEEP | REFERENCE, MIGRATION |
| `THIRD-PARTY-NOTICES.md` | 1 | yes | yes | KEEP | REFERENCE, MIGRATION |
| `adapters/` | 6 | yes | yes | KEEP | MIGRATION, G3_EVOLUTION_KERNEL |
| `capability_vault/` | 109 | yes | no | FREEZE | REFERENCE, MIGRATION |
| `docs/` | 64 | yes | yes | REDUCE | REFERENCE, WEB_DOCUMENTATION |
| `docs-site/` | 16 | yes | no | KEEP | WEB_DOCUMENTATION |
| `emotivus_forge/` | 188 | yes | yes | KEEP | G1_PROJECT_TRUTH, G2_SESSION_CONTINUITY, G3_EVOLUTION_KERNEL |
| `examples/` | 47 | yes | yes | REFERENCE | MIGRATION, REFERENCE |
| `exchange/` | 381 | no | no | KEEP | REFERENCE, G3_EVOLUTION_KERNEL |
| `forge` | 1 | yes | yes | KEEP | G2_SESSION_CONTINUITY |
| `forge.cmd` | 1 | yes | yes | KEEP | G2_SESSION_CONTINUITY |
| `forge.py` | 1 | yes | yes | KEEP | G2_SESSION_CONTINUITY |
| `frg` | 1 | yes | yes | KEEP | G2_SESSION_CONTINUITY |
| `frg.cmd` | 1 | yes | yes | KEEP | G2_SESSION_CONTINUITY |
| `frg.py` | 1 | yes | yes | KEEP | G2_SESSION_CONTINUITY |
| `planning/` | 44 | yes | yes | KEEP | REFERENCE, G3_EVOLUTION_KERNEL |
| `policy-packs/` | 1 | yes | yes | KEEP | G1_PROJECT_TRUTH, MIGRATION |
| `release/` | 70 | yes | yes | KEEP | PACKAGING, REFERENCE |
| `research/` | 5 | yes | no | REFERENCE | REFERENCE |
| `tests/` | 131 | yes | yes | KEEP | TESTING |
| `tools/` | 23 | yes | yes | KEEP | PACKAGING, TESTING |

## Manifest path classification

| Path pattern | Dev | Public | Classification |
|---|---:|---:|---|
| `.deployignore` | yes | yes | PACKAGING, G1_PROJECT_TRUTH |
| `.forgeignore` | yes | yes | PACKAGING, G1_PROJECT_TRUTH |
| `CERTIFICATION.md` | yes | no | REFERENCE |
| `CHANGELOG.md` | yes | yes | REFERENCE |
| `CONFIDENTIALITY-POLICY.json` | yes | yes | PACKAGING, G1_PROJECT_TRUTH |
| `FORGE-MANIFEST.json` | yes | yes | PACKAGING, G1_PROJECT_TRUTH |
| `FORGE-PRODUCT.json` | yes | yes | PACKAGING, G1_PROJECT_TRUTH |
| `IMPLEMENTATION-REPORT.md` | yes | no | REFERENCE |
| `LICENSE-INTERNAL.md` | yes | no | REFERENCE |
| `PROGRESS-STATUS.md` | yes | yes | REFERENCE |
| `PUBLIC-RELEASE-NOTICE.md` | yes | yes | REFERENCE |
| `README.md` | yes | yes | REFERENCE |
| `ROADMAP.md` | yes | yes | REFERENCE |
| `RUN-FORGE.md` | yes | yes | REFERENCE |
| `THIRD-PARTY-LICENSES/` | yes | yes | MIGRATION, REFERENCE |
| `THIRD-PARTY-NOTICES.md` | yes | yes | REFERENCE |
| `adapters/` | yes | yes | MIGRATION, REFERENCE |
| `capability_vault/` | yes | no | REFERENCE |
| `docs-site/` | yes | no | WEB_DOCUMENTATION |
| `docs/` | yes | yes | REFERENCE |
| `emotivus_forge/` | yes | yes | SHARED_RUNTIME |
| `examples/` | yes | yes | MIGRATION, REFERENCE |
| `forge` | yes | yes | SHARED_RUNTIME |
| `forge.cmd` | yes | yes | SHARED_RUNTIME |
| `forge.py` | yes | yes | SHARED_RUNTIME |
| `frg` | yes | yes | SHARED_RUNTIME |
| `frg.cmd` | yes | yes | SHARED_RUNTIME |
| `frg.py` | yes | yes | SHARED_RUNTIME |
| `planning/` | yes | no | REFERENCE |
| `planning/README.md` | no | yes | REFERENCE |
| `policy-packs/` | yes | yes | MIGRATION, REFERENCE |
| `release/` | yes | no | PACKAGING |
| `release/WEBSITE-CONTENT-ACCURACY.md` | no | yes | PACKAGING |
| `release/WEBSITE-DEPLOYMENT.md` | no | yes | PACKAGING |
| `research/` | yes | no | REFERENCE |
| `tests/` | yes | yes | TESTING |
| `tools/` | yes | yes | PACKAGING |

## Reduction decision boundary

This report authorizes **classification and review only**. Static non-reachability or absence from a bounded command trace does not, by itself, authorize deletion. A removal must also preserve tests, package boundaries, migrations, historical truth, and the four-page website pipeline.
