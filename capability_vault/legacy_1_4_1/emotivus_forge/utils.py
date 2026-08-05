from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_SCAN_EXCLUDES = {
    ".git", ".hg", ".svn", ".idea", ".vscode", "__pycache__",
    ".forge", "node_modules", "dist", "build", "deploy", ".venv", "venv",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_rel(value: str) -> str:
    return value.strip().replace("\\", "/").strip("/")


def path_is_excluded(relative: Path, excludes: set[str]) -> bool:
    posix = relative.as_posix()
    for raw in excludes:
        rule = normalize_rel(raw)
        if not rule:
            continue
        if "/" in rule:
            if posix == rule or posix.startswith(rule + "/"):
                return True
        elif rule in relative.parts:
            return True
    return False


def iter_project_files(root: Path, excludes: Iterable[str], forge_root: Path | None = None) -> Iterable[Path]:
    root = root.resolve()
    excluded = set(DEFAULT_SCAN_EXCLUDES) | {normalize_rel(item) for item in excludes if normalize_rel(item)}
    if forge_root is not None:
        try:
            rel_forge = forge_root.resolve().relative_to(root).as_posix()
        except ValueError:
            rel_forge = ""
        if rel_forge:
            excluded.add(rel_forge)

    for current, dir_names, file_names in os.walk(root):
        current_path = Path(current)
        relative_dir = current_path.relative_to(root)
        kept: list[str] = []
        for name in sorted(dir_names):
            candidate = relative_dir / name
            if not path_is_excluded(candidate, excluded):
                kept.append(name)
        dir_names[:] = kept
        for name in sorted(file_names):
            path = current_path / name
            relative = path.relative_to(root)
            if not path_is_excluded(relative, excluded):
                yield path


def tree_fingerprint(root: Path, excludes: Iterable[str], forge_root: Path | None = None) -> str:
    digest = hashlib.sha256()
    for path in sorted(iter_project_files(root, excludes, forge_root), key=lambda p: p.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(os.readlink(path).encode("utf-8", errors="replace"))
        else:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()



def tree_snapshot(root: Path, excludes: Iterable[str], forge_root: Path | None = None) -> dict[str, dict[str, Any]]:
    """Return a deterministic per-file snapshot for changed-since-green evidence."""
    root = root.resolve()
    snapshot: dict[str, dict[str, Any]] = {}
    for path in sorted(iter_project_files(root, excludes, forge_root), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        try:
            if path.is_symlink():
                target = os.readlink(path)
                digest = sha256_bytes(target.encode("utf-8", errors="replace"))
                size = len(target.encode("utf-8", errors="replace"))
                kind = "symlink"
            else:
                digest = sha256_file(path)
                size = path.stat().st_size
                kind = "file"
        except OSError:
            continue
        snapshot[relative] = {"sha256": digest, "size": size, "kind": kind}
    return snapshot

def declared_paths_fingerprint(root: Path, declared_paths: Iterable[str]) -> dict[str, Any]:
    """Fingerprint an explicit working set, including excluded fixtures and nested tool products.

    Paths are project-relative files or directories. Missing and unsafe entries are
    represented in the digest so a cached command cannot silently reuse evidence
    after its ecosystem inputs disappear or move.
    """
    root = root.resolve()
    digest = hashlib.sha256()
    files = 0
    total_bytes = 0
    missing: list[str] = []
    unsafe: list[str] = []
    seen: set[str] = set()

    def record(relative: str, path: Path) -> None:
        nonlocal files, total_bytes
        if relative in seen:
            return
        seen.add(relative)
        digest.update(relative.encode("utf-8", errors="replace"))
        digest.update(b"\0")
        try:
            if path.is_symlink():
                payload = os.readlink(path).encode("utf-8", errors="replace")
            else:
                payload = path.read_bytes()
        except OSError as exc:
            payload = f"UNREADABLE:{type(exc).__name__}:{exc}".encode("utf-8", errors="replace")
        digest.update(payload)
        digest.update(b"\0")
        files += 1
        total_bytes += len(payload)

    for raw in sorted({normalize_rel(str(item)) for item in declared_paths if normalize_rel(str(item))}):
        rel_path = Path(raw)
        if rel_path.is_absolute() or ".." in rel_path.parts:
            unsafe.append(raw)
            digest.update(f"UNSAFE:{raw}\0".encode("utf-8", errors="replace"))
            continue
        path = (root / rel_path).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            unsafe.append(raw)
            digest.update(f"UNSAFE:{raw}\0".encode("utf-8", errors="replace"))
            continue
        if path.is_file() or path.is_symlink():
            record(rel_path.as_posix(), path)
            continue
        if path.is_dir():
            for child in sorted(path.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
                if child.is_file() or child.is_symlink():
                    record(child.relative_to(root).as_posix(), child)
            continue
        missing.append(raw)
        digest.update(f"MISSING:{raw}\0".encode("utf-8", errors="replace"))

    return {
        "sha256": digest.hexdigest(),
        "files": files,
        "bytes": total_bytes,
        "missing": missing,
        "unsafe": unsafe,
    }


def resolve_command(command: list[str], *, project: Path, forge: Path) -> list[str]:
    replacements = {
        "{project}": str(project.resolve()),
        "{forge}": str(forge.resolve()),
        "{python}": os.environ.get("PYTHON_BINARY", os.sys.executable),
        "{php}": os.environ.get("PHP_BINARY", "php"),
        "{node}": os.environ.get("NODE_BINARY", "node"),
    }
    resolved: list[str] = []
    for part in command:
        value = str(part)
        for needle, replacement in replacements.items():
            value = value.replace(needle, replacement)
        resolved.append(value)
    return resolved
