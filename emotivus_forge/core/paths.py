from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
        return self.project_root / ".forge"

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
