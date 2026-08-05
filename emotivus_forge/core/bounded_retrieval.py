from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from .common import read_jsonl
from .continuity_register import TRUST_RANK, continuity_register_summary
from .paths import ForgePaths
from .session_close import latest_session_close

TOKEN_RE = re.compile(r"[a-z0-9]+(?:[._:/+#-][a-z0-9]+)*", re.IGNORECASE)
NEVER_FADE_KINDS = {"knowledge-gap", "unresolved-risk", "next-action", "authority-contradiction", "merge-candidate", "migration-collision"}
PRIORITY_WEIGHT = {"blocker": 5.0, "high": 3.0, "medium": 1.5, "low": 0.5}


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(TOKEN_RE.findall(text))


def token_set(value: Any) -> set[str]:
    return {token for token in normalize_text(value).split() if token}


def token_similarity(left: Any, right: Any) -> float:
    a, b = token_set(left), token_set(right)
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    jaccard = intersection / union if union else 0.0
    containment = intersection / min(len(a), len(b))
    return max(jaccard, containment * 0.92)


def _item_text(item: dict[str, Any]) -> str:
    values = [
        item.get("stable_id", ""), item.get("key", ""), item.get("title", ""), item.get("text", ""),
        item.get("value", ""), item.get("question", ""), item.get("rationale", ""), item.get("impact", ""),
        item.get("required_evidence", ""), item.get("reason", ""), item.get("kind", ""),
    ]
    return " ".join(str(value) for value in values if value not in (None, "", []))


def _continuity_items(project_root: Path) -> list[dict[str, Any]]:
    summary = continuity_register_summary(project_root)
    items: list[dict[str, Any]] = []
    stale = summary.get("status") != "CURRENT"
    for fact in summary.get("facts", []):
        if not isinstance(fact, dict):
            continue
        items.append({
            "stable_id": f"fact:{fact.get('fact_id', fact.get('key', ''))}",
            "kind": "continuity-fact",
            "key": str(fact.get("key", "")),
            "value": fact.get("value"),
            "rationale": str(fact.get("rationale", "")),
            "impact": str(fact.get("impact", "")),
            "trust": str(fact.get("trust", "automatically-extracted")),
            "trust_rank": int(fact.get("trust_rank", 0) or 0),
            "support": fact.get("support", []),
            "support_status": "stale" if stale else "current",
            "never_fade": str(fact.get("trust")) == "owner-declared",
            "source": "continuity-register",
        })
    for gap in summary.get("gaps", []):
        if not isinstance(gap, dict) or gap.get("status") != "open":
            continue
        items.append({
            "stable_id": f"gap:{gap.get('gap_id', '')}",
            "kind": "knowledge-gap",
            "key": str(gap.get("gap_id", "")),
            "question": str(gap.get("question", "")),
            "required_evidence": str(gap.get("required_evidence", "")),
            "priority": str(gap.get("priority", "medium")),
            "blocking_scopes": list(gap.get("blocking_scopes", [])) if isinstance(gap.get("blocking_scopes"), list) else [],
            "owner": str(gap.get("owner", "")),
            "trust": "project-evidenced",
            "trust_rank": TRUST_RANK["project-evidenced"],
            "support": gap.get("evidence", []),
            "support_status": "stale" if stale else "current",
            "never_fade": True,
            "source": "continuity-register",
        })
    return items


def _session_items(project_root: Path) -> list[dict[str, Any]]:
    event = latest_session_close(project_root)
    if not isinstance(event, dict):
        return []
    payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}
    event_id = str(event.get("id", ""))
    utc = str(event.get("utc", ""))
    items: list[dict[str, Any]] = []
    for index, decision in enumerate(payload.get("decisions", []), 1):
        if isinstance(decision, dict):
            items.append({
                "stable_id": f"decision:{event_id}:{index}", "kind": "decision", "text": str(decision.get("text", "")),
                "rationale": str(decision.get("rationale", "")), "trust": "developer-recorded", "trust_rank": TRUST_RANK["developer-recorded"],
                "support": [{"kind": "ledger-event", "event_id": event_id}], "support_status": "current", "recorded_utc": utc,
                "never_fade": True, "source": "session-close",
            })
    for index, fact in enumerate(payload.get("owner_facts", []), 1):
        if isinstance(fact, dict):
            items.append({
                "stable_id": f"owner-fact:{event_id}:{index}", "kind": "owner-fact", "text": str(fact.get("text", "")),
                "impact": str(fact.get("impact", "")), "trust": "owner-declared", "trust_rank": TRUST_RANK["owner-declared"],
                "support": [{"kind": "ledger-event", "event_id": event_id}], "support_status": "current", "recorded_utc": utc,
                "never_fade": True, "source": "session-close",
            })
    for index, risk in enumerate(payload.get("unresolved_risks", []), 1):
        text = str(risk or "").strip()
        if text:
            items.append({
                "stable_id": f"risk:{event_id}:{index}", "kind": "unresolved-risk", "text": text,
                "trust": "developer-recorded", "trust_rank": TRUST_RANK["developer-recorded"],
                "support": [{"kind": "ledger-event", "event_id": event_id}], "support_status": "current", "recorded_utc": utc,
                "never_fade": True, "source": "session-close",
            })
    next_action = payload.get("next_action", {}) if isinstance(payload.get("next_action"), dict) else {}
    text = str(next_action.get("text", "")).strip()
    if text:
        items.append({
            "stable_id": f"next-action:{event_id}", "kind": "next-action", "text": text,
            "trust": "developer-recorded", "trust_rank": TRUST_RANK["developer-recorded"],
            "support": [{"kind": "ledger-event", "event_id": event_id}], "support_status": "current", "recorded_utc": utc,
            "never_fade": True, "source": "session-close",
        })
    return items


