from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .common import ForgeStateError, read_jsonl_report, utc_now
from .models import CoreSettings, StateIntegrityIssue
from .ledger import verify_ledger_chain
from .paths import ForgePaths

_JSON_STATE_NAMES = ("passport.json", "authorities.json", "native-tools.json", "settings.json", "state.json")
_JSONL_STATE_NAMES = ("ledger.jsonl", "metrics.jsonl")


def _document_validation_error(name: str, value: dict[str, Any]) -> str:
    schema = value.get("schema", 1)
    # Derived, never hardcoded. A second hardcoded registry silently capped settings at
    # schema 20 while state.py had advanced, and every migrated project read as BLOCKED
    # malformed state. Deriving both bounds makes that class of drift impossible.
    from .state import CORE_STATE_SCHEMA, SETTINGS_SCHEMA

    allowed = {
        "passport.json": {1},
        "authorities.json": {1, 2},
        "native-tools.json": {1, 2, 3, 4},
        "settings.json": set(range(1, SETTINGS_SCHEMA + 1)),
        "state.json": set(range(1, CORE_STATE_SCHEMA + 1)),
    }.get(name, {1})
    if schema not in allowed:
        return f"unsupported schema {schema}; supported schema(s): {sorted(allowed)}"
    if name == "passport.json":
        if not isinstance(value.get("identity", {}), dict):
            return "identity must be an object"
        if not isinstance(value.get("objective", {}), dict):
            return "objective must be an object"
    elif name == "authorities.json":
        if not isinstance(value.get("objective", {}), dict):
            return "objective must be an object"
        if not isinstance(value.get("candidates", []), list):
            return "candidates must be an array"
    elif name == "native-tools.json":
        if not isinstance(value.get("candidates", []), list):
            return "candidates must be an array"
        canonical = value.get("canonical")
        if canonical is not None and not isinstance(canonical, dict):
            return "canonical must be an object or null"
    elif name == "settings.json":
        try:
            CoreSettings.from_dict(value)
        except (TypeError, ValueError) as exc:
            return str(exc)
        for key in ("authority_path_precedence", "advanced_capabilities", "guardrails", "field_trials", "project_identity", "project_events", "ledger_assertions", "check_qualifications", "artifact_provenance", "deployable_boundaries", "canonical_claims", "relationship_sets", "runtime_state_matrices", "state_transition_plans", "release_packages", "presentation_profiles", "release_distributions", "cold_session_validations", "release_proofs", "release_authorizations", "project_lineages", "merge_candidates", "migration_catalogs", "package_families", "surface_coverages", "release_facts", "continuity_registers", "third_party_intakes"):
            if not isinstance(value.get(key, {}), dict):
                return f"{key} must be an object"
        for key in ("lineage_control_paths", "migration_control_paths", "package_family_control_paths", "surface_coverage_control_paths", "release_fact_control_paths", "continuity_control_paths", "third_party_control_paths"):
            if not isinstance(value.get(key, []), list):
                return f"{key} must be an array"
    elif name == "state.json":
        if "snapshot" in value and not isinstance(value.get("snapshot"), dict):
            return "snapshot must be an object"
        if "last_check" in value and not isinstance(value.get("last_check"), dict):
            return "last_check must be an object"
        if schema >= 2:
            if not isinstance(value.get("notices", {}), dict):
                return "notices must be an object"
            if not isinstance(value.get("knowledge", {}), dict):
                return "knowledge must be an object"
        if schema >= 3 and not isinstance(value.get("authority_baseline", {}), dict):
            return "authority_baseline must be an object"
        if schema >= 4 and not isinstance(value.get("sidecar", {}), dict):
            return "sidecar must be an object"
        if schema >= 5 and not isinstance(value.get("workspace_integrity", {}), dict):
            return "workspace_integrity must be an object"
    return ""


class ForgeLockError(RuntimeError):
    pass


class ProjectLock:
    """Cross-platform best-effort exclusive lock with no persistent ninth state file."""

    def __init__(self, project_root: Path, *, timeout_seconds: float = 10.0) -> None:
        self.root = project_root.resolve() / ".forge"
        self.path = self.root / ".operation.lock"
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.handle: Any = None

    def acquire(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0)
        if self.handle.tell() == 0:
            self.handle.write(b"0")
            self.handle.flush()
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    self.handle.seek(0)
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.handle.seek(0)
                self.handle.truncate()
                self.handle.write(json.dumps({"pid": os.getpid(), "acquired_utc": utc_now()}).encode("utf-8"))
                self.handle.flush()
                os.fsync(self.handle.fileno())
                return
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    self.handle.close()
                    self.handle = None
                    raise ForgeLockError(
                        f"Could not acquire the Forge project lock within {self.timeout_seconds:g} seconds. "
                        "Another Forge operation may still be writing this project."
                    )
                time.sleep(0.05)

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                # The lock itself has been released; a harmless stale path is preferable
                # to hiding a completed operation behind a cleanup error.
                pass

    def __enter__(self) -> "ProjectLock":
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.release()


