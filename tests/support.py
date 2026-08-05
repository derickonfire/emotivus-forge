from __future__ import annotations

import json
import unittest
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]


class ForgeTestCase(unittest.TestCase):
    def _fixture(self, root: Path) -> None:
        (root / "index.php").write_text("<?php echo 'ok';\n", encoding="utf-8")
        (root / "BACKLOG.md").write_text(
            "# Backlog\n\n## THE NEXT ACTION\n\n- Add a login screen.\n",
            encoding="utf-8",
        )


    def _native_invocation_contract(
        self,
        root: Path,
        *,
        expected_checks: list[str] | None = None,
        expected_count: int | None = None,
        argv: list[str] | None = None,
        working_directory: str = ".",
        coverage_policy: str = "exact",
    ) -> Path:
        path = root / "forge-native-invocation.json"
        payload = {
            "schema": "forge-native-invocation/1",
            "candidate_id": "canonical",
            "authority": "owner",
            "argv": argv or ["bash", "tools/run_all_checks.sh"],
            "working_directory": working_directory,
            "environment": {},
            "coverage_policy": coverage_policy,
            "timeout_seconds": 30,
            "verification_tier": "sandbox",
            "rationale": "The project owner confirmed the exact invocation and expected gate coverage.",
        }
        if expected_checks is not None:
            payload["expected_checks"] = expected_checks
        if expected_count is not None:
            payload["expected_count"] = expected_count
        if expected_checks is None and expected_count is None:
            payload["expected_count"] = 1
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    def _doctor_contract(self, root: Path, *, runtime_seconds: int = 5, file_limit: int = 20) -> Path:
        evidence = root / "runtime-issue.md"
        evidence.write_text("# Runtime issue\n\nConfirm the local runtime matches the project declaration.\n", encoding="utf-8")
        contract = root / "forge-doctor-contract.json"
        contract.write_text(json.dumps({
            "schema": 1,
            "capability_id": "doctor",
            "authority": "owner",
            "trigger": {
                "description": "A concrete local runtime mismatch requires bounded diagnosis.",
                "evidence_paths": ["runtime-issue.md"],
            },
            "scope": {
                "included": ["local runtime versions", "declared runtime pins", "required PHP extensions"],
                "excluded": ["production equivalence", "automatic repair", "database state"],
            },
            "budget": {
                "runtime_seconds": runtime_seconds,
                "file_limit": file_limit,
                "output_characters": 6000,
            },
            "focused_regressions": [
                "doctor.inactive-by-default",
                "doctor.explicit-contract",
                "doctor.diagnose-only",
                "doctor.budget-bound",
                "doctor.contract-change-requires-reactivation",
            ],
            "native_advantage": {
                "status": "distinct-value",
                "explanation": "This compares project-declared runtime expectations with the local CLI without replacing the native test gate.",
            },
            "allow_repairs": False,
        }, indent=2) + "\n", encoding="utf-8")
        return contract

    def _atomic_guardrail_contract(self, root: Path) -> Path:
        (root / "migrations").mkdir(exist_ok=True)
        (root / "admin").mkdir(exist_ok=True)
        (root / "public").mkdir(exist_ok=True)
        (root / "migrations" / "001_labels.sql").write_text("-- baseline schema\n", encoding="utf-8")
        (root / "admin" / "editor.php").write_text("<?php echo 'editor';\n", encoding="utf-8")
        (root / "public" / "menu.php").write_text("<?php echo 'menu';\n", encoding="utf-8")
        (root / "DECISIONS.md").write_text(
            "# Decision\n\nDietary labeling must land across storage, editor, and public display in one pass.\n",
            encoding="utf-8",
        )
        contract = root / "dietary-label-guardrail.json"
        contract.write_text(json.dumps({
            "schema": 1,
            "guardrail_id": "dietary-labels-atomic",
            "title": "Dietary labels must land atomically",
            "authority": "owner",
            "rationale": "A partial dietary-label implementation can display a mark that is unsupported by stored project data.",
            "mode": "atomic-change-set",
            "evidence_paths": ["DECISIONS.md"],
            "trigger_paths": ["migrations/**", "admin/**", "public/**"],
            "required_surfaces": [
                {"id": "storage", "description": "Schema and migration support for persisted labels", "path_patterns": ["migrations/**"]},
                {"id": "editor", "description": "Administrative controls that set the labels", "path_patterns": ["admin/**"]},
                {"id": "public-display", "description": "Customer-facing rendering of the labels", "path_patterns": ["public/**"]},
            ],
            "unsafe_partial_state": "A false dietary claim may appear configured or public without a trustworthy persisted value behind it.",
            "verification_boundary": "Changing every declared surface does not prove the labels are correct, migrated, accessible, or safe in production.",
        }, indent=2) + "\n", encoding="utf-8")
        return contract


    def _project_identity_contract(self, root: Path, *, version_code: int = 26080101) -> Path:
        path = root / "forge-project-identity.json"
        path.write_text(json.dumps({
            "schema": 1,
            "identity_id": "product-suite",
            "authority": "owner",
            "release_train": "preview",
            "build_id": "2026-08-01.1",
            "components": {
                "server": {"status": "present", "version": "0.3.0", "contracts": {"api": "1"}},
                "web": {"status": "present", "version": "0.2.0", "contracts": {}},
                "player": {"status": "absent", "version": None, "contracts": {}},
            },
            "monotonic": {"android_version_code": version_code},
            "baseline": {"build_id": "2026-07-31.2", "source": "owner", "confirmed_utc": "2026-08-01T12:00:00-04:00"},
            "truth_boundary": "The project owner declares identity values; Forge records, compares, and rejects monotonic regressions but never chooses a version.",
        }, indent=2) + "\n", encoding="utf-8")
        return path

    def _event_guardrail_contract(self, root: Path) -> Path:
        (root / "config").mkdir(exist_ok=True)
        (root / "docs").mkdir(exist_ok=True)
        (root / "config" / "cors.json").write_text('{"origins":["*"]}\n', encoding="utf-8")
        (root / "docs" / "deployment.md").write_text("# Deployment\n\nDomain is not selected.\n", encoding="utf-8")
        (root / "DECISIONS.md").write_text("# Decisions\n\nWildcard CORS is temporary until the production domain is confirmed.\n", encoding="utf-8")
        path = root / "domain-window-guardrail.json"
        path.write_text(json.dumps({
            "schema": 1,
            "guardrail_id": "domain-window",
            "title": "Close temporary domain placeholders",
            "authority": "owner",
            "rationale": "Wildcard domain placeholders are acceptable only while the production domain remains genuinely undecided.",
            "mode": "event-obligation",
            "evidence_paths": ["DECISIONS.md"],
            "closes_at": {
                "event_id": "production-domain-confirmed",
                "description": "The project owner confirms the production domain."
            },
            "blocks": [
                {"id": "runtime-config", "description": "Replace temporary runtime origin configuration", "path_patterns": ["config/cors.json"]},
                {"id": "operator-docs", "description": "Update the deployment instructions for the confirmed domain", "path_patterns": ["docs/deployment.md"]}
            ],
            "unsafe_after_close": "A wildcard origin remains a security defect after the production domain is known and can be configured exactly.",
            "verification_boundary": "Changing both declared paths does not prove production deployment, browser behavior, or complete security review.",
        }, indent=2) + "\n", encoding="utf-8")
        return path

    def _deadline_fork_fixture(self, root: Path) -> None:
        self._fixture(root)
        (root / "requirements.md").write_text(
            "# Requirements\n\nFollow-up presets must include Immediate, 15 Minutes, and 30 Minutes.\n",
            encoding="utf-8",
        )
        (root / "followup.html").write_text(
            '<label>Due date <input type="date" name="due_date"></label>\n',
            encoding="utf-8",
        )

    def _relationship_contract(self, root: Path) -> Path:
        (root / "public").mkdir(exist_ok=True)
        (root / "includes").mkdir(exist_ok=True)
        (root / "assets").mkdir(exist_ok=True)
        (root / "templates").mkdir(exist_ok=True)
        (root / "media").mkdir(exist_ok=True)
        (root / "migrations").mkdir(exist_ok=True)
        (root / "public" / "menu.php").write_text("<?php require __DIR__ . '/../includes/menu-data.php';\n", encoding="utf-8")
        (root / "includes" / "menu-data.php").write_text("<?php function menu_rows(){ return []; }\n", encoding="utf-8")
        (root / "templates" / "menu.html").write_text('<button data-menu-crop>Crop</button>\n', encoding="utf-8")
        (root / "assets" / "menu-crop.js").write_text("document.querySelector('[data-menu-crop]');\n", encoding="utf-8")
        (root / "media" / "hero.jpg").write_bytes(b"neutral-image")
        (root / "public" / "hero.php").write_text("<?php echo 'media/hero.jpg';\n", encoding="utf-8")
        (root / "migrations" / "001_menu.sql").write_text("CREATE TABLE menu_items (id INT);\n", encoding="utf-8")
        (root / "RELATIONSHIP-DECISIONS.md").write_text(
            "# Confirmed relationships\n\nThe public menu depends on menu data, crop markup depends on its behavior, and the hero image has one public consumer.\n",
            encoding="utf-8",
        )
        contract = root / "forge-relationships.json"
        contract.write_text(json.dumps({
            "schema": 1,
            "relationship_set_id": "public-menu-runtime",
            "title": "Confirmed public menu relationships",
            "authority": "owner",
            "rationale": "The project owner confirmed the relationships that connect the public menu entry point, behavior binding, resource consumer, and migration effect.",
            "evidence_paths": ["RELATIONSHIP-DECISIONS.md"],
            "relationships": [
                {
                    "id": "menu-entrypoint-data",
                    "kind": "entrypoint-include",
                    "source": {"role": "public entry point", "path_patterns": ["public/menu.php"]},
                    "targets": [{"role": "menu data include", "path_patterns": ["includes/menu-data.php"]}],
                    "propagation": "bidirectional",
                    "affected_surfaces": ["public-menu"],
                    "required_checks": ["native.public-menu-render"],
                    "reason": "The public menu entry point requires the menu data include at runtime."
                },
                {
                    "id": "menu-crop-binding",
                    "kind": "behavior-binding",
                    "source": {"role": "crop markup", "path_patterns": ["templates/menu.html"]},
                    "targets": [{"role": "crop behavior", "path_patterns": ["assets/menu-crop.js"]}],
                    "propagation": "bidirectional",
                    "affected_surfaces": ["menu-editor"],
                    "required_checks": ["native.menu-crop-behavior"],
                    "reason": "The menu crop controls require a matching behavior binding."
                },
                {
                    "id": "hero-resource-consumer",
                    "kind": "resource-consumer",
                    "source": {"role": "hero resource", "path_patterns": ["media/hero.jpg"]},
                    "targets": [{"role": "public hero consumer", "path_patterns": ["public/hero.php"]}],
                    "propagation": "bidirectional",
                    "affected_surfaces": ["public-hero"],
                    "required_checks": [],
                    "reason": "The hero image remains in use while the public hero consumer references it."
                },
                {
                    "id": "menu-migration-effect",
                    "kind": "migration-effect",
                    "source": {"role": "menu migration", "path_patterns": ["migrations/*.sql"]},
                    "targets": [{"role": "public menu runtime", "path_patterns": ["public/menu.php"]}],
                    "propagation": "source-to-target",
                    "affected_surfaces": ["public-menu"],
                    "required_checks": ["native.migration-contract"],
                    "reason": "Menu schema changes can affect the public menu runtime contract."
                }
            ],
            "verification_boundary": "Forge traverses only these owner-confirmed path relationships; it does not prove runtime execution, behavioral correctness, complete consumer coverage, or unrecorded dependencies."
        }, indent=2) + "\n", encoding="utf-8")
        return contract

    def _field_trial_contract(self, root: Path, *, minimum_observations: int = 3) -> Path:
        truth = root / "FIELD-TRUTH.md"
        truth.write_text(
            "# Field truth\n\nObjective: preserve project continuity.\nAuthority: ROADMAP.md governs the next action.\n",
            encoding="utf-8",
        )
        contract = root / "forge-field-trial.json"
        contract.write_text(json.dumps({
            "schema": 1,
            "trial_id": "continuity-trial",
            "title": "Cross-model continuity field trial",
            "authority": "owner",
            "rationale": "Forge needs observed project-local evidence before it can make any claim about continuity value or recommendation accuracy.",
            "project_profile": "zip-multi-session",
            "models": ["ChatGPT", "Claude"],
            "scenarios": ["first-contact", "continuation", "defect-investigation"],
            "ground_truth_paths": ["FIELD-TRUTH.md", "BACKLOG.md"],
            "minimum_observations": minimum_observations,
            "measures": [
                "objective-recovery", "authority-discovery", "resume-usefulness", "owner-comprehension",
                "time-to-meaningful-work", "native-evidence-ingestion", "doctor-recommendation",
                "doctor-diagnosis", "guardrail-trigger", "contract-usability",
            ],
            "truth_boundary": "Human or controlled-fixture observations describe only this local sample and cannot establish universal accuracy, causality, or commercial value.",
        }, indent=2) + "\n", encoding="utf-8")
        return contract

    def _field_observation(
        self,
        root: Path,
        observation_id: str,
        *,
        model: str = "ChatGPT",
        scenario: str = "continuation",
        objective: str = "correct",
        authority: str = "correct",
        doctor_truth: str = "needed",
        doctor_result: str = "recommended",
        guardrail_truth: str = "should-trigger",
        guardrail_result: str = "triggered",
        minutes: float = 8.0,
    ) -> Path:
        path = root / f"{observation_id}.json"
        path.write_text(json.dumps({
            "schema": 1,
            "observation_id": observation_id,
            "trial_id": "continuity-trial",
            "task_id": f"task-{observation_id}",
            "scenario": scenario,
            "model": model,
            "reviewer": "Project owner",
            "reviewer_role": "owner",
            "outcomes": {
                "objective_recovery": objective,
                "authority_discovery": authority,
                "resume_usefulness_score": 4,
                "owner_comprehension_score": 5,
                "contract_usability_score": 4,
                "time_to_meaningful_work_minutes": minutes,
                "native_evidence_ingestion": "complete",
                "doctor": {
                    "ground_truth": doctor_truth,
                    "forge_result": doctor_result,
                    "diagnosis": "correct" if doctor_truth == "needed" else "not-applicable",
                },
                "guardrail": {
                    "ground_truth": guardrail_truth,
                    "forge_result": guardrail_result,
                },
                "evidence_paths": ["FIELD-TRUTH.md"],
                "notes": "Observed by the project owner after the bounded task.",
            },
        }, indent=2) + "\n", encoding="utf-8")
        return path
