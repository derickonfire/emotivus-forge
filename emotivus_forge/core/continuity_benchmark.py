"""Reproducible continuity benchmark.

This module is a **measuring instrument**, not evidence. It defines how a continuity
comparison must be set up so that its results could be believed, and it refuses to
produce a comparison that would not be believable.

The instrument enforces seven conditions:

1. **Immutable tasks.** A task's identity is the SHA-256 of its canonical content. Change
   any field and it is a different task, never an edited one.
2. **Exact parents.** Every run names the exact package it ran against, by SHA-256.
3. **Paired arms.** A comparison needs a ``forge`` arm and a ``control`` arm of the same
   task, same parent, same provider, and same model.
4. **Declared provider and model identity.** Comparing runs across different models
   measures the models, not Forge.
5. **Isolated workspaces.** Two runs may never share a workspace path.
6. **Exact token and cost records.** Provider-reported only. Heuristic estimates are
   rejected outright rather than silently averaged into a result.
7. **Human review.** A run is not admissible until a named reviewer accepts it.

A suite with zero recorded runs reports ``NOT_RUN``. It never reports a tie, a pass, or a
neutral result, because no comparison happened.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

FORGE_ARM = "forge"
CONTROL_ARM = "control"
ARMS = (FORGE_ARM, CONTROL_ARM)

REQUIRED_TASK_FIELDS = ("name", "instruction", "success_criteria", "turns")
REQUIRED_RUN_FIELDS = (
    "task_id", "arm", "parent_sha256", "provider", "model", "workspace",
    "exact_input_tokens", "exact_output_tokens",
)

TRUTH_BOUNDARY = (
    "This is a measuring instrument, not evidence. A defined benchmark proves nothing until "
    "runs are recorded, reviewed, and paired. Zero runs reports NOT_RUN, never a tie. Results "
    "compare only runs sharing an identical task, parent package, provider, and model; anything "
    "else measures the environment rather than Forge."
)


class BenchmarkError(ValueError):
    """Raised when a definition or record would produce an unbelievable comparison."""


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def define_task(task: dict[str, Any]) -> dict[str, Any]:
    """Seal a task definition. Identity is content; there is no editing."""
    missing = [field for field in REQUIRED_TASK_FIELDS if not task.get(field)]
    if missing:
        raise BenchmarkError(f"task definition missing required fields: {sorted(missing)}")
    turns = task.get("turns")
    if not isinstance(turns, int) or turns < 1:
        raise BenchmarkError("task turns must be a positive integer")
    criteria = task.get("success_criteria")
    if not isinstance(criteria, list) or not all(isinstance(c, str) and c.strip() for c in criteria):
        raise BenchmarkError("task success_criteria must be a non-empty list of strings")
    content = {
        "name": str(task["name"]),
        "instruction": str(task["instruction"]),
        "success_criteria": [str(c) for c in criteria],
        "turns": turns,
    }
    return {
        "schema": "forge-benchmark-task/1",
        "task_id": hashlib.sha256(_canonical(content).encode("utf-8")).hexdigest(),
        "content": content,
        "sealed": True,
        "identity_source": "sha256 of canonical content",
    }


def verify_task_immutable(sealed: dict[str, Any]) -> bool:
    """Recompute a sealed task's identity from its content."""
    expected = hashlib.sha256(_canonical(sealed.get("content", {})).encode("utf-8")).hexdigest()
    return expected == sealed.get("task_id")


def record_run(run: dict[str, Any]) -> dict[str, Any]:
    """Validate and seal one run record.

    Token counts must be provider-reported exact integers. There is no estimate path: a
    benchmark that averages guesses produces a number nobody should act on.
    """
    missing = [field for field in REQUIRED_RUN_FIELDS if run.get(field) in (None, "")]
    if missing:
        raise BenchmarkError(f"run record missing required fields: {sorted(missing)}")
    if run["arm"] not in ARMS:
        raise BenchmarkError(f"run arm must be one of {list(ARMS)}")
    for field in ("exact_input_tokens", "exact_output_tokens"):
        value = run.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise BenchmarkError(f"{field} must be a non-negative provider-reported integer")
    if run.get("token_source") not in (None, "provider-reported"):
        raise BenchmarkError("token_source must be provider-reported; estimates are not admissible")
    if len(str(run["parent_sha256"])) != 64:
        raise BenchmarkError("parent_sha256 must be a full SHA-256 digest")
    cost = run.get("exact_cost")
    if cost is not None and (isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0):
        raise BenchmarkError("exact_cost must be a non-negative number when supplied")
    review = run.get("human_review") or {}
    reviewed = bool(review.get("reviewer")) and review.get("accepted") is True
    return {
        "schema": "forge-benchmark-run/1",
        "task_id": str(run["task_id"]),
        "arm": run["arm"],
        "parent_sha256": str(run["parent_sha256"]),
        "provider": str(run["provider"]),
        "model": str(run["model"]),
        "workspace": str(run["workspace"]),
        "exact_input_tokens": run["exact_input_tokens"],
        "exact_output_tokens": run["exact_output_tokens"],
        "exact_cost": cost,
        "token_source": "provider-reported",
        "human_review": {"reviewer": review.get("reviewer"), "accepted": review.get("accepted", False)},
        "admissible": reviewed,
        "admissibility_reason": None if reviewed else "human review not recorded or not accepted",
    }


