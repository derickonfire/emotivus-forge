"""Forward-compatible migration inventory (Goal 3 · cross-model evolution).

Cross-model evolution requires that when this Forge migrates an older or another
vendor's package, it preserves fields it does not recognize rather than silently
dropping them — and reports them, so a different or newer model can see exactly what
was carried through unrecognized. Forge retains unknown fields verbatim and never
interprets them; this module reports what was preserved, not what it means.
"""

from __future__ import annotations

from typing import Any

from .state import _settings_defaults

TRUTH_BOUNDARY = (
    "The forward-compat inventory lists top-level settings fields this Forge schema does "
    "not recognize but preserved unchanged through migration. It reports what was carried, "
    "not what the fields mean: unknown fields are retained verbatim and never interpreted, "
    "trusted, or treated as authority, evidence, or lineage."
)


def known_settings_fields() -> set[str]:
    """The set of top-level settings fields this Forge schema recognizes."""
    return set(_settings_defaults().keys())


def preserved_unknown_fields(settings: dict[str, Any]) -> list[str]:
    """Top-level settings keys not recognized by this schema (preserved verbatim)."""
    if not isinstance(settings, dict):
        return []
    known = known_settings_fields()
    return sorted(key for key in settings if key not in known)


def forward_compat_report(settings: dict[str, Any]) -> dict[str, Any]:
    """Inventory of fields preserved through migration without being recognized."""
    unknown = preserved_unknown_fields(settings)
    return {
        "schema": 1,
        "unknown_field_count": len(unknown),
        "unknown_fields": unknown,
        "truth_boundary": TRUTH_BOUNDARY,
    }
