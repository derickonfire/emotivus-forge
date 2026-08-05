# Project Configuration Reference

Forge stores each project's active contract in `.emotivus-forge.json`.

## `project`

`name` labels reports and package names. `kind` records whether initialization found existing source. `risk_preset` and `deployment_target` record the selected initial-run posture.

## `adapters`

A list containing any of `php`, `javascript`, `css`, `apache`, `node`, and `python`. Adapters activate built-in syntax and environment checks.

## `paths`

- `exclude`: source paths excluded from audit fingerprints and adapter scans.
- `reports`: JSON and text evidence directory.
- `baseline`: accepted warning/info fingerprint file.
- `deploy_ignore`: optional ignore rules read during packaging.

## `runtime`

Each runtime has `required` and `expected`. A required unavailable runtime is an error. An expected version mismatch is an error.

## `quality`

- `require_tests`: warns when no test source is detected.
- `require_documentation`: warns when no project README is detected.
- `fail_on_new_warnings`: promotes newly introduced warnings into a failed audit while continuing to distinguish legacy warnings.

## `versioning`

- `enabled`: activates the release identity gate.
- `status`: must be `release` for the release profile.
- `baseline_version`: confirmed starting version.
- `target_version`: version being delivered; must differ from the baseline.
- `package_version`: version used in package naming.
- `package_version_rule`: `same`, `remove_dots`, or `none`.
- `source.path` and `source.regex`: optional runtime source file and a regex whose first capture group must equal the target.
- `migration.required` and `migration.path`: optional mandatory migration evidence.

## `packaging`

- `output`: supports `{project}` and `{version}`.
- `required_files`: every listed file must enter the package.
- `exclude`: normal exclusions that may be changed by later `.deployignore` rules.
- `immutable_exclude`: exclusions that ignore negation cannot reverse.
- `hard_exclude`: sensitive paths that block packaging if reintroduced.
- `secret_scan`: detects private keys and likely embedded credential literals.

## `profiles`

Each profile controls whether it runs the audit, release gate, package dry run, and which command groups it executes.

## `commands`

Commands contain an `id`, argument-array `command`, and `timeout`. Supported placeholders are `{project}`, `{forge}`, `{python}`, `{php}`, and `{node}`.


## `initialization`

Records the configuration timestamp, selected preset, whether inherited advisories were baselined, and the answers schema.

## `verification`

Lists live systems that require human or staging verification because static analysis cannot prove them.

## `tool_migration`

Records the selected existing-tool mode, discovered ecosystem registry, adopted canonical commands, inventory counts, and any quarantined files. Adopted source, datasets, fixtures, and generated state remain host-authoritative and in place unless an explicit confirmed remove action moves a narrow standalone replacement candidate into `.forge/legacy-tools/`.

## v1.0.4 first-contact fields

```json
{
  "quality": {
    "test_entry_points": ["tools/smoke.php"]
  },
  "environment": {
    "required_executables": ["mariadb"],
    "required_env": ["APP_TEST_DB_HOST"],
    "expected_layout": [
      {"path": "../Planning", "kind": "directory", "required": true}
    ]
  },
  "continuity": {
    "objective_sources": ["ACTIVE-BUILD-PROMPT.md", "BACKLOG.md"],
    "next_action": "",
    "state_archive": "Forge-State.zip"
  },
  "isolation": {
    "mode": "host",
    "forge_root": "Emotivus-Forge",
    "host_scanner_excludes": ["Emotivus-Forge", ".forge"]
  },
  "packaging": {
    "zero_byte_allow": [".gitkeep", ".keep"]
  }
}
```

`required_env` stores variable names only. Secret values do not belong in Forge configuration or portable state. `expected_layout` paths are resolved relative to the host project root and checked by Forge Doctor.

## v1.0.5 evidence fields

Commands may declare an execution-evidence contract:

```json
{
  "id": "host.full-gate",
  "command": ["bash", "tools/run_all_checks.sh", "."],
  "required": true,
  "evidence": {
    "protocol": "markers",
    "required": true,
    "allow_skip": false,
    "required_fields": ["status", "assertions", "skips", "migrations"]
  }
}
```

Marker output uses `FORGE_STATUS`, `FORGE_ASSERTIONS`, `FORGE_SKIPS`, `FORGE_MIGRATIONS`, and `FORGE_EXECUTED`. Ordinary commands may continue using the default exit-code protocol.

Project-level evidence configuration:

```json
{
  "evidence": {
    "history_path": ".forge/evidence/execution-history.json",
    "failure_dir": ".forge/failures",
    "history_limit": 500,
    "anomaly": {
      "enabled": true,
      "minimum_samples": 3,
      "fast_ratio": 0.6
    }
  }
}
```