def _ledger_items(project_root: Path, *, limit: int = 120) -> list[dict[str, Any]]:
    rows = read_jsonl(ForgePaths(project_root).ledger)
    items: list[dict[str, Any]] = []
    for event in rows[-limit:]:
        if not isinstance(event, dict):
            continue
        kind = str(event.get("kind", ""))
        if kind == "session-close":
            continue
        payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}
        text_parts = [kind]
        for key in ("summary", "reason", "title", "claim", "next_action", "register_id", "candidate_id", "inventory_id"):
            if payload.get(key):
                text_parts.append(str(payload.get(key)))
        items.append({
            "stable_id": f"ledger:{event.get('id', '')}", "kind": "ledger-event", "text": " — ".join(text_parts),
            "trust": "developer-recorded", "trust_rank": TRUST_RANK["developer-recorded"],
            "support": [{"kind": "ledger-event", "event_id": str(event.get("id", ""))}], "support_status": "current",
            "recorded_utc": str(event.get("utc", "")), "never_fade": kind in NEVER_FADE_KINDS, "source": "ledger",
        })
    return items


def _deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    exact: dict[str, dict[str, Any]] = {}
    for item in items:
        key = normalize_text(item.get("key") or item.get("text") or item.get("question") or item.get("value"))
        if not key:
            key = str(item.get("stable_id", ""))
        current = exact.get(key)
        if current is None:
            exact[key] = item
            continue
        current_rank = (int(current.get("trust_rank", 0)), current.get("support_status") == "current", str(current.get("recorded_utc", "")))
        new_rank = (int(item.get("trust_rank", 0)), item.get("support_status") == "current", str(item.get("recorded_utc", "")))
        if new_rank > current_rank:
            exact[key] = item
    candidates = list(exact.values())
    kept: list[dict[str, Any]] = []
    for item in sorted(candidates, key=lambda row: (-int(row.get("trust_rank", 0)), str(row.get("stable_id", "")))):
        duplicate_index = next((i for i, existing in enumerate(kept) if token_similarity(_item_text(item), _item_text(existing)) >= 0.94), None)
        if duplicate_index is None:
            kept.append(item)
            continue
        existing = kept[duplicate_index]
        item_rank = (int(item.get("trust_rank", 0)), item.get("support_status") == "current")
        existing_rank = (int(existing.get("trust_rank", 0)), existing.get("support_status") == "current")
        if item_rank > existing_rank:
            kept[duplicate_index] = item
    return kept


def _rankings(items: list[dict[str, Any]], query: str) -> dict[str, list[str]]:
    normalized_query = normalize_text(query)
    query_tokens = token_set(query)
    exact: list[tuple[float, str]] = []
    similarity: list[tuple[float, str]] = []
    authority: list[tuple[float, str]] = []
    urgency: list[tuple[float, str]] = []
    for item in items:
        stable_id = str(item.get("stable_id", ""))
        haystack = _item_text(item)
        normalized_haystack = normalize_text(haystack)
        exact_score = 0.0
        for field in (item.get("stable_id"), item.get("key"), item.get("title")):
            field_norm = normalize_text(field)
            if normalized_query and field_norm and (normalized_query == field_norm or normalized_query in field_norm):
                exact_score = max(exact_score, 3.0 if normalized_query == field_norm else 2.0)
        if query_tokens and query_tokens <= token_set(haystack):
            exact_score = max(exact_score, 1.5)
        if exact_score:
            exact.append((exact_score, stable_id))
        sim = token_similarity(query, haystack)
        if sim:
            similarity.append((sim, stable_id))
        trust_score = float(item.get("trust_rank", 0)) + (0.5 if item.get("support_status") == "current" else -1.0)
        authority.append((trust_score, stable_id))
        urgent = PRIORITY_WEIGHT.get(str(item.get("priority", "")), 0.0)
        if item.get("never_fade"):
            urgent += 2.0
        if item.get("kind") in NEVER_FADE_KINDS:
            urgent += 2.0
        if urgent:
            urgency.append((urgent, stable_id))
    sort = lambda rows: [stable_id for _, stable_id in sorted(rows, key=lambda pair: (-pair[0], pair[1]))]
    return {"exact": sort(exact), "similarity": sort(similarity), "authority": sort(authority), "urgency": sort(urgency)}