def inspect_state_integrity(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    paths = ForgePaths(project_root)
    if not paths.root.is_dir():
        return {"schema": 1, "status": "MISSING", "issues": [], "checked_files": 0}

    issues: list[StateIntegrityIssue] = []
    checked = 0
    for name in _JSON_STATE_NAMES:
        path = paths.root / name
        if not path.is_file():
            continue
        checked += 1
        try:
            raw = path.read_text(encoding="utf-8")
            value = json.loads(raw)
        except OSError as exc:
            issues.append(StateIntegrityIssue("blocker", name, f"could not be read: {exc}"))
            continue
        except UnicodeDecodeError:
            issues.append(StateIntegrityIssue("blocker", name, "is not valid UTF-8"))
            continue
        except json.JSONDecodeError as exc:
            issues.append(StateIntegrityIssue("blocker", name, f"invalid JSON: {exc.msg}", line=exc.lineno))
            continue
        if not isinstance(value, dict):
            issues.append(StateIntegrityIssue("blocker", name, "top-level state document must be an object"))
            continue
        schema = value.get("schema")
        if schema is not None and (not isinstance(schema, int) or schema < 1):
            issues.append(StateIntegrityIssue("blocker", name, "schema must be a positive integer"))
            continue
        validation_error = _document_validation_error(name, value)
        if validation_error:
            issues.append(StateIntegrityIssue("blocker", name, validation_error))

    for name in _JSONL_STATE_NAMES:
        path = paths.root / name
        if not path.is_file():
            continue
        checked += 1
        rows, row_issues = read_jsonl_report(path)
        for issue in row_issues:
            issues.append(StateIntegrityIssue(
                "blocker",
                name,
                issue.message,
                line=issue.line or None,
                recovered_records=len(rows),
            ))
        if name == "ledger.jsonl" and not row_issues:
            chain = verify_ledger_chain(path)
            for item in chain.get("issues", []):
                issues.append(StateIntegrityIssue(
                    "blocker",
                    name,
                    str(item.get("message", "ledger integrity failure")),
                    line=int(item.get("line", 0)) or None,
                    recovered_records=len(rows),
                ))

    resume = paths.resume
    if resume.is_file():
        checked += 1
        try:
            resume.read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(StateIntegrityIssue("blocker", resume.name, f"could not be read: {exc}"))
        except UnicodeDecodeError:
            issues.append(StateIntegrityIssue("blocker", resume.name, "is not valid UTF-8"))

    status = "BLOCKED" if issues else "HEALTHY"
    return {
        "schema": 1,
        "status": status,
        "issues": [item.to_dict() for item in issues],
        "checked_files": checked,
        "preservation": "Malformed files were left unchanged; valid JSONL records were recovered only for diagnosis.",
    }


def require_healthy_state(project_root: Path) -> dict[str, Any]:
    report = inspect_state_integrity(project_root)
    if report.get("status") == "BLOCKED":
        first = report.get("issues", [{}])[0]
        path = project_root.resolve() / ".forge" / str(first.get("path", "state"))
        line = first.get("line")
        raise ForgeStateError(path, str(first.get("message", "Forge state is corrupted")), line=int(line) if isinstance(line, int) else None)
    return report


@contextmanager
def state_transaction(
    project_root: Path,
    *,
    validate_existing: bool = True,
    timeout_seconds: float = 10.0,
) -> Iterator[dict[str, Any]]:
    """Lock and rollback the eight top-level state files as one operation boundary."""
    project_root = project_root.resolve()
    paths = ForgePaths(project_root)
    with ProjectLock(project_root, timeout_seconds=timeout_seconds):
        if validate_existing and paths.root.is_dir():
            require_healthy_state(project_root)
        snapshot: dict[str, bytes | None] = {}
        for path in paths.minimal_state_files():
            snapshot[path.name] = path.read_bytes() if path.is_file() else None
        transaction = {"schema": 1, "started_utc": utc_now(), "files": list(snapshot)}
        try:
            yield transaction
        except BaseException:
            paths.root.mkdir(parents=True, exist_ok=True)
            for path in paths.minimal_state_files():
                previous = snapshot[path.name]
                if previous is None:
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass
                else:
                    path.write_bytes(previous)
                    try:
                        with path.open("rb") as handle:
                            os.fsync(handle.fileno())
                    except OSError:
                        pass
            raise
