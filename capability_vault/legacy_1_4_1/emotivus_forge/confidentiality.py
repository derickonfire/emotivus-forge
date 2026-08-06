from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .security import has_private_key_bytes, has_secret_assignment_bytes
from .utils import utc_now, write_json

TEXT_SUFFIXES = {
    ".py", ".php", ".phtml", ".inc", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
    ".css", ".scss", ".sass", ".less", ".html", ".htm", ".json", ".yml", ".yaml",
    ".toml", ".ini", ".cfg", ".conf", ".md", ".txt", ".xml", ".sql", ".sh", ".bash",
}
ARCHIVE_SUFFIXES = {".zip"}
DEFAULT_EXCLUDES = {".git", ".forge", "deploy", "dist", "build", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SENSITIVE_PATH_PATTERNS = (
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa", "id_dsa", "id_ecdsa",
    "id_ed25519", "credentials.json", "service-account*.json", "secrets.*", "*backup*.sql",
    "*dump*.sql", "*database*.sql", "*.sqlite", "*.sqlite3",
)
POSIX_HOME_RE = re.compile(rb"/(?:home|Users)/[^/\s\x00]+/")
WINDOWS_HOME_RE = re.compile(rb"[A-Za-z]:\\Users\\[^\\\s\x00]+\\")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalized_text_sha256(data: bytes) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return ""
    normalized = "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")).strip() + "\n"
    return _sha256(normalized.encode("utf-8"))