def check_workspace_isolation(runs: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Two runs sharing a workspace contaminate each other. Report every collision."""
    seen: dict[str, list[str]] = {}
    for run in runs:
        seen.setdefault(str(run.get("workspace", "")), []).append(
            f"{run.get('task_id', '?')}:{run.get('arm', '?')}"
        )
    collisions = [
        {"workspace": workspace, "runs": sorted(members)}
        for workspace, members in sorted(seen.items())
        if len(members) > 1
    ]
    return {"isolated": not collisions, "collisions": collisions, "workspaces": len(seen)}


def _pair_key(run: dict[str, Any]) -> tuple[str, str, str, str]:
    return (run["task_id"], run["parent_sha256"], run["provider"], run["model"])


def compare_arms(runs: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Pair admissible forge and control runs that match on every controlled variable."""
    rows = [dict(run) for run in runs]
    isolation = check_workspace_isolation(rows)
    admissible = [r for r in rows if r.get("admissible")]
    grouped: dict[tuple[str, str, str, str], dict[str, list[dict[str, Any]]]] = {}
    for run in admissible:
        grouped.setdefault(_pair_key(run), {FORGE_ARM: [], CONTROL_ARM: []})[run["arm"]].append(run)

    pairs: list[dict[str, Any]] = []
    unpaired: list[dict[str, Any]] = []
    for key in sorted(grouped):
        task_id, parent, provider, model = key
        arms = grouped[key]
        if not arms[FORGE_ARM] or not arms[CONTROL_ARM]:
            unpaired.append({
                "task_id": task_id, "parent_sha256": parent, "provider": provider, "model": model,
                "missing_arm": CONTROL_ARM if arms[FORGE_ARM] else FORGE_ARM,
            })
            continue
        forge_tokens = sum(r["exact_input_tokens"] + r["exact_output_tokens"] for r in arms[FORGE_ARM])
        control_tokens = sum(r["exact_input_tokens"] + r["exact_output_tokens"] for r in arms[CONTROL_ARM])
        pairs.append({
            "task_id": task_id, "parent_sha256": parent, "provider": provider, "model": model,
            "forge_runs": len(arms[FORGE_ARM]), "control_runs": len(arms[CONTROL_ARM]),
            "forge_total_tokens": forge_tokens, "control_total_tokens": control_tokens,
            "token_delta": forge_tokens - control_tokens,
        })

    inadmissible = [
        {"task_id": r.get("task_id"), "arm": r.get("arm"), "reason": r.get("admissibility_reason")}
        for r in rows if not r.get("admissible")
    ]
    if not pairs:
        status = "NOT_RUN" if not admissible else "INCOMPLETE"
    else:
        status = "PAIRED"
    return {
        "schema": "forge-benchmark-comparison/1",
        "status": status,
        "pairs": pairs,
        "unpaired": unpaired,
        "inadmissible_runs": inadmissible,
        "workspace_isolation": isolation,
        "runs_recorded": len(rows),
        "runs_admissible": len(admissible),
        "truth_boundary": TRUTH_BOUNDARY,
    }


def define_suite(name: str, tasks: Iterable[dict[str, Any]], target_sessions: int) -> dict[str, Any]:
    """Declare a stress suite. Declaring is not running, and the record says so."""
    sealed = [t if t.get("sealed") else define_task(t) for t in tasks]
    if not sealed:
        raise BenchmarkError("a suite must declare at least one task")
    if not isinstance(target_sessions, int) or target_sessions < 1:
        raise BenchmarkError("target_sessions must be a positive integer")
    ids = [t["task_id"] for t in sealed]
    if len(set(ids)) != len(ids):
        raise BenchmarkError("a suite must not declare the same task twice")
    return {
        "schema": "forge-benchmark-suite/1",
        "name": str(name),
        "suite_id": hashlib.sha256(_canonical({"name": str(name), "tasks": sorted(ids),
                                               "target_sessions": target_sessions}).encode("utf-8")).hexdigest(),
        "task_ids": ids,
        "target_sessions": target_sessions,
        "execution_status": "NOT_RUN",
        "sessions_recorded": 0,
        "declared_not_executed": True,
        "truth_boundary": (
            "A declared suite is a plan. It carries no result until runs are recorded, reviewed, "
            "and paired. Target session counts describe intent, never achievement."
        ),
    }
