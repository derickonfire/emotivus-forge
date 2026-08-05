from __future__ import annotations

import json
import tempfile
from pathlib import Path

from emotivus_forge.core import secret_screening as ss
from emotivus_forge.core.confidentiality_boundary import classify_confidentiality_boundaries
from tests.support import FORGE_ROOT, ForgeTestCase

SYNTHETIC_POLICY = {"synthetic_fixture_paths": ["tests/fixtures/security"]}


class SecretScreeningTests(ForgeTestCase):
    def test_private_key_block_is_block_level(self) -> None:
        findings = ss.screen_text("app/config.py", "-----BEGIN PRIVATE KEY-----\nAAAA\n")
        self.assertEqual(ss.highest_level(findings), ss.BLOCK)
        self.assertTrue(any(f["rule"] == "private-key-block" for f in findings))

    def test_aws_access_key_shape_is_block_level(self) -> None:
        findings = ss.screen_text("deploy/notes.md", "id AKIAABCDEFGHIJKLMNOP here")
        self.assertEqual(ss.highest_level(findings), ss.BLOCK)

    def test_connection_string_credentials_are_review_level(self) -> None:
        findings = ss.screen_text(
            "docs/setup.md", "postgres://appuser:hunter2primary@db.internal:5432/app"
        )
        self.assertEqual(ss.highest_level(findings), ss.REVIEW)

    def test_yesmem_adapted_anthropic_key_is_block_level(self) -> None:
        value = "sk-ant-" + "A1_b" * 14
        findings = ss.screen_text("config/runtime.txt", value)
        self.assertEqual(ss.highest_level(findings), ss.BLOCK)
        self.assertTrue(any(f["rule"] == "anthropic-api-key" for f in findings))

    def test_yesmem_adapted_openai_project_key_is_block_level(self) -> None:
        value = "sk-proj-" + "A1_b" * 10
        findings = ss.screen_text("config/runtime.txt", value)
        self.assertEqual(ss.highest_level(findings), ss.BLOCK)
        self.assertTrue(any(f["rule"] == "openai-api-key" for f in findings))

    def test_anthropic_key_is_not_double_classified_as_openai(self) -> None:
        value = "sk-ant-" + "A1_b" * 14
        rules = {f["rule"] for f in ss.screen_text("config/runtime.txt", value)}
        self.assertIn("anthropic-api-key", rules)
        self.assertNotIn("openai-api-key", rules)

    def test_yesmem_adapted_github_pat_is_block_level(self) -> None:
        value = "ghp_" + "A1b2" * 9
        findings = ss.screen_text("config/runtime.txt", value)
        self.assertEqual(ss.highest_level(findings), ss.BLOCK)
        self.assertTrue(any(f["rule"] == "github-personal-access-token" for f in findings))

    def test_yesmem_adapted_gpg_private_key_block_is_block_level(self) -> None:
        findings = ss.screen_text(
            "keys/backup.asc",
            "-----BEGIN PGP PRIVATE KEY BLOCK-----\nsynthetic-body\n-----END PGP PRIVATE KEY BLOCK-----",
        )
        self.assertEqual(ss.highest_level(findings), ss.BLOCK)

    def test_yesmem_adapted_jwt_accepts_non_ey_second_segment(self) -> None:
        token = "eyJ" + "A" * 12 + "." + "B" * 14 + "." + "C" * 14
        findings = ss.screen_text("logs/request.txt", token)
        self.assertEqual(ss.highest_level(findings), ss.REVIEW)
        self.assertTrue(any(f["rule"] == "jwt-literal" for f in findings))

    def test_yesmem_adapted_standalone_bearer_token_is_review_level(self) -> None:
        findings = ss.screen_text("docs/request.txt", "Bearer abc123def456ghi789jkl")
        self.assertEqual(ss.highest_level(findings), ss.REVIEW)
        self.assertTrue(any(f["rule"] == "bearer-token-literal" for f in findings))

    def test_yesmem_adapted_generic_url_password_is_review_level(self) -> None:
        findings = ss.screen_text(
            "docs/setup.md", "connect https://user:hunter2primary@example.test/path"
        )
        self.assertEqual(ss.highest_level(findings), ss.REVIEW)
        self.assertTrue(any(f["rule"] == "inline-url-credentials" for f in findings))

    def test_url_with_port_but_no_userinfo_is_not_a_credential(self) -> None:
        self.assertEqual(
            ss.screen_text("docs/setup.md", "see https://example.test:8080/path"),
            [],
        )

    def test_aws_secret_access_key_json_is_review_level(self) -> None:
        findings = ss.screen_text(
            "docs/config.json",
            '"AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"',
        )
        self.assertEqual(ss.highest_level(findings), ss.INFORMATIONAL)
        self.assertTrue(any(f["rule"] == "aws-secret-access-key-placeholder" for f in findings))

    def test_live_aws_secret_access_key_in_env_is_block_level(self) -> None:
        findings = ss.screen_text(
            ".env",
            "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYQWERTYUIOP\n",
        )
        self.assertEqual(ss.highest_level(findings), ss.BLOCK)
        self.assertTrue(any(f["rule"] == "aws-secret-access-key-live" for f in findings))

    def test_no_yesmem_adapted_finding_retains_provider_value(self) -> None:
        value = "sk-proj-" + "A1_b" * 10
        serialized = json.dumps(ss.screen_text("config/runtime.txt", value))
        self.assertNotIn(value, serialized)

    def test_noisy_upstream_defaults_are_not_forge_builtins(self) -> None:
        text = (
            "contact user@example.com at +1-415-555-0100; "
            "resolver 8.8.8.8; digest " + "0123456789abcdef" * 4
        )
        self.assertEqual(ss.screen_text("docs/public-reference.md", text), [])

    def test_placeholder_assignment_is_informational_only(self) -> None:
        findings = ss.screen_text("app/settings.py", "API_KEY = 'your_api_key_here'\n")
        self.assertEqual(ss.highest_level(findings), ss.INFORMATIONAL)
        self.assertFalse(ss.summarize(findings)["blocked"])

    def test_template_file_downgrades_literal_assignment(self) -> None:
        findings = ss.screen_text("config.example.yaml", "CLIENT_SECRET: aZ92kdlsMQ8vbTr4\n")
        self.assertEqual(ss.highest_level(findings), ss.INFORMATIONAL)

    def test_live_sensitive_file_high_entropy_escalates_to_block(self) -> None:
        findings = ss.screen_text(".env", "API_KEY=aZ92kdlsMQ8vbTr4Xy7Wq1Ce5Nh0Pj\n")
        self.assertEqual(ss.highest_level(findings), ss.BLOCK)
        self.assertTrue(
            any(f["rule"] == "secret-assignment-live-high-entropy" for f in findings)
        )

    def test_ordinary_file_literal_assignment_stays_review(self) -> None:
        findings = ss.screen_text("app/settings.py", "API_KEY = 'aZ92kdlsMQ8vbTr4Xy7Wq1'\n")
        self.assertEqual(ss.highest_level(findings), ss.REVIEW)

    def test_synthetic_fixture_paths_downgrade_and_record_origin(self) -> None:
        findings = ss.screen_text(
            "tests/fixtures/security/synthetic_secrets.txt",
            "AKIAABCDEFGHIJKLMNOP\n-----BEGIN PRIVATE KEY-----\n",
            SYNTHETIC_POLICY,
        )
        self.assertEqual(ss.highest_level(findings), ss.INFORMATIONAL)
        self.assertTrue(all(f.get("downgraded_from") for f in findings))
        self.assertFalse(ss.summarize(findings)["blocked"])

    def test_no_finding_ever_retains_the_matched_value(self) -> None:
        secret = "aZ92kdlsMQ8vbTr4Xy7Wq1Ce5Nh0Pj"
        findings = ss.screen_text(".env", f"API_KEY={secret}\n")
        serialized = json.dumps(findings)
        self.assertNotIn(secret, serialized)
        self.assertTrue(all(f["value_retained"] is False for f in findings))

    def test_schema_one_policy_terms_are_treated_as_block(self) -> None:
        findings = ss.screen_text(
            "docs/notes.md", "internal ProjectAtlas reference", {"forbidden_terms": ["ProjectAtlas"]}
        )
        self.assertEqual(ss.highest_level(findings), ss.BLOCK)

    def test_schema_two_review_and_informational_terms_separate(self) -> None:
        policy = {"review_terms": ["StagingHost"], "informational_terms": ["InternalNote"]}
        review = ss.screen_text("docs/a.md", "StagingHost appears", policy)
        info = ss.screen_text("docs/b.md", "InternalNote appears", policy)
        self.assertEqual(ss.highest_level(review), ss.REVIEW)
        self.assertEqual(ss.highest_level(info), ss.INFORMATIONAL)

    def test_allow_paths_suppress_all_findings(self) -> None:
        findings = ss.screen_text(
            "docs/known.md", "-----BEGIN PRIVATE KEY-----", {"allow_paths": ["docs/known.md"]}
        )
        self.assertEqual(findings, [])

    def test_sensitive_filename_alone_is_review_not_block(self) -> None:
        findings = ss.screen_paths(["config/id_rsa"])
        self.assertEqual(ss.highest_level(findings), ss.REVIEW)

    def test_findings_are_deterministically_ordered(self) -> None:
        text = "AKIAABCDEFGHIJKLMNOP\n-----BEGIN PRIVATE KEY-----\nAPI_KEY = 'aZ92kdlsMQ8vbT'\n"
        first = ss.screen_text("app/x.py", text)
        second = ss.screen_text("app/x.py", text)
        self.assertEqual(first, second)
        self.assertEqual(first, sorted(first, key=lambda f: (f["path"], f["rule"], f["level"])))

    def test_summary_declares_no_mutation_and_a_truth_boundary(self) -> None:
        summary = ss.summarize(ss.screen_text("app/x.py", "nothing here"))
        self.assertFalse(summary["mutates_scanned_bytes"])
        self.assertFalse(summary["values_retained"])
        self.assertIn("does not prove", summary["truth_boundary"])

    def test_screening_never_edits_the_scanned_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / ".env"
            body = "API_KEY=aZ92kdlsMQ8vbTr4Xy7Wq1Ce5Nh0Pj\n"
            path.write_text(body, encoding="utf-8")
            ss.screen_text(".env", path.read_text(encoding="utf-8"))
            self.assertEqual(path.read_text(encoding="utf-8"), body)

    def test_entropy_scores_low_for_repetitive_values(self) -> None:
        self.assertLess(ss.shannon_entropy("aaaaaaaaaaaaaaaa"), 1.0)
        self.assertGreater(ss.shannon_entropy("aZ92kdlsMQ8vbTr4Xy7Wq1Ce5Nh0Pj"), 4.0)

    def test_boundary_classifier_exposes_tiered_screening(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / ".env").write_text("API_KEY=aZ92kdlsMQ8vbTr4Xy7Wq1Ce5Nh0Pj\n", encoding="utf-8")
            result = classify_confidentiality_boundaries(root, [".env"])
            self.assertIn("tiered_screening", result)
            self.assertEqual(result["highest_confidentiality_level"], ss.BLOCK)
            self.assertFalse(result["tiered_screening"]["values_retained"])

    def test_packaged_policy_declares_tier_levels(self) -> None:
        policy = json.loads((FORGE_ROOT / "CONFIDENTIALITY-POLICY.json").read_text(encoding="utf-8"))
        self.assertEqual(policy["schema"], 2)
        self.assertEqual(policy["levels"], [ss.BLOCK, ss.REVIEW, ss.INFORMATIONAL])
        self.assertTrue(policy["never_mutates_scanned_bytes"])

    def test_packaged_policy_ships_no_private_denylist(self) -> None:
        policy = json.loads((FORGE_ROOT / "CONFIDENTIALITY-POLICY.json").read_text(encoding="utf-8"))
        for key in ("forbidden_terms", "review_terms", "informational_terms", "forbidden_sha256"):
            self.assertEqual(policy.get(key, []), [], f"{key} must ship empty")

    def test_repository_fixtures_screen_as_informational_only(self) -> None:
        policy = json.loads((FORGE_ROOT / "CONFIDENTIALITY-POLICY.json").read_text(encoding="utf-8"))
        fixture = FORGE_ROOT / "tests" / "fixtures" / "security" / "synthetic_secrets.txt"
        findings = ss.screen_text(
            "tests/fixtures/security/synthetic_secrets.txt",
            fixture.read_text(encoding="utf-8"),
            policy,
        )
        self.assertTrue(findings)
        self.assertEqual(ss.highest_level(findings), ss.INFORMATIONAL)

    def test_detector_corpus_paths_are_declared_synthetic(self) -> None:
        policy = json.loads((FORGE_ROOT / "CONFIDENTIALITY-POLICY.json").read_text(encoding="utf-8"))
        declared = policy["synthetic_fixture_paths"]
        self.assertIn("tests/fixtures/security", declared)
        self.assertIn("tests/test_secret_screening.py", declared)

    def test_this_module_screens_as_informational_under_packaged_policy(self) -> None:
        policy = json.loads((FORGE_ROOT / "CONFIDENTIALITY-POLICY.json").read_text(encoding="utf-8"))
        body = (FORGE_ROOT / "tests" / "test_secret_screening.py").read_text(encoding="utf-8")
        findings = ss.screen_text("tests/test_secret_screening.py", body, policy)
        self.assertEqual(ss.highest_level(findings), ss.INFORMATIONAL)

    def test_token_count_identifiers_are_not_credentials(self) -> None:
        noisy = (
            "provider_input_tokens: object | None = None\n"
            "output_tokens = _nonnegative_int(provider_output_tokens)\n"
            "heuristic_resume_tokens = max(0, round(chars / 4))\n"
        )
        self.assertEqual(ss.screen_text("app/telemetry.py", noisy), [])

    def test_bare_dict_key_assignment_is_not_a_credential(self) -> None:
        code = 'key = (str(evidence.get("matrix_id", "")), str(evidence.get("scenario", "")))\n'
        self.assertEqual(ss.screen_text("app/matrix.py", code), [])

    def test_dotted_and_call_references_are_not_credential_literals(self) -> None:
        code = "api_token = self.settings.api_token\nclient_secret = os.getenv('CLIENT_SECRET')\n"
        self.assertEqual(ss.highest_level(ss.screen_text("app/x.py", code)), ss.INFORMATIONAL)

    def test_unquoted_env_style_secret_is_still_detected(self) -> None:
        findings = ss.screen_text(".env", "API_KEY=aZ92kdlsMQ8vbTr4Xy7Wq1Ce5Nh0Pj\n")
        self.assertEqual(ss.highest_level(findings), ss.BLOCK)

    def test_forge_source_tree_screens_clean_under_packaged_policy(self) -> None:
        policy = json.loads((FORGE_ROOT / "CONFIDENTIALITY-POLICY.json").read_text(encoding="utf-8"))
        offenders: list[str] = []
        for path in sorted((FORGE_ROOT / "emotivus_forge").rglob("*.py")):
            relative = path.relative_to(FORGE_ROOT).as_posix()
            findings = ss.screen_text(relative, path.read_text(encoding="utf-8"), policy)
            if ss.highest_level(findings) in (ss.BLOCK, ss.REVIEW):
                offenders.append(relative)
        self.assertEqual(offenders, [], "engine source must screen clean at BLOCK and REVIEW")

    def test_legacy_vault_detector_corpus_is_declared_synthetic(self) -> None:
        policy = json.loads((FORGE_ROOT / "CONFIDENTIALITY-POLICY.json").read_text(encoding="utf-8"))
        self.assertIn(
            "capability_vault/legacy_1_4_1/tests/test_forge_core.py",
            policy["synthetic_fixture_paths"],
        )

    def test_declared_synthetic_paths_are_not_stale(self) -> None:
        """A declared exemption must point at real content in this edition.

        Public editions prune development-only trees such as capability_vault, so an
        exemption whose top-level directory is absent is edition-pruned, not stale. If
        the top-level directory IS present, the declared path must exist, which is what
        catches a genuinely stale exemption.
        """
        policy = json.loads((FORGE_ROOT / "CONFIDENTIALITY-POLICY.json").read_text(encoding="utf-8"))
        declared_paths = policy["synthetic_fixture_paths"]
        self.assertTrue(declared_paths, "policy must declare its detector corpus")
        resolved = 0
        for declared in declared_paths:
            top = (FORGE_ROOT / declared.split("/", 1)[0])
            if not top.exists():
                continue  # edition-pruned, not stale
            self.assertTrue(
                (FORGE_ROOT / declared).exists(),
                f"declared synthetic path {declared} is stale; a stale exemption hides nothing safely",
            )
            resolved += 1
        self.assertGreater(resolved, 0, "at least one declared exemption must resolve in every edition")

    def test_interpolated_values_are_not_hardcoded_credentials(self) -> None:
        code = (
            'token = f"{os.getpid()}-{time.time_ns()}"\n'
            'api_key = "prefix-{}".format(run_id)\n'
        )
        self.assertEqual(ss.screen_text("app/selftest.py", code), [])