def _load_policy(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"schema": 1}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not read confidentiality policy {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema", 1) != 1:
        raise RuntimeError("confidentiality policy must be a schema-1 JSON object")
    return payload


def _rules(values: Any, prefix: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    if not isinstance(values, list):
        return result
    for index, raw in enumerate(values, 1):
        if isinstance(raw, str) and raw:
            result.append((f"{prefix}-{index}", raw))
        elif isinstance(raw, dict):
            value = str(raw.get("value", ""))
            if value:
                result.append((str(raw.get("id") or f"{prefix}-{index}"), value))
    return result


def _allowed(path: str, policy: dict[str, Any]) -> bool:
    return any(fnmatch.fnmatch(path, str(pattern)) for pattern in policy.get("allow_paths", []) if str(pattern))


def _finding(path: str, rule_id: str, kind: str, *, archive: str = "") -> dict[str, str]:
    payload = {"path": path, "rule_id": rule_id, "kind": kind}
    if archive:
        payload["archive"] = archive
    return payload


def _scan_bytes(path: str, data: bytes, policy: dict[str, Any], *, archive: str = "") -> list[dict[str, str]]:
    if _allowed(path, policy):
        return []
    findings: list[dict[str, str]] = []
    lowered_path = path.lower()
    for pattern in SENSITIVE_PATH_PATTERNS:
        if fnmatch.fnmatch(lowered_path, pattern.lower()) or fnmatch.fnmatch(PurePosixPath(lowered_path).name, pattern.lower()):
            findings.append(_finding(path, "generic-sensitive-path", "sensitive-path", archive=archive))
            break
    fixture_paths = [str(item) for item in policy.get("synthetic_fixture_paths", [])]
    if has_private_key_bytes(data, path, fixture_paths):
        findings.append(_finding(path, "generic-private-key", "secret-material", archive=archive))
    if has_secret_assignment_bytes(data, path, fixture_paths):
        findings.append(_finding(path, "generic-secret-assignment", "secret-material", archive=archive))
    if POSIX_HOME_RE.search(data) or WINDOWS_HOME_RE.search(data):
        findings.append(_finding(path, "generic-absolute-user-path", "host-identity", archive=archive))

    digest = _sha256(data)
    normalized_digest = _normalized_text_sha256(data)
    forbidden_hashes = {value.lower(): rule_id for rule_id, value in _rules(policy.get("forbidden_sha256"), "private-hash")}
    forbidden_normalized = {value.lower(): rule_id for rule_id, value in _rules(policy.get("forbidden_normalized_sha256"), "private-normalized-hash")}
    if digest.lower() in forbidden_hashes:
        findings.append(_finding(path, forbidden_hashes[digest.lower()], "private-content-hash", archive=archive))
    if normalized_digest and normalized_digest.lower() in forbidden_normalized:
        findings.append(_finding(path, forbidden_normalized[normalized_digest.lower()], "private-normalized-content-hash", archive=archive))

    if Path(path).suffix.lower() in TEXT_SUFFIXES or not Path(path).suffix:
        lowered = data.lower()
        for rule_id, value in _rules(policy.get("forbidden_terms"), "private-term"):
            encoded = value.encode("utf-8", errors="ignore").lower()
            if encoded and encoded in lowered:
                findings.append(_finding(path, rule_id, "private-term", archive=archive))
        for rule_id, pattern in _rules(policy.get("forbidden_path_patterns"), "private-path"):
            if fnmatch.fnmatch(path, pattern):
                findings.append(_finding(path, rule_id, "private-path", archive=archive))
    return findings


def _iter_files(root: Path, paths: Iterable[Path] | None = None) -> Iterable[Path]:
    if paths is not None:
        for path in paths:
            candidate = path.resolve()
            if candidate.is_file() and not candidate.is_symlink():
                yield candidate
        return
    for current, dir_names, file_names in os.walk(root):
        current_path = Path(current)
        dir_names[:] = [name for name in sorted(dir_names) if name not in DEFAULT_EXCLUDES]
        for name in sorted(file_names):
            path = current_path / name
            if path.is_file() and not path.is_symlink():
                yield path


def _scan_zip_bytes(data: bytes, *, archive_label: str, policy: dict[str, Any], depth: int = 0, max_depth: int = 4) -> tuple[list[dict[str, str]], int]:
    findings: list[dict[str, str]] = []
    members = 0
    if depth > max_depth:
        return [_finding(archive_label, "generic-archive-depth-limit", "archive-integrity")], members
    try:
        with zipfile.ZipFile(__import__("io").BytesIO(data)) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                findings.append(_finding(archive_label, "generic-duplicate-archive-path", "archive-integrity"))
            if len(names) > 10000:
                findings.append(_finding(archive_label, "generic-archive-member-limit", "archive-integrity"))
                return findings, members
            total_uncompressed = sum(int(info.file_size) for info in archive.infolist())
            if total_uncompressed > 100 * 1024 * 1024:
                findings.append(_finding(archive_label, "generic-archive-size-limit", "archive-integrity"))
                return findings, members
            for info in archive.infolist():
                if info.is_dir():
                    continue
                members += 1
                member = info.filename.replace("\\", "/")
                nested_label = f"{archive_label}!/{member}"
                if member.startswith("/") or ".." in PurePosixPath(member).parts:
                    findings.append(_finding(member, "generic-unsafe-archive-path", "archive-integrity", archive=archive_label))
                    continue
                member_data = archive.read(info)
                findings.extend(_scan_bytes(member, member_data, policy, archive=archive_label))
                if Path(member).suffix.lower() in ARCHIVE_SUFFIXES:
                    nested_findings, nested_members = _scan_zip_bytes(member_data, archive_label=nested_label, policy=policy, depth=depth + 1, max_depth=max_depth)
                    findings.extend(nested_findings)
                    members += nested_members
    except zipfile.BadZipFile:
        findings.append(_finding(archive_label, "generic-unreadable-archive", "archive-integrity"))
    return findings, members


def scan_zip_archive(archive_path: Path, *, policy_path: Path | None = None, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    archive_path = archive_path.resolve()
    active_policy = policy or _load_policy(policy_path)
    try:
        data = archive_path.read_bytes()
    except OSError as exc:
        finding = _finding(archive_path.name, "generic-unreadable-archive", "archive-integrity")
        return {"status": "FAIL", "archive": str(archive_path), "members_scanned": 0, "findings": [finding], "error": str(exc)}
    findings, members = _scan_zip_bytes(data, archive_label=archive_path.name, policy=active_policy)
    return {"status": "FAIL" if findings else "PASS", "archive": str(archive_path), "members_scanned": members, "findings": findings}


def scan_confidentiality(
    root: Path,
    *,
    policy_path: Path | None = None,
    paths: Iterable[Path] | None = None,
    write: bool = True,
    output_dir: str = ".forge/confidentiality",
    scan_archives: bool = True,
) -> dict[str, Any]:
    root = root.resolve()
    policy = _load_policy(policy_path)
    findings: list[dict[str, str]] = []
    files_scanned = 0
    archive_members_scanned = 0
    resolved_policy = policy_path.resolve() if policy_path is not None else None
    for path in _iter_files(root, paths):
        if resolved_policy is not None and path.resolve() == resolved_policy:
            continue
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = path.name
        data = path.read_bytes()
        files_scanned += 1
        findings.extend(_scan_bytes(relative, data, policy))
        if scan_archives and path.suffix.lower() in ARCHIVE_SUFFIXES:
            archive_result = scan_zip_archive(path, policy=policy)
            archive_members_scanned += int(archive_result.get("members_scanned", 0))
            findings.extend(archive_result.get("findings", []))
    unique = {(item.get("path", ""), item.get("rule_id", ""), item.get("kind", ""), item.get("archive", "")): item for item in findings}
    payload = {
        "schema": 1,
        "generated_utc": utc_now(),
        "status": "FAIL" if unique else "PASS",
        "mode": "metadata-only",
        "files_scanned": files_scanned,
        "archive_members_scanned": archive_members_scanned,
        "findings": [unique[key] for key in sorted(unique)],
        "policy": {
            "external": bool(policy_path),
            "rule_counts": {
                "terms": len(_rules(policy.get("forbidden_terms"), "private-term")),
                "hashes": len(_rules(policy.get("forbidden_sha256"), "private-hash")),
                "normalized_hashes": len(_rules(policy.get("forbidden_normalized_sha256"), "private-normalized-hash")),
                "paths": len(_rules(policy.get("forbidden_path_patterns"), "private-path")),
            },
        },
    }
    if write:
        destination = root / output_dir / "latest.json"
        write_json(destination, payload)
        payload["report"] = str(destination)
    return payload
