from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


# Read-only consultation redirects a project's Forge state directory to a
# disposable location OUTSIDE the project tree, so a bounded read-only invocation
# reads the real project bytes but writes nothing into the project's ".forge".
# Keyed by the resolved project root; empty in normal (persisting) operation.
_STATE_REDIRECTS: dict[Path, Path] = {}


def state_root(project_root: Path) -> Path:
    """Resolve where this project's Forge state lives.

    Returns ``project_root / ".forge"`` unless a read-only redirect is active for
    this project, in which case the redirected (disposable) directory is returned.
    """
    override = _STATE_REDIRECTS.get(project_root.resolve())
    return override if override is not None else project_root / ".forge"


@contextmanager
def redirect_state(project_root: Path, alt_root: Path) -> Iterator[None]:
    """Temporarily redirect a project's Forge state directory to ``alt_root``.

    Every state read/write that resolves through ``state_root`` (which is every
    ForgePaths-based path and the storage lock) is diverted for the duration.
    """
    key = project_root.resolve()
    previous = _STATE_REDIRECTS.get(key)
    _STATE_REDIRECTS[key] = Path(alt_root)
    try:
        yield
    finally:
        if previous is None:
            _STATE_REDIRECTS.pop(key, None)
        else:
            _STATE_REDIRECTS[key] = previous


STATE_FILE_NAMES = (
    "passport.json",
    "resume.md",
    "ledger.jsonl",
    "authorities.json",
    "native-tools.json",
    "settings.json",
    "state.json",
    "metrics.jsonl",
)

IGNORED_DIR_NAMES = {
    ".forge", ".git", ".hg", ".svn", ".idea", ".vscode",
    "__pycache__", "node_modules", "vendor", "dist", "build", "coverage",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".venv", "venv",
    "capability_vault",
}


@dataclass(frozen=True)
class ForgePaths:
    project_root: Path

    @property
    def root(self) -> Path:
        return state_root(self.project_root)

    @property
    def passport(self) -> Path:
        return self.root / "passport.json"

    @property
    def resume(self) -> Path:
        return self.root / "resume.md"

    @property
    def ledger(self) -> Path:
        return self.root / "ledger.jsonl"

    @property
    def authorities(self) -> Path:
        return self.root / "authorities.json"

    @property
    def native_tools(self) -> Path:
        return self.root / "native-tools.json"

    @property
    def settings(self) -> Path:
        return self.root / "settings.json"

    @property
    def state(self) -> Path:
        return self.root / "state.json"

    @property
    def metrics(self) -> Path:
        return self.root / "metrics.jsonl"

    @property
    def evidence(self) -> Path:
        return self.root / "evidence"

    @property
    def native_evidence(self) -> Path:
        return self.evidence / "native-gate"

    def minimal_state_files(self) -> list[Path]:
        return [self.root / name for name in STATE_FILE_NAMES]
