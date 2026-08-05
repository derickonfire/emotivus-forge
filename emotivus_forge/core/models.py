from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

NOTICE_LEVELS = ("silent", "notice", "warning", "blocker")
NOTICE_MODES = ("quiet", "standard", "visible")


@dataclass(frozen=True)
class AiNotice:
    id: str
    level: str
    summary: str
    category: str
    speak: bool
    repeated: bool = False
    mode: str = "standard"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": 1,
            "id": self.id,
            "level": self.level,
            "summary": self.summary,
            "category": self.category,
            "speak": self.speak,
            "repeated": self.repeated,
            "mode": self.mode,
            "details": self.details,
        }


@dataclass(frozen=True)
class StateIntegrityIssue:
    severity: str
    path: str
    message: str
    line: int | None = None
    recovered_records: int = 0

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "severity": self.severity,
            "path": self.path,
            "message": self.message,
            "recovered_records": self.recovered_records,
        }
        if self.line is not None:
            result["line"] = self.line
        return result


@dataclass(frozen=True)
class KnowledgeChange:
    key: str
    label: str
    status: str
    previous: Any = None
    current: Any = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "previous": self.previous,
            "current": self.current,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CoreSettings:
    adoption_file_budget: int = 5000
    hash_file_limit_bytes: int = 1_000_000
    hash_total_budget_bytes: int = 8_000_000
    authority_candidate_budget: int = 40
    resume_budget: str = "compact"
    native_gate_timeout_seconds: int = 180
    notice_mode: str = "standard"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CoreSettings":
        mode = str(value.get("notice_mode", "standard")).lower()
        if mode not in NOTICE_MODES:
            raise ValueError("notice_mode must be quiet, standard, or visible")
        resume_budget = str(value.get("resume_budget", "compact")).lower()
        if resume_budget not in {"compact", "standard", "full"}:
            raise ValueError("resume_budget must be compact, standard, or full")
        numeric = {
            "adoption_file_budget": int(value.get("adoption_file_budget", 5000)),
            "hash_file_limit_bytes": int(value.get("hash_file_limit_bytes", 1_000_000)),
            "hash_total_budget_bytes": int(value.get("hash_total_budget_bytes", 8_000_000)),
            "authority_candidate_budget": int(value.get("authority_candidate_budget", 40)),
            "native_gate_timeout_seconds": int(value.get("native_gate_timeout_seconds", 180)),
        }
        if any(number <= 0 for number in numeric.values()):
            raise ValueError("numeric Forge settings must be positive")
        return cls(
            **numeric,
            resume_budget=resume_budget,
            notice_mode=mode,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "adoption_file_budget": self.adoption_file_budget,
            "hash_file_limit_bytes": self.hash_file_limit_bytes,
            "hash_total_budget_bytes": self.hash_total_budget_bytes,
            "authority_candidate_budget": self.authority_candidate_budget,
            "resume_budget": self.resume_budget,
            "native_gate_timeout_seconds": self.native_gate_timeout_seconds,
            "notice_mode": self.notice_mode,
        }