Timing comparisons are keyed by check ID, command fingerprint, and environment signature. Timing alone is advisory. Evidence-count regression can make an anomaly blocking.

## maintenance

- `maintenance.update.preserve_paths`: Forge-relative private extension paths retained across upgrades.
- `maintenance.update.post_update_profile`: `quick`, `section`, or `release` Gate run by the incoming Forge before the upgrade is accepted.
- `maintenance.update.backup_limit`: retained installation backups.
- `maintenance.doctor.allowed_types`: reversible repair types permitted for explicit proposals.
- `maintenance.doctor.repair_specs`: optional declared filesystem repairs.
- `maintenance.ci.provider` and `generated`: last CI Bridge selection and generated paths.
- `maintenance.delivery.*`: internal package names, output pattern, and internal-source exclusions.

Expected-layout entries may include a `repair` object, for example `{"type":"create-directory"}`. The repair is only proposed; applying it still requires explicit confirmation.

## v1.2 controlled-change fields

Configuration schema 5 adds Pivot lifecycle and quality-coverage policy inside the existing `project_memory` section:

```json
{
  "project_memory": {
    "mode": "development",
    "traceability": {
      "release_requires_quality_coverage": true
    },
    "pivot": {
      "require_release_gate_on_complete": true,
      "checkpoint_profile_order": ["release", "section", "quick"],
      "allowed_modes": ["exploration", "transition", "development", "release"],
      "default_entry_mode": "exploration"
    }
  }
}
```

`mode` is the current controlled-change mode. Pivot activation sets the configured entry mode; only an explicit Pivot mode action changes it.

Plans include `quality_targets`, `quality_evidence`, and derived `quality_coverage`. Evidence values are durable references such as `gate:section`, `lab:critical-flow`, `manual:review-id`, `external:report-id`, or project-relative files.

Standards are Ledger records with `type: "standard"`. Active standard records require a source, version, authority, and scope. Plans refer to standards by Ledger ID so replacements and supersession remain traceable.


## v1.2.1 Lab truthfulness fields

Configuration schema 6 adds explicit Lab evidence policy and internal-delivery cache hygiene:

```json
{
  "lab": {
    "minimum_evidence_by_profile": {
      "quick": "connectivity-smoke",
      "section": "content-readiness",
      "release": "content-readiness"
    }
  },
  "maintenance": {
    "delivery": {
      "exclude": ["__pycache__", "*.pyc", "*.pyo", ".pytest_cache", ".mypy_cache", ".ruff_cache"]
    }
  }
}
```

Lab recipes can declare prerequisites, content assertions, stateful journeys, evidence boundaries, and an evidence level. Forge reports the strongest level actually proven; a recipe cannot overstate its claim merely by naming a stronger level.


## v1.3 runtime-proof fields

Configuration schema 7 adds project-owned runtime contracts inside Prove → Lab:

```json
{
  "runtime_proof": {
    "enabled": true,
    "contracts_path": ".forge/contracts/runtime-contracts.json",
    "output_dir": ".forge/runtime",
    "required_kinds_by_profile": {"quick": [], "section": [], "release": []},
    "minimum_boundary_by_profile": {
      "quick": "local-process",
      "section": "disposable-local-environment",
      "release": "release-equivalent"
    }
  }
}
```

No runtime-contract kind is mandatory by default. Projects deliberately assign contracts and required kinds to Gate profiles. Authorization contracts require an explicit actor/action/target matrix, including privilege administration and session revocation. Migration contracts declare predecessor and schema-capability relationships.

## `release_proof`

- `claim_level`: strongest release claim requested.
- `auto_minimum`: raises the minimum claim when executable surfaces, persisted state, or target deployment evidence require it.
- `surfaces`: project-declared additions or corrections to the discovered surface inventory.
- `deployment_states`: required persisted-state-plus-current-code scenarios and bound PASS evidence.
- `scan_documentation_claims`: reports one-time verification claims that lack recurring evidence.

## `environment.target`

Declares target runtime versions, required extensions, required services, and bound release-equivalent or production-observed evidence. It is separate from Doctor, which measures the current machine.

## `delivery_proof`

- `manifest_path`: first-class artifact provenance registry.
- `output`: exact final handoff bundle path.
- `scan_roots` and `detect_patterns`: locations and shapes used to detect undeclared deliverables.

Generated artifacts require a Forge-observed command, explicit inputs, generator fingerprint, execution receipt, input fingerprint, and output hash. Frozen artifacts require a reviewed reason.
