#!/usr/bin/env python3
"""Build a deterministic neutral Emotivus Forge ZIP from FORGE-MANIFEST.json."""
from __future__ import annotations

import argparse
import fnmatch
import glob
import hashlib
import json
import os
import stat
import sys
import zipfile
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from emotivus_forge.core import secret_screening  # noqa: E402
from emotivus_forge.core import workspace_integrity  # noqa: E402
from emotivus_forge.core.build_attestation import build_manifest_payload, write_build_manifest  # noqa: E402

EXCLUDED_PARTS = {"__pycache__", ".git", ".release-checks", ".forge", ".runtime", "deploy"}
TEXT_SUFFIXES = {
    ".py", ".json", ".md", ".txt", ".html", ".css", ".js", ".ts", ".tsx",
    ".php", ".xml", ".yaml", ".yml", ".toml", ".sh", ".cmd", ".csv", ".svg",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


def normalized_archive_mode(relative: str) -> int:
    path = Path(relative)
    if relative in {"forge", "frg"} or path.suffix == ".sh":
        return 0o755
    return 0o644


def iter_directory(root: Path, directory: Path) -> Iterable[Path]:
    for current, dir_names, file_names in os.walk(directory):
        current_path = Path(current)
        dir_names[:] = [name for name in sorted(dir_names) if name not in EXCLUDED_PARTS]
        for name in sorted(file_names):
            path = current_path / name
            relative = path.relative_to(root)
            if any(part in EXCLUDED_PARTS for part in relative.parts):
                continue
            if path.is_file() and not path.is_symlink():
                yield path


def expand_manifest(root: Path, patterns: list[str]) -> list[Path]:
    included: dict[str, Path] = {}
    for raw in patterns:
        if not isinstance(raw, str) or not raw.strip():
            raise RuntimeError("manifest path entries must be non-empty strings")
        pattern = raw.strip().replace("\\", "/")
        if pattern.startswith("/") or ".." in Path(pattern).parts:
            raise RuntimeError(f"unsafe Forge path: {pattern}")
        candidate = root / pattern.rstrip("/")
        if pattern.endswith("/"):
            if not candidate.is_dir():
                raise RuntimeError(f"required Forge directory missing: {pattern}")
            matches = list(iter_directory(root, candidate))
        elif any(char in pattern for char in "*?["):
            matches = [Path(item) for item in glob.glob(str(root / pattern), recursive=True)]
            matches = [item for item in matches if item.is_file() and not item.is_symlink()]
            if not matches:
                raise RuntimeError(f"Forge pattern matched no files: {pattern}")
        else:
            if not candidate.is_file():
                raise RuntimeError(f"required Forge file missing: {pattern}")
            matches = [candidate]
        for path in matches:
            relative = path.relative_to(root).as_posix()
            if any(part in EXCLUDED_PARTS for part in Path(relative).parts):
                continue
            included[relative] = path
    return [included[key] for key in sorted(included)]


def _load_policy(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not read confidentiality policy {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"confidentiality policy must be an object: {path}")
    return value


def _combined_policy(root: Path, private_policy: str) -> dict[str, list[str]]:
    policies = [_load_policy(root / "CONFIDENTIALITY-POLICY.json")]
    if private_policy:
        policies.append(_load_policy(Path(private_policy).resolve()))
    result = {
        "forbidden_terms": [],
        "forbidden_sha256": [],
        "forbidden_path_patterns": [],
        "allow_paths": [],
    }
    for policy in policies:
        for key in result:
            values = policy.get(key, [])
            if isinstance(values, list):
                for value in values:
                    text = str(value).strip()
                    if text and text not in result[key]:
                        result[key].append(text)
    return result


def scan_files(root: Path, files: list[Path], policy: dict[str, list[str]]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    forbidden_hashes = set(policy["forbidden_sha256"])
    terms = [term.casefold() for term in policy["forbidden_terms"]]
    allow = set(policy["allow_paths"])
    for path in files:
        relative = path.relative_to(root).as_posix()
        if relative in allow:
            continue
        if any(fnmatch.fnmatch(relative, pattern) for pattern in policy["forbidden_path_patterns"]):
            findings.append({"path": relative, "kind": "forbidden-path"})
        digest = sha256_file(path)
        if digest in forbidden_hashes:
            findings.append({"path": relative, "kind": "forbidden-hash"})
        if terms and path.suffix.lower() in TEXT_SUFFIXES and path.stat().st_size <= 5_000_000:
            try:
                text = path.read_text(encoding="utf-8").casefold()
            except (OSError, UnicodeDecodeError):
                continue
            for term in terms:
                if term in text:
                    findings.append({"path": relative, "kind": "forbidden-term", "term": term})
    return findings


def scan_archive(path: Path, policy: dict[str, list[str]]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    terms = [term.casefold() for term in policy["forbidden_terms"]]
    forbidden_hashes = set(policy["forbidden_sha256"])
    allow = set(policy["allow_paths"])
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            relative = info.filename
            if relative in allow:
                continue
            if any(fnmatch.fnmatch(relative, pattern) for pattern in policy["forbidden_path_patterns"]):
                findings.append({"path": relative, "kind": "forbidden-path"})
            if info.file_size > 20_000_000:
                continue
            content = archive.read(info)
            if hashlib.sha256(content).hexdigest() in forbidden_hashes:
                findings.append({"path": relative, "kind": "forbidden-hash"})
            if terms and Path(relative).suffix.lower() in TEXT_SUFFIXES:
                try:
                    text = content.decode("utf-8").casefold()
                except UnicodeDecodeError:
                    continue
                for term in terms:
                    if term in text:
                        findings.append({"path": relative, "kind": "forbidden-term", "term": term})
    return findings


def _raw_policy(root: Path, private_policy: str) -> dict[str, Any]:
    """Merge the packaged policy with an external private policy, if supplied."""
    merged: dict[str, Any] = {}
    candidates = [root / "CONFIDENTIALITY-POLICY.json"]
    if private_policy:
        candidates.append(Path(private_policy))
    for candidate in candidates:
        try:
            if candidate.is_file():
                data = json.loads(candidate.read_text(encoding="utf-8"))
            else:
                continue
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        for key, value in data.items():
            if isinstance(value, list):
                merged.setdefault(key, [])
                for item in value:
                    if item not in merged[key]:
                        merged[key].append(item)
    return merged


def _screen_selection(root: Path, files: list[Path], raw_policy: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    relatives: list[str] = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        relatives.append(relative)
        if (
            path.suffix.lower() not in secret_screening.TEXT_SUFFIXES
            and path.name.lower() not in secret_screening.EXTENSIONLESS_CREDENTIAL_NAMES
        ):
            continue
        try:
            if path.stat().st_size > 5_000_000:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        findings.extend(secret_screening.screen_text(relative, text, raw_policy))
    findings.extend(secret_screening.screen_paths(relatives, raw_policy))
    return secret_screening.summarize(findings)



def build_package(
    root: Path,
    *,
    manifest_path: Path | str = "FORGE-MANIFEST.json",
    output: Path | str = "deploy/Emotivus-Forge.zip",
    edition: str = "development",
    private_policy: str = "",
    build_manifest_path: Path | str = "",
    fail_on_review: bool = False,
    before_publish: Any = None,
) -> dict[str, Any]:
    """Build one deterministic edition and return exact build facts.

    ``before_publish`` is a development/test hook invoked after every selected file has been read
    into the temporary archive and before the final source-selection recheck. Production CLI use
    never supplies it. This creates a deterministic boundary for concurrent-writer campaigns
    without adding a public command, environment switch, daemon, or background monitor.
    """
    root = Path(root).resolve()
    if edition not in {"development", "public"}:
        raise ValueError(f"unsupported Forge edition: {edition}")
    manifest_path = Path(manifest_path)
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    output = Path(output)
    if not output.is_absolute():
        output = root / output
    build_manifest = Path(build_manifest_path) if build_manifest_path else None
    if build_manifest is not None and not build_manifest.is_absolute():
        build_manifest = root / build_manifest

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("forge_schema") != 1:
        raise RuntimeError("FORGE-MANIFEST.json must use forge_schema 1")
    path_key = "public_paths" if edition == "public" else "canonical_paths"
    patterns = data.get(path_key)
    if not isinstance(patterns, list):
        raise RuntimeError(f"{path_key} must be an array")
    archive_root = str(data.get("archive_root", "Emotivus-Forge")).strip().strip("/\\")
    if not archive_root or ".." in Path(archive_root).parts:
        raise RuntimeError("archive_root must be a safe relative path")
    files = expand_manifest(root, patterns)
    policy = _combined_policy(root, private_policy)
    findings = scan_files(root, files, policy)
    if findings:
        raise RuntimeError(f"confidentiality scan failed with {len(findings)} finding(s): {findings[:5]}")
    raw_policy = _raw_policy(root, private_policy)
    screening = _screen_selection(root, files, raw_policy)
    if screening["blocked"]:
        blocking = [f for f in screening["findings"] if f["level"] == secret_screening.BLOCK]
        raise RuntimeError(f"tiered screening BLOCK on {len(blocking)} finding(s): {blocking[:5]}")
    if fail_on_review and screening["counts"][secret_screening.REVIEW]:
        reviewed = [f for f in screening["findings"] if f["level"] == secret_screening.REVIEW]
        raise RuntimeError(f"strict mode: {len(reviewed)} REVIEW finding(s): {reviewed[:5]}")
    source_selection = workspace_integrity.fingerprint_selection(root, files)

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in files:
                relative = path.relative_to(root).as_posix()
                info = zipfile.ZipInfo(f"{archive_root}/{relative}", ZIP_EPOCH)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | normalized_archive_mode(relative)) << 16
                content = path.read_bytes()
                expected = source_selection["files"].get(relative, {})
                if len(content) != expected.get("size") or hashlib.sha256(content).hexdigest() != expected.get("sha256"):
                    raise RuntimeError(f"selected package source drifted before read: {relative}")
                if edition == "public" and relative == "FORGE-MANIFEST.json":
                    public_manifest = dict(data)
                    public_manifest["state"] = "public-development-preview"
                    public_manifest["edition"] = "public"
                    public_manifest["canonical_paths"] = list(data.get("public_paths", []))
                    content = (json.dumps(public_manifest, indent=2) + "\n").encode("utf-8")
                archive.writestr(info, content)
        if before_publish is not None:
            before_publish(root, list(files), dict(source_selection), temporary)
        workspace_integrity.require_selection_unchanged(root, files, source_selection)
        archive_findings = scan_archive(temporary, policy)
        if archive_findings:
            raise RuntimeError(f"built archive confidentiality scan failed: {archive_findings[:5]}")
        temporary.replace(output)
        if build_manifest is not None:
            payload = build_manifest_payload(
                output,
                version=str(data.get("version", "")),
                edition=edition,
                source_fingerprint=str(source_selection.get("fingerprint", "")),
                source_file_count=int(source_selection.get("file_count", 0)),
                forge_manifest_sha256=sha256_file(manifest_path),
            )
            write_build_manifest(build_manifest, payload)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "schema": 1,
        "edition": edition,
        "file_count": len(files),
        "output": str(output),
        "build_manifest": str(build_manifest) if build_manifest is not None else "",
        "screening": screening,
        "source_fingerprint": source_selection["fingerprint"],
        "sha256": sha256_file(output),
        "bytes": output.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--manifest", default="FORGE-MANIFEST.json")
    parser.add_argument("--output", default="deploy/Emotivus-Forge.zip")
    parser.add_argument("--edition", choices=("development", "public"), default="development")
    parser.add_argument("--private-policy", default=os.environ.get("FORGE_PRIVATE_POLICY", ""))
    parser.add_argument("--build-manifest", default="", help="write a deterministic exact-package build manifest for optional external signing")
    parser.add_argument("--fail-on-review", action="store_true",
                        help="treat REVIEW screening findings as blocking")
    args = parser.parse_args()
    try:
        result = build_package(
            Path(args.root),
            manifest_path=args.manifest,
            output=args.output,
            edition=args.edition,
            private_policy=args.private_policy,
            build_manifest_path=args.build_manifest,
            fail_on_review=args.fail_on_review,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
        print(f"FORGE PACKAGE: BLOCKED — {exc}", file=os.sys.stderr)
        return 1
    print(f"FORGE PACKAGE ({args.edition}): PASS")
    print(f"Files: {result['file_count']}")
    print(f"Output: {result['output']}")
    print("Confidentiality: PASS")
    counts = result["screening"]["counts"]
    print(
        "Screening: BLOCK {b} / REVIEW {r} / INFORMATIONAL {i}".format(
            b=counts[secret_screening.BLOCK],
            r=counts[secret_screening.REVIEW],
            i=counts[secret_screening.INFORMATIONAL],
        )
    )
    for finding in result["screening"]["findings"]:
        if finding["level"] == secret_screening.REVIEW:
            print(f"  REVIEW {finding['path']} — {finding['descriptor']}")
    print(f"Source fingerprint: {result['source_fingerprint']}")
    if result["build_manifest"]:
        print(f"Build manifest: {result['build_manifest']}")
    print(f"SHA-256: {result['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
