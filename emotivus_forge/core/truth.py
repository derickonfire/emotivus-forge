from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

TRUTH_STATES = (
    "OBSERVED",
    "CONFIRMED",
    "INFERRED",
    "UNKNOWN",
    "NOT_RUN",
    "BLOCKED_ATTEMPTED",
    "BLOCKED_UNATTEMPTED",
    "STALE",
    "CONTRADICTED",
)

VERIFICATION_TIERS = (
    "static",
    "sandbox",
    "headless",
    "emulator",
    "dev_device",
    "staging",
    "production",
)

# Higher tiers may support stronger claims, but never imply lower-tier checks ran.
TIER_RANK = {name: index for index, name in enumerate(VERIFICATION_TIERS, 1)}


def normalize_truth_state(value: Any, *, default: str = "UNKNOWN") -> str:
    normalized = str(value or "").strip().upper().replace("-", "_")
    return normalized if normalized in TRUTH_STATES else default


def normalize_verification_tier(value: Any, *, default: str = "static") -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    return normalized if normalized in VERIFICATION_TIERS else default


@dataclass(frozen=True)
class TruthRecord:
    subject: str
    truth_state: str
    result: str = "UNKNOWN"
    verification_tier: str = "static"
    attempted: bool = False
    reason: str = ""
    source: str = ""
    exclusions: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": 1,
            "subject": self.subject,
            "truth_state": normalize_truth_state(self.truth_state),
            "result": str(self.result or "UNKNOWN").upper(),
            "verification_tier": normalize_verification_tier(self.verification_tier),
            "attempted": bool(self.attempted),
            "reason": self.reason,
            "source": self.source,
            "exclusions": list(self.exclusions),
        }


def summarize_truth_records(records: Iterable[dict[str, Any] | TruthRecord]) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    for item in records:
        row = item.to_dict() if isinstance(item, TruthRecord) else dict(item)
        row["truth_state"] = normalize_truth_state(row.get("truth_state"))
        row["verification_tier"] = normalize_verification_tier(row.get("verification_tier"))
        row["attempted"] = bool(row.get("attempted", False))
        normalized.append(row)
    state_counts = Counter(str(row["truth_state"]) for row in normalized)
    tier_counts = Counter(str(row["verification_tier"]) for row in normalized)
    unresolved = [
        row for row in normalized
        if row["truth_state"] in {"UNKNOWN", "NOT_RUN", "BLOCKED_ATTEMPTED", "BLOCKED_UNATTEMPTED", "STALE", "CONTRADICTED"}
    ]
    highest_tier = "none"
    observed_tiers = [
        str(row["verification_tier"]) for row in normalized
        if row["truth_state"] == "OBSERVED" and bool(row.get("attempted", False))
    ]
    if observed_tiers:
        highest_tier = max(observed_tiers, key=lambda value: TIER_RANK.get(value, 0))
    return {
        "schema": 1,
        "record_count": len(normalized),
        "state_counts": dict(sorted(state_counts.items())),
        "tier_counts": dict(sorted(tier_counts.items(), key=lambda pair: TIER_RANK.get(pair[0], 0))),
        "highest_observed_tier": highest_tier,
        "unresolved_count": len(unresolved),
        "unresolved": unresolved[:30],
        "truth_boundary": (
            "Truth states describe what Forge observed, confirmed, inferred, could not run, or considers stale. "
            "A higher verification tier does not imply every lower tier ran, and an unrun check is never explained by another blocker."
        ),
    }
