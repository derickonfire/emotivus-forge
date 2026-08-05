from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


class ForgeStateError(RuntimeError):
    """Raised when persisted Forge state cannot be trusted safely."""

    def __init__(self, path: Path, message: str, *, line: int | None = None) -> None:
        self.path = path
        self.line = line
        location = f"{path}:{line}" if line is not None else str(path)
        super().__init__(f"{location}: {message}")


@dataclass(frozen=True)
class JsonlIssue:
    path: str
    line: int
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "line": self.line, "message": self.message}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_rel(path: str | Path) -> str:
    value = Path(path).as_posix()
    while value.startswith("./"):
        value = value[2:]
    return "" if value == "." else value


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def pretty_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def safe_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    return bool(normalized) and not normalized.startswith("/") and ".." not in path.parts


def member_is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF)


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (0o100644 & 0xFFFF) << 16
    return info


def verify_archive_hygiene(archive: zipfile.ZipFile, problems: list[str]) -> tuple[list[str], str, str, dict[str, Any]]:
    """Shared kit-archive hygiene: duplicate / unsafe / encrypted / symlink /
    timestamp checks, single top-level root enforcement, and MANIFEST.json load.
    Appends any problems in place and returns (names, root_name, manifest_name,
    manifest). Callers keep their own schema, payload, and kit_id logic."""
    infos = archive.infolist()
    names = [info.filename for info in infos if not info.is_dir()]
    if len(names) != len(set(names)):
        problems.append("archive contains duplicate member names")
    if any(not safe_member(name) for name in names):
        problems.append("archive contains unsafe member paths")
    if any(info.flag_bits & 0x1 for info in infos):
        problems.append("archive contains encrypted members")
    if any(member_is_symlink(info) for info in infos):
        problems.append("archive contains symbolic-link members")
    if any(info.date_time != ZIP_TIMESTAMP for info in infos):
        problems.append("archive member timestamps are not deterministic")
    roots = {PurePosixPath(name).parts[0] for name in names if PurePosixPath(name).parts}
    if len(roots) != 1:
        problems.append("archive must contain exactly one top-level kit directory")
        root_name = ""
    else:
        root_name = next(iter(roots))
    manifest_name = f"{root_name}/MANIFEST.json" if root_name else ""
    manifest: dict[str, Any] = {}
    if not manifest_name or manifest_name not in names:
        problems.append("archive does not contain MANIFEST.json at the kit root")
    else:
        try:
            loaded = json.loads(archive.read(manifest_name).decode("utf-8"))
            manifest = loaded if isinstance(loaded, dict) else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            problems.append(f"MANIFEST.json is invalid: {exc}")
    return names, root_name, manifest_name, manifest


def _is_forge_state_path(path: Path) -> bool:
    return ".forge" in path.parts


def read_json(path: Path, default: Any = None, *, strict: bool | None = None) -> Any:
    """Read JSON without hiding corruption in persisted Forge state.

    Project-owned source/config files remain tolerant by default. Files below `.forge`
    are strict automatically so malformed continuity state cannot silently become an
    empty object and then be overwritten.
    """
    if not path.is_file():
        return default
    strict_mode = _is_forge_state_path(path) if strict is None else strict
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        if strict_mode:
            raise ForgeStateError(path, f"could not be read: {exc}") from exc
    except UnicodeDecodeError as exc:
        if strict_mode:
            raise ForgeStateError(path, "is not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        if strict_mode:
            raise ForgeStateError(path, f"invalid JSON: {exc.msg}", line=exc.lineno) from exc
    return default


def _fsync_parent(path: Path) -> None:
    """Best-effort directory sync after an atomic replace."""
    if os.name == "nt":
        return
    flags = getattr(os, "O_DIRECTORY", 0) | os.O_RDONLY
    try:
        directory_fd = os.open(str(path.parent), flags)
    except OSError:
        return
    try:
        os.fsync(directory_fd)
    except OSError:
        pass
    finally:
        os.close(directory_fd)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        _fsync_parent(path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        _fsync_parent(path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_jsonl_report(path: Path) -> tuple[list[dict[str, Any]], list[JsonlIssue]]:
    """Recover valid JSONL rows while reporting each malformed line separately."""
    rows: list[dict[str, Any]] = []
    issues: list[JsonlIssue] = []
    if not path.is_file():
        return rows, issues
    try:
        with path.open("r", encoding="utf-8") as handle:
            for number, raw_line in enumerate(handle, 1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    issues.append(JsonlIssue(str(path), number, f"invalid JSONL: {exc.msg}"))
                    continue
                if isinstance(value, dict):
                    rows.append(value)
                else:
                    issues.append(JsonlIssue(str(path), number, "JSONL record must be an object"))
    except OSError as exc:
        issues.append(JsonlIssue(str(path), 0, f"could not be read: {exc}"))
    except UnicodeDecodeError:
        issues.append(JsonlIssue(str(path), 0, "is not valid UTF-8"))
    return rows, issues


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows, _issues = read_jsonl_report(path)
    return rows


def unique_strings(values: Iterable[object]) -> list[str]:
    result: list[str] = []
    for raw in values:
        value = str(raw).strip()
        if value and value not in result:
            result.append(value)
    return result