def _rrf(rankings: dict[str, list[str]], *, k: int = 60) -> tuple[dict[str, float], dict[str, list[str]]]:
    scores: dict[str, float] = defaultdict(float)
    reasons: dict[str, list[str]] = defaultdict(list)
    for channel, ordered in rankings.items():
        for rank, stable_id in enumerate(ordered, 1):
            scores[stable_id] += 1.0 / (k + rank)
            reasons[stable_id].append(f"{channel} rank {rank}")
    return dict(scores), dict(reasons)


def _relationship_trace(selected: list[dict[str, Any]], *, depth: int = 1, node_budget: int = 24) -> dict[str, Any]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    nodes: dict[str, dict[str, str]] = {}
    for item in selected:
        item_id = str(item.get("stable_id", ""))
        nodes[item_id] = {"kind": str(item.get("kind", "")), "label": str(item.get("key") or item.get("text") or item.get("question") or item_id)[:180]}
        for support in item.get("support", []):
            if not isinstance(support, dict):
                continue
            if support.get("kind") == "project-file":
                support_id = f"file:{support.get('path', '')}"
            elif support.get("kind") == "ledger-event":
                support_id = f"ledger:{support.get('event_id', '')}"
            else:
                support_id = f"support:{normalize_text(support.get('note', ''))[:80]}"
            nodes[support_id] = {"kind": str(support.get("kind", "support")), "label": str(support.get("path") or support.get("event_id") or support.get("note") or support_id)[:180]}
            adjacency[item_id].add(support_id); adjacency[support_id].add(item_id)
    starts = [str(item.get("stable_id", "")) for item in selected]
    visited: set[str] = set(starts)
    queue = deque((node, 0) for node in starts)
    edges: set[tuple[str, str]] = set()
    while queue and len(visited) <= node_budget:
        node, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        for neighbor in sorted(adjacency.get(node, set())):
            edges.add(tuple(sorted((node, neighbor))))
            if neighbor not in visited and len(visited) < node_budget:
                visited.add(neighbor); queue.append((neighbor, current_depth + 1))
    return {
        "depth": depth,
        "node_budget": node_budget,
        "nodes": [{"id": node_id, **nodes.get(node_id, {})} for node_id in sorted(visited)],
        "edges": [{"from": left, "to": right} for left, right in sorted(edges) if left in visited and right in visited],
    }


def retrieve_continuity(project_root: Path, query: str, *, result_budget: int = 6, relationship_depth: int = 1) -> dict[str, Any]:
    project_root = project_root.resolve()
    result_budget = max(1, min(int(result_budget), 30))
    relationship_depth = max(0, min(int(relationship_depth), 2))
    query = str(query or "").strip()
    items = _deduplicate(_continuity_items(project_root) + _session_items(project_root) + _ledger_items(project_root))
    rankings = _rankings(items, query)
    scores, reasons = _rrf(rankings)
    by_id = {str(item.get("stable_id", "")): item for item in items}
    mandatory = [item for item in items if item.get("never_fade") and (item.get("kind") in NEVER_FADE_KINDS or item.get("priority") in {"blocker", "high"})]
    mandatory_ids = {str(item.get("stable_id", "")) for item in mandatory}
    ordered_ids = sorted(scores, key=lambda stable_id: (-scores[stable_id], -int(by_id.get(stable_id, {}).get("trust_rank", 0)), stable_id))
    selected: list[dict[str, Any]] = []
    for item in sorted(mandatory, key=lambda row: (-PRIORITY_WEIGHT.get(str(row.get("priority", "")), 0.0), str(row.get("stable_id", "")))):
        if len(selected) >= result_budget:
            break
        selected.append(item)
    for stable_id in ordered_ids:
        if len(selected) >= result_budget:
            break
        if stable_id in mandatory_ids or stable_id not in by_id:
            continue
        selected.append(by_id[stable_id])
    results: list[dict[str, Any]] = []
    for item in selected:
        stable_id = str(item.get("stable_id", ""))
        results.append({
            **item,
            "retrieval_score": round(float(scores.get(stable_id, 0.0)), 8),
            "selection_reasons": (["never-fade"] if stable_id in mandatory_ids else []) + reasons.get(stable_id, []),
        })
    return {
        "schema": 1,
        "status": "CURRENT" if results else "EMPTY",
        "query": query,
        "result_budget": result_budget,
        "candidate_count": len(items),
        "result_count": len(results),
        "results": results,
        "ranking_channels": {name: len(values) for name, values in rankings.items()},
        "relationship_trace": _relationship_trace(results, depth=relationship_depth),
        "truth_boundary": (
            "Retrieval ranks current and historical project records for orientation only. Similarity, frequency, recency, rank fusion, "
            "and graph proximity do not change trust, authority, support validity, project baselines, or release state."
        ),
    }
