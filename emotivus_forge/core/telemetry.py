from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .common import append_jsonl, read_jsonl, utc_now
from .paths import ForgePaths

TELEMETRY_SCHEMA = 2
BENCHMARK_ARMS = ("with-forge", "without-forge")
MIN_BENCHMARK_PAIRS = 3


def _nonnegative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a non-negative integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a non-negative integer") from exc
    if number < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return number


def record_metric(project_root: Path, operation: str, values: dict[str, Any]) -> None:
    """Append local operational telemetry.

    Callers must label estimates explicitly. This function never converts bytes or
    characters into a claim of actual provider-token usage or savings.
    """
    append_jsonl(ForgePaths(project_root).metrics, {
        "schema": TELEMETRY_SCHEMA,
        "utc": utc_now(),
        "operation": operation,
        **values,
    })


def normalize_interaction_telemetry(
    *,
    provider: str = "",
    provider_input_tokens: object | None = None,
    provider_output_tokens: object | None = None,
    retry_count: object = 0,
    correction_count: object = 0,
    session_output_characters: object | None = None,
    benchmark_id: str = "",
    benchmark_arm: str = "",
) -> dict[str, Any]:
    """Validate operator-supplied interaction metrics for Session Close.

    Provider counts are treated as exact only because the operator explicitly
    supplies them from a provider report. Forge does not infer them.
    """
    input_supplied = provider_input_tokens is not None
    output_supplied = provider_output_tokens is not None
    if input_supplied != output_supplied:
        raise ValueError("provider input and output token counts must be supplied together")

    exact: dict[str, Any] = {}
    if input_supplied:
        provider_name = str(provider).strip()
        if not provider_name:
            raise ValueError("exact provider token counts require --provider")
        input_tokens = _nonnegative_int(provider_input_tokens, label="provider input tokens")
        output_tokens = _nonnegative_int(provider_output_tokens, label="provider output tokens")
        exact = {
            "source": "provider-reported",
            "provider": provider_name,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
    elif str(provider).strip():
        raise ValueError("--provider requires exact provider input and output token counts")

    retries = _nonnegative_int(retry_count, label="retry count")
    corrections = _nonnegative_int(correction_count, label="correction count")
    output_chars: int | None = None
    if session_output_characters is not None:
        output_chars = _nonnegative_int(session_output_characters, label="session output characters")

    benchmark_id = str(benchmark_id).strip()
    benchmark_arm = str(benchmark_arm).strip()
    if bool(benchmark_id) != bool(benchmark_arm):
        raise ValueError("benchmark ID and benchmark arm must be supplied together")
    if benchmark_arm and benchmark_arm not in BENCHMARK_ARMS:
        raise ValueError(f"benchmark arm must be one of: {', '.join(BENCHMARK_ARMS)}")
    if benchmark_id and not exact:
        raise ValueError("controlled benchmark entries require exact provider token counts")

    return {
        "schema": 1,
        "exact_provider_tokens": exact,
        "observed": {
            "retry_count": retries,
            "correction_count": corrections,
            "session_output_characters": output_chars,
        },
        "benchmark": {
            "id": benchmark_id,
            "arm": benchmark_arm,
        } if benchmark_id else {},
        "truth_boundary": (
            "Provider token counts are exact only when copied from the named provider. "
            "Character-based estimates remain heuristic and are never reported as actual savings."
        ),
    }


def record_interaction_session(project_root: Path, telemetry: dict[str, Any], *, session_event_id: str) -> None:
    exact = telemetry.get("exact_provider_tokens", {}) if isinstance(telemetry, dict) else {}
    observed = telemetry.get("observed", {}) if isinstance(telemetry, dict) else {}
    benchmark = telemetry.get("benchmark", {}) if isinstance(telemetry, dict) else {}
    record_metric(project_root, "interaction-session", {
        "session_event_id": session_event_id,
        "exact_provider_tokens": exact if isinstance(exact, dict) else {},
        "observed": observed if isinstance(observed, dict) else {},
        "benchmark": benchmark if isinstance(benchmark, dict) else {},
    })


def _paired_benchmarks(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row.get("operation") != "interaction-session":
            continue
        benchmark = row.get("benchmark", {})
        exact = row.get("exact_provider_tokens", {})
        if not isinstance(benchmark, dict) or not isinstance(exact, dict):
            continue
        benchmark_id = str(benchmark.get("id", "")).strip()
        arm = str(benchmark.get("arm", "")).strip()
        if not benchmark_id or arm not in BENCHMARK_ARMS:
            continue
        if exact.get("source") != "provider-reported":
            continue
        grouped[benchmark_id][arm].append(row)

    pairs: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for benchmark_id in sorted(grouped):
        arms = grouped[benchmark_id]
        pair_count = min(len(arms["with-forge"]), len(arms["without-forge"]))
        for index in range(pair_count):
            with_row = arms["with-forge"][index]
            without_row = arms["without-forge"][index]
            with_exact = with_row["exact_provider_tokens"]
            without_exact = without_row["exact_provider_tokens"]
            provider_with = str(with_exact.get("provider", "")).strip()
            provider_without = str(without_exact.get("provider", "")).strip()
            if provider_with.casefold() != provider_without.casefold():
                rejected.append({
                    "benchmark_id": benchmark_id,
                    "pair_index": index + 1,
                    "reason": "provider-mismatch",
                    "provider_with_forge": provider_with,
                    "provider_without_forge": provider_without,
                })
                continue
            with_total = int(with_exact.get("total_tokens", 0) or 0)
            without_total = int(without_exact.get("total_tokens", 0) or 0)
            pairs.append({
                "benchmark_id": benchmark_id,
                "pair_index": index + 1,
                "provider_with_forge": provider_with,
                "provider_without_forge": provider_without,
                "with_forge_tokens": with_total,
                "without_forge_tokens": without_total,
                "token_delta_without_minus_with": without_total - with_total,
                "source": "exact-provider-reported-pair",
            })
    return pairs, rejected


def summarize_telemetry(
    project_root: Path,
    *,
    current_resume_characters: int = 0,
    current_cached_records: int = 0,
    current_evidence_records_reused: int = 0,
) -> dict[str, Any]:
    rows = read_jsonl(ForgePaths(project_root).metrics)
    operation_counts = Counter(str(row.get("operation", "unknown")) for row in rows)
    interaction_rows = [row for row in rows if row.get("operation") == "interaction-session"]

    exact_sessions = 0
    exact_input = 0
    exact_output = 0
    retries = 0
    corrections = 0
    observed_output_characters = 0
    for row in interaction_rows:
        exact = row.get("exact_provider_tokens", {})
        observed = row.get("observed", {})
        if isinstance(exact, dict) and exact.get("source") == "provider-reported":
            exact_sessions += 1
            exact_input += int(exact.get("input_tokens", 0) or 0)
            exact_output += int(exact.get("output_tokens", 0) or 0)
        if isinstance(observed, dict):
            retries += int(observed.get("retry_count", 0) or 0)
            corrections += int(observed.get("correction_count", 0) or 0)
            observed_output_characters += int(observed.get("session_output_characters", 0) or 0)

    first_adopt = next((row for row in rows if row.get("operation") == "adopt"), None)
    initialization_ms = int(first_adopt.get("duration_ms", 0) or 0) if isinstance(first_adopt, dict) else 0
    pairs, rejected_comparisons = _paired_benchmarks(rows)
    aggregate_delta = sum(item["token_delta_without_minus_with"] for item in pairs)
    if len(pairs) < MIN_BENCHMARK_PAIRS:
        break_even = {
            "status": "insufficient-pairs",
            "required_pairs": MIN_BENCHMARK_PAIRS,
            "observed_pairs": len(pairs),
            "aggregate_token_delta": aggregate_delta,
            "conclusion": "Break-even is not established. At least three matched exact-provider pairs are required.",
        }
    elif aggregate_delta > 0:
        break_even = {
            "status": "observed-in-sample",
            "required_pairs": MIN_BENCHMARK_PAIRS,
            "observed_pairs": len(pairs),
            "aggregate_token_delta": aggregate_delta,
            "conclusion": "The matched sample used fewer exact provider tokens with Forge; this is not a universal savings claim.",
        }
    else:
        break_even = {
            "status": "not-observed-in-sample",
            "required_pairs": MIN_BENCHMARK_PAIRS,
            "observed_pairs": len(pairs),
            "aggregate_token_delta": aggregate_delta,
            "conclusion": "The matched sample did not demonstrate lower exact provider-token use with Forge.",
        }

    heuristic_resume_tokens = max(0, round(current_resume_characters / 4))
    meaningful_sessions = operation_counts.get("session-close", 0)
    if meaningful_sessions <= 1 and not pairs:
        suitability = "For a small one-off task, Forge overhead may exceed its benefit; repeated-session value is not yet proven."
    elif not pairs:
        suitability = "Continuity reuse is observed, but token savings and practical break-even remain unproven without matched exact-provider comparisons."
    else:
        suitability = break_even["conclusion"]

    return {
        "schema": 1,
        "operation_counts": dict(sorted(operation_counts.items())),
        "observed": {
            "initialization_duration_ms": initialization_ms,
            "meaningful_session_closes": meaningful_sessions,
            "current_cached_records_reused": max(0, int(current_cached_records)),
            "current_evidence_records_reused": max(0, int(current_evidence_records_reused)),
            "recorded_retry_count": retries,
            "recorded_correction_count": corrections,
            "recorded_session_output_characters": observed_output_characters,
        },
        "exact_provider": {
            "session_count": exact_sessions,
            "input_tokens": exact_input,
            "output_tokens": exact_output,
            "total_tokens": exact_input + exact_output,
            "source": "provider-reported only",
        },
        "heuristic": {
            "current_resume_token_estimate": heuristic_resume_tokens,
            "method": "rounded UTF-8 character count divided by four",
            "classification": "heuristic estimate; not provider measurement and not token savings",
        },
        "benchmark": {
            "protocol": "matched task, same provider/model/settings, one with Forge and one without Forge; record exact provider counts; use at least three valid pairs",
            "validated_by_forge": "shared benchmark ID and matching provider name; model/settings/task equivalence remain operator-controlled",
            "pairs": pairs,
            "rejected_comparisons": rejected_comparisons,
            "break_even": break_even,
        },
        "suitability": suitability,
        "truth_boundary": "No workspace-byte compression or character estimate is reported as actual provider-token savings.",
    }
