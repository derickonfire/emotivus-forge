from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

from .utils import normalize_rel, tree_snapshot, utc_now, write_json

DEPLOY_MANIFEST_NAMES = (
    "DEPLOY-MANIFEST.txt", "DEPLOY-MANIFEST.json", "FORGE-DEPLOY-MANIFEST.json",
    "deployment-manifest.json", "manifest.json",
)
DEV_AUTHORITIES = {
    "planning": ("Planning", "planning", "BACKLOG.md", "ACTIVE-BUILD-PROMPT.md"),
    "release": ("Release", "release"),
    "tests": ("tests", "test", "spec"),
    "tools": ("tools", "scripts", "bin"),
}


def _exists_any(root: Path, names: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for name in names:
        path = root / name
        if path.exists():
            found.append(normalize_rel(name))
    return found


def _manifest_paths(root: Path) -> list[str]:
    result: list[str] = []
    for name in DEPLOY_MANIFEST_NAMES:
        if (root / name).is_file():
            result.append(name)
    for pattern in ("*DEPLOY*MANIFEST*", "*deploy*manifest*", "Release/*MANIFEST*", "release/*manifest*"):
        for path in root.glob(pattern):
            if path.is_file():
                rel = path.relative_to(root).as_posix()
                if rel not in result:
                    result.append(rel)
    return sorted(result)


def classify_workspace(project_root: Path, forge_root: Path | None = None) -> dict[str, Any]:
    root = project_root.resolve()
    authorities = {key: _exists_any(root, names) for key, names in DEV_AUTHORITIES.items()}
    manifests = _manifest_paths(root)
    internal_manifest = (root / "FORGE-INTERNAL-DELIVERY-MANIFEST.json").is_file()
    forge_state = any(root.glob("Forge-State*.zip"))
    has_diffs = (root / "Diffs").exists() or (root / "diffs").exists()
    dev_count = sum(bool(values) for values in authorities.values())
    missing = [key for key, values in authorities.items() if not values]
    evidence: list[str] = []
    if manifests:
        evidence.append("deployment manifest present: " + ", ".join(manifests[:5]))
    for key, values in authorities.items():
        if values:
            evidence.append(f"{key} authority present: {', '.join(values[:4])}")
    forge_core = (root / "FORGE-MANIFEST.json").is_file() and (root / "forge.py").is_file() and (root / "emotivus_forge").is_dir()
    has_tests_and_tools = bool(authorities["tests"] and authorities["tools"])
    if forge_core:
        kind, confidence = "development-source", "high"
        evidence.append("Forge Core source manifest and entry points present")
    elif internal_manifest:
        kind, confidence = "internal-delivery", "high"
    elif manifests and dev_count <= 1:
        kind, confidence = "deployment-package", "high"
    elif has_tests_and_tools and has_diffs:
        kind, confidence = "reconstructed-development-source", "medium"
        evidence.append("diff/reconstruction material present")
    elif has_tests_and_tools:
        kind, confidence = "development-source", "high"
    elif dev_count == len(DEV_AUTHORITIES):
        kind, confidence = "development-source", "high"
    elif manifests and dev_count >= 2:
        kind, confidence = "mixed-workspace", "medium"
    elif dev_count >= 2:
        kind, confidence = "partial-development-source", "medium"
    elif manifests:
        kind, confidence = "release-candidate", "medium"
    else:
        kind, confidence = "unknown", "low"

    allowed = ["audit", "understand", "doctor", "graph", "package-inspection"]
    restricted: list[str] = []
    if kind in {"development-source", "reconstructed-development-source", "internal-delivery"}:
        allowed += ["development", "change-planning", "regression-work", "release-preparation"]
    elif kind in {"deployment-package", "release-candidate"}:
        allowed += ["deployment-reconciliation", "acceptance-rehearsal"]
        restricted += ["full-development", "regression-modification", "release-certification"]
    else:
        allowed += ["limited-analysis"]
        restricted += ["release-certification"]

    return {
        "schema": 1,
        "generated_utc": utc_now(),
        "classification": kind,
        "confidence": confidence,
        "authorities": authorities,
        "missing_authorities": missing,
        "manifests": manifests,
        "portable_state_present": forge_state,
        "evidence": evidence,
        "allowed_activities": allowed,
        "restricted_activities": restricted,
    }


def _json_requirement(path: Path, key_paths: tuple[tuple[str, ...], ...]) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    for keys in key_paths:
        value: Any = data
        for key in keys:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip().lstrip("v>=~^ ")
    return ""


def infer_runtime_requirements(project_root: Path) -> dict[str, dict[str, Any]]:
    root = project_root.resolve()
    result: dict[str, dict[str, Any]] = {
        "php": {"expected": "", "source": "", "confidence": ""},
        "node": {"expected": "", "source": "", "confidence": ""},
        "python": {"expected": "", "source": "", "confidence": ""},
    }
    composer = root / "composer.json"
    if composer.is_file():
        value = _json_requirement(composer, (("config", "platform", "php"), ("require", "php")))
        if value:
            match = re.search(r"(\d+\.\d+)", value)
            result["php"] = {"expected": match.group(1) if match else value, "source": "composer.json", "confidence": "high"}
    for rel in ("tools/release.json", "release.json", "Release/release.json", "config/release.json"):
        path = root / rel
        if path.is_file() and not result["php"]["expected"]:
            value = _json_requirement(path, (("php_target",), ("php_version",), ("runtime", "php"), ("php", "expected")))
            if value:
                match = re.search(r"(\d+\.\d+)", value)
                result["php"] = {"expected": match.group(1) if match else value, "source": rel, "confidence": "high"}
    package = root / "package.json"
    if package.is_file():
        value = _json_requirement(package, (("engines", "node"),))
        if value:
            match = re.search(r"(\d+)(?:\.(\d+))?", value)
            expected = f"{match.group(1)}.{match.group(2) or '0'}" if match else value
            result["node"] = {"expected": expected, "source": "package.json#engines.node", "confidence": "high"}
    nvmrc = root / ".nvmrc"
    if nvmrc.is_file() and not result["node"]["expected"]:
        value = nvmrc.read_text(encoding="utf-8", errors="replace").strip().lstrip("v")
        if value:
            result["node"] = {"expected": value, "source": ".nvmrc", "confidence": "high"}
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            value = data.get("project", {}).get("requires-python", "") if isinstance(data, dict) else ""
        except (OSError, tomllib.TOMLDecodeError):
            value = ""
        match = re.search(r"(\d+\.\d+)", str(value))
        if match:
            result["python"] = {"expected": match.group(1), "source": "pyproject.toml#project.requires-python", "confidence": "high"}

    docs = [root / name for name in ("README.md", "README.txt", "HANDOVER.md", "docs/README.md")]
    patterns = {
        "php": re.compile(r"\bPHP\s*(?:version\s*)?(\d+\.\d+)\b", re.I),
        "node": re.compile(r"\bNode(?:\.js)?\s*(?:version\s*)?v?(\d+(?:\.\d+)?)\b", re.I),
        "python": re.compile(r"\bPython\s*(?:version\s*)?(\d+\.\d+)\b", re.I),
    }
    for path in docs:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")[:300_000]
        for runtime, pattern in patterns.items():
            if result[runtime]["expected"]:
                continue
            match = pattern.search(text)
            if match:
                result[runtime] = {"expected": match.group(1), "source": path.relative_to(root).as_posix(), "confidence": "medium"}
    return result


def infer_work_scope(project_root: Path, objective_sources: list[str] | None = None) -> dict[str, Any]:
    root = project_root.resolve()
    sources = objective_sources or ["Planning/ACTIVE-BUILD-PROMPT.md", "ACTIVE-BUILD-PROMPT.md", "BACKLOG.md"]
    selected = ""
    text = ""
    for rel in sources:
        path = root / rel
        if path.is_file():
            selected = normalize_rel(rel)
            text = path.read_text(encoding="utf-8", errors="replace")[:500_000]
            break
    lowered = text.lower()
    mode = "development"
    coding_allowed = True
    confidence = "low" if not text else "medium"
    reason = "No explicit active-scope restriction was detected."
    if any(token in lowered for token in ("no additional approved coding scope", "no approved coding scope", "source implementation and static release package are complete")):
        coding_allowed = False
        confidence = "high"
        reason = "The active scope explicitly states that no additional coding is approved."
        if "acceptance" in lowered or "staging" in lowered:
            mode = "acceptance"
        elif "deployment" in lowered:
            mode = "deployment"
        else:
            mode = "maintenance"
    elif "staging acceptance" in lowered or "acceptance ledger" in lowered:
        mode = "acceptance"
        confidence = "medium"
        reason = "The active scope centers on staging acceptance."
    elif "incident" in lowered:
        mode = "incident-response"
    return {
        "schema": 1,
        "mode": mode,
        "coding_allowed": coding_allowed,
        "source": selected,
        "confidence": confidence,
        "reason": reason,
    }


def packaging_policy_contradictions(project_root: Path, config: dict[str, Any]) -> list[dict[str, str]]:
    root = project_root.resolve()
    ignore_path = root / config.get("paths", {}).get("deploy_ignore", ".deployignore")
    if not ignore_path.is_file():
        return []
    raw_lines = ignore_path.read_text(encoding="utf-8", errors="replace").splitlines()
    rules = [line.strip().replace("\\", "/") for line in raw_lines if line.strip() and not line.lstrip().startswith("#") and not line.strip().startswith("!")]
    manifest_text = ""
    manifest_sources: list[str] = []
    for rel in _manifest_paths(root):
        path = root / rel
        try:
            manifest_text += "\n" + path.read_text(encoding="utf-8", errors="replace")[:5_000_000]
            manifest_sources.append(rel)
        except OSError:
            pass
    required = [normalize_rel(str(item)) for item in config.get("packaging", {}).get("required_files", [])]
    contradictions: list[dict[str, str]] = []
    for rule in rules:
        clean = rule.lstrip("/")
        if any(ch in clean for ch in "*?["):
            continue
        prefix = clean.rstrip("/") + "/" if clean.endswith("/") else clean
        # Ordinary deployment exclusions are overridden by packaging.required_files.
        # Immutable and hard exclusions remain authoritative in the packager itself.
        if manifest_text and clean.endswith("/") and re.search(rf"(?m)(?:^|[\s|]){re.escape(prefix)}[^\s|]+", manifest_text):
            contradictions.append({"rule": rule, "source": str(ignore_path.relative_to(root)), "conflict": ", ".join(manifest_sources), "reason": "prior deployment manifest contains artifacts under the excluded directory"})
    unique = {(item["rule"], item["conflict"], item["reason"]): item for item in contradictions}
    return list(unique.values())



def build_source_completeness(project_root: Path, forge_root: Path | None, workspace: dict[str, Any]) -> dict[str, Any]:
    root = project_root.resolve()
    excludes = ["Emotivus-Forge", ".forge", ".git", "deploy", "node_modules", "vendor"]
    snapshot = tree_snapshot(root, excludes, forge_root)
    authorities = workspace.get("authorities", {})
    status = "complete" if workspace.get("classification") in {"development-source", "internal-delivery"} else "reconstructed" if workspace.get("classification") == "reconstructed-development-source" else "incomplete"
    reconstruction: list[str] = []
    for name in ("Diffs", "diffs", "HANDOVER.md", "README-EXPORT.md"):
        if (root / name).exists():
            reconstruction.append(name)
    return {
        "schema": 1,
        "generated_utc": utc_now(),
        "status": status,
        "workspace_classification": workspace.get("classification", "unknown"),
        "file_count": len(snapshot),
        "tree_snapshot": snapshot,
        "authorities": authorities,
        "missing_authorities": workspace.get("missing_authorities", []),
        "reconstruction_evidence": reconstruction,
        "evidence_boundary": "development-source",
    }

def write_provenance_reports(project_root: Path, workspace: dict[str, Any], runtime: dict[str, Any], scope: dict[str, Any], source_completeness: dict[str, Any] | None = None) -> dict[str, str]:
    root = project_root.resolve()
    out = root / ".forge" / "provenance"
    write_json(out / "workspace.json", workspace)
    write_json(out / "runtime-requirements.json", {"schema": 1, "generated_utc": utc_now(), "runtimes": runtime})
    write_json(out / "work-scope.json", scope)
    if source_completeness is not None:
        write_json(out / "development-source-manifest.json", source_completeness)
    lines = [
        "# Forge Workspace Provenance", "",
        f"- Classification: **{workspace['classification']}**",
        f"- Confidence: **{workspace['confidence']}**",
        f"- Missing authorities: {', '.join(workspace['missing_authorities']) or 'none'}",
        f"- Work mode: **{scope['mode']}**",
        f"- Coding allowed by active scope: **{scope['coding_allowed']}**",
        f"- Scope source: `{scope['source'] or 'not detected'}`", "",
        "## Evidence", "",
    ]
    lines.extend(f"- {item}" for item in workspace.get("evidence", []))
    lines.extend(["", "## Runtime requirements", ""])
    for name, item in runtime.items():
        lines.append(f"- **{name}**: {item.get('expected') or 'not detected'}" + (f" (`{item.get('source')}`; {item.get('confidence')})" if item.get('source') else ""))
    lines.extend(["", "## Allowed activities", ""] + [f"- {item}" for item in workspace.get("allowed_activities", [])])
    if workspace.get("restricted_activities"):
        lines.extend(["", "## Restricted activities", ""] + [f"- {item}" for item in workspace["restricted_activities"]])
    (out / "workspace.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {"workspace_json": str(out / "workspace.json"), "workspace_md": str(out / "workspace.md"), "runtime": str(out / "runtime-requirements.json"), "scope": str(out / "work-scope.json"), "source_manifest": str(out / "development-source-manifest.json") if source_completeness is not None else ""}
