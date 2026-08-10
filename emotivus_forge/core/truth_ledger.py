"""Append-only, hash-chained witness ledger: claim -> ground truth -> verdict.

This is the durable home for the "man with the binoculars" role: a record of claims
made across a collaboration (governance docs, bus messages, checkpoints) each bound to
independently-verifiable ground truth (git objects, file bytes, run IDs) with a verdict.

It is deliberately SEPARATE from the Forge event ledger (`core/ledger.py`, which records
Forge's own lifecycle events) and from ledger-assertions (`core/ledger_assertions.py`,
which record obligations to re-check). This ledger records witness *history*.

Honesty invariants (carried from Forge's founding "never upgrade NOT_RUN to PASS" rule):
  * Append-only. Entries are never mutated or deleted.
  * A changed verdict is a NEW entry that SUPERSEDES the prior one; the superseded entry
    stays readable and the lineage is preserved (supersede, don't delete).
  * No auto-upgrade. Nothing here changes an entry's verdict. UNVERIFIABLE is terminal
    for its entry and never silently becomes CONFIRMED.
  * Hash-chained. Every entry carries the canonical hash of the prior entry, so any
    tamper (including an edited verdict) is detectable.
  * Provenance-split verdicts (schema 2, field-driven — see
    planning/OBSERVED-MISS-unbound-confirmed.md). CONFIRMED is reserved for
    binder-derived verdicts carrying a reproduce command and a ground-truth binding;
    an unbound human/model judgement is ATTESTED. Enforced at write time
    (`append_claim` refuses an unbound CONFIRMED) and at read time (`verify_ledger`
    flags one that was smuggled in), so a hash-chained HEALTHY status can no longer
    dress up unverified assertions as machine-verified truth.

Boundary: this ledger records verdicts and their provenance. It does NOT re-derive
ground truth (that is the binder track). `verify_ledger` proves chain integrity and
provenance discipline, not the correctness of any single verdict.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .common import append_jsonl, read_jsonl, read_jsonl_report, utc_now
from .paths import ForgePaths

SCHEMA = 2
# Verdicts split the single positive outcome by PROVENANCE, so the ledger can never
# again render an unbound assertion as machine-verified truth:
#   CONFIRMED  — true AND re-derived by a binder; requires a reproduce command plus a
#                ground-truth binding. The only "machine-verified true" verdict.
#   ATTESTED   — asserted true by a human/model from reasoning: honest, but UNBOUND.
#                Never silently upgraded to CONFIRMED without a binder re-deriving it.
#   CONTRADICTED / UNVERIFIABLE / INCOMPLETE — as before; UNVERIFIABLE stays terminal.
VERDICTS = {"CONFIRMED", "ATTESTED", "CONTRADICTED", "UNVERIFIABLE", "INCOMPLETE"}
DERIVATIONS = {"binder", "asserted"}
_CANONICAL_EXCLUDED = {"entry_hash"}

TRUTH_LEDGER_BOUNDARY = (
    "This ledger records witness verdicts and their provenance, append-only and "
    "supersede-not-delete. It does not re-derive ground truth; an entry is only as sound "
    "as the method that produced its verdict. CONFIRMED is reserved for binder-derived "
    "verdicts that carry a re-runnable reproduce command; a human/model judgement is "
    "ATTESTED, never CONFIRMED. Verification proves chain integrity and that no CONFIRMED "
    "entry is unbound — not that any single verdict is correct."
)


def _is_binder_backed(derivation: Any, reproduce: Any, ground_truth: Any) -> bool:
    """True only when a binder re-derived the verdict and left the evidence to re-run it.

    A CONFIRMED verdict must carry this backing: derivation ``binder``, a non-empty
    reproduce command (what a verifier independently re-runs), and a real ground-truth
    binding (kind other than ``none``). The ledger does not itself execute the command —
    that is the binder track's job — but it refuses to call anything CONFIRMED unless the
    re-runnable proof recipe is present.
    """
    if str(derivation or "").strip() != "binder":
        return False
    if not str(reproduce or "").strip():
        return False
    kind = str(ground_truth.get("kind", "")).strip() if isinstance(ground_truth, dict) else ""
    return bool(kind) and kind != "none"


def _canonical_hash(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key not in _CANONICAL_EXCLUDED}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _entry_id(timestamp: str, semantic: dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(semantic, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:10]
    return f"tl-{timestamp.replace('-', '').replace(':', '')[:15]}-{digest}"


def _require_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Truth-ledger entry requires {label}.")
    return text


def _normalize_ground_truth(ground_truth: Any) -> dict[str, Any]:
    if ground_truth in (None, ""):
        return {"kind": "none"}
    if not isinstance(ground_truth, dict):
        raise ValueError("Truth-ledger ground_truth must be an object.")
    kind = str(ground_truth.get("kind", "")).strip() or "none"
    normalized = {"kind": kind}
    for key in ("pointer", "observed", "expected"):
        if key in ground_truth and ground_truth[key] not in (None, ""):
            normalized[key] = ground_truth[key]
    return normalized


def truth_ledger_path(project_root: Path) -> Path:
    return ForgePaths(project_root).truth_ledger


def read_ledger(project_root: Path) -> list[dict[str, Any]]:
    return read_jsonl(truth_ledger_path(project_root))


def _tip_ids(entries: list[dict[str, Any]]) -> set[str]:
    superseded = {str(entry.get("supersedes", "")) for entry in entries if entry.get("supersedes")}
    return {str(entry.get("id", "")) for entry in entries if str(entry.get("id", "")) not in superseded}


def append_claim(
    project_root: Path,
    *,
    claim: str,
    verdict: str,
    subject: str = "project",
    source: str = "",
    source_ref: str = "",
    ground_truth: Any = None,
    method: str = "",
    derivation: str = "asserted",
    reproduce: str = "",
    observer: str = "forge-observer",
    note: str = "",
    supersedes: str = "",
) -> dict[str, Any]:
    """Append one witness entry. A changed verdict must supersede a prior entry, never edit it.

    Provenance is enforced here so the ledger cannot record an unverified claim as
    verified truth. CONFIRMED is accepted only when it is binder-backed (derivation
    ``binder`` with a reproduce command and a ground-truth binding). A positive judgement
    without that backing must be recorded as ATTESTED — this is Forge's founding
    "never upgrade NOT_RUN to PASS" rule applied to the ledger itself.
    """
    claim_text = _require_text(claim, "a claim")
    verdict = str(verdict or "").strip().upper()
    if verdict not in VERDICTS:
        raise ValueError(f"Truth-ledger verdict must be one of {sorted(VERDICTS)}; got {verdict!r}.")
    derivation = (str(derivation or "").strip().lower() or "asserted")
    if derivation not in DERIVATIONS:
        raise ValueError(f"Truth-ledger derivation must be one of {sorted(DERIVATIONS)}; got {derivation!r}.")
    reproduce = str(reproduce or "").strip()
    subject = _require_text(subject, "a subject")
    supersedes = str(supersedes or "").strip()

    ground_truth_norm = _normalize_ground_truth(ground_truth)
    binder_backed = _is_binder_backed(derivation, reproduce, ground_truth_norm)
    if derivation == "binder" and not binder_backed:
        raise ValueError(
            "A binder-derived entry must carry a reproduce command and a ground-truth binding "
            "(kind other than 'none'); without them it is not binder-backed."
        )
    if verdict == "CONFIRMED" and not binder_backed:
        raise ValueError(
            "CONFIRMED is reserved for binder-derived verdicts: it requires derivation='binder', "
            "a reproduce command, and a ground-truth binding. Record a human/model judgement as "
            "ATTESTED, or supply the reproduce command a binder used. Forge never renders an "
            "unbound assertion as CONFIRMED."
        )
    if verdict == "ATTESTED" and derivation == "binder":
        raise ValueError(
            "ATTESTED is for an unbound human/model judgement; a binder-derived positive verdict "
            "is CONFIRMED, not ATTESTED."
        )

    existing = read_ledger(project_root)
    lineage = ""
    if supersedes:
        target = next((entry for entry in existing if str(entry.get("id", "")) == supersedes), None)
        if target is None:
            raise ValueError(f"Cannot supersede unknown truth-ledger entry: {supersedes}")
        if supersedes not in _tip_ids(existing):
            raise ValueError(
                f"Truth-ledger entry {supersedes} is already superseded; supersede the current tip of its lineage instead."
            )
        lineage = str(target.get("lineage", "")) or supersedes

    timestamp = utc_now()
    semantic = {
        "subject": subject,
        "claim": claim_text,
        "verdict": verdict,
        "derivation": derivation,
        "source": str(source or ""),
        "observer": str(observer or "forge-observer"),
        "supersedes": supersedes,
    }
    entry_id = _entry_id(timestamp, semantic)
    if not lineage:
        lineage = entry_id
    previous_hash = _canonical_hash(existing[-1]) if existing else ""
    entry = {
        "schema": SCHEMA,
        "id": entry_id,
        "utc": timestamp,
        "subject": subject,
        "claim": {"text": claim_text, "source": str(source or ""), "source_ref": str(source_ref or "")},
        "ground_truth": ground_truth_norm,
        "verdict": verdict,
        "derivation": derivation,
        "reproduce": reproduce,
        "method": str(method or ""),
        "observer": str(observer or "forge-observer"),
        "note": str(note or ""),
        "supersedes": supersedes,
        "lineage": lineage,
        "previous_entry_hash": previous_hash,
    }
    entry["entry_hash"] = _canonical_hash(entry)
    append_jsonl(truth_ledger_path(project_root), entry)
    return entry


def supersede_claim(
    project_root: Path,
    target_id: str,
    *,
    claim: str,
    verdict: str,
    **fields: Any,
) -> dict[str, Any]:
    """Convenience wrapper: append a new entry that supersedes ``target_id``.

    The prior entry is never modified; the new entry links to it and inherits its lineage.
    """
    target_id = _require_text(target_id, "a target entry id")
    return append_claim(project_root, claim=claim, verdict=verdict, supersedes=target_id, **fields)


def append_binder_verdict(
    project_root: Path,
    *,
    claim: str,
    verdict: str,
    reproduce: str,
    ground_truth: Any,
    subject: str = "project",
    source: str = "",
    source_ref: str = "",
    method: str = "",
    observer: str = "forge-binder",
    note: str = "",
    supersedes: str = "",
) -> dict[str, Any]:
    """Record a verdict a binder re-derived. Sets derivation='binder' and carries the
    reproduce command, so a CONFIRMED emitted this way is genuinely binder-backed. This is
    the only honest path to a CONFIRMED entry; hand-asserted claims must use ATTESTED."""
    return append_claim(
        project_root,
        claim=claim,
        verdict=verdict,
        derivation="binder",
        reproduce=reproduce,
        ground_truth=ground_truth,
        subject=subject,
        source=source,
        source_ref=source_ref,
        method=method,
        observer=observer,
        note=note,
        supersedes=supersedes,
    )


# A binder's own verdict vocabulary maps into the ledger's. NOT_RUN never becomes a
# positive verdict — it lands as UNVERIFIABLE (terminal), preserving "never upgrade
# NOT_RUN to PASS". GAPS/CONTRADICTED are negative; COVERED/CONFIRMED are positive and,
# because they arrive via a binder run with reproduce evidence, are legitimately CONFIRMED.
_BINDER_VERDICT_MAP = {
    "CONFIRMED": "CONFIRMED",
    "COVERED": "CONFIRMED",
    "CONTRADICTED": "CONTRADICTED",
    "GAPS": "CONTRADICTED",
    "NOT_RUN": "UNVERIFIABLE",
}


def record_binder_result(
    project_root: Path,
    result: dict[str, Any],
    *,
    subject: str = "project",
    source: str = "forge bind",
    observer: str = "forge-binder",
    supersedes: str = "",
) -> dict[str, Any]:
    """Bridge a G1 binder result (``forge bind`` / source_anchored_release / gate_diff /
    gate_coverage) into a binder-derived ledger entry.

    The reproduce evidence and ground-truth binding are taken from the binder's own
    findings, so the emitted verdict carries a re-runnable recipe rather than a bare word.
    A positive binder verdict with no reproduce evidence is refused by ``append_claim``
    (it cannot be CONFIRMED), which is the correct failure: a binder that cannot say how it
    checked has not earned CONFIRMED.
    """
    raw_verdict = str(result.get("verdict", "")).strip().upper()
    verdict = _BINDER_VERDICT_MAP.get(raw_verdict, "UNVERIFIABLE")
    findings = result.get("findings", []) if isinstance(result.get("findings"), list) else []
    reproduce = "; ".join(
        str(f.get("reproduce", "")).strip()
        for f in findings
        if isinstance(f, dict) and str(f.get("reproduce", "")).strip()
    )
    head = str(result.get("head", "")).strip()
    if not reproduce and verdict != "CONFIRMED":
        # A non-positive verdict's re-derivation recipe is the bind invocation itself
        # (re-running it re-derives NOT_RUN/CONTRADICTED). A CONFIRMED, by contrast,
        # must carry the finding-level evidence — no fallback is offered there, so a
        # binder that cannot say how it checked cannot yield CONFIRMED.
        reproduce = f"forge bind {str(result.get('target', '')).strip() or 'unknown'}" + (f" --head {head}" if head else "")
    ground_truth = {
        "kind": "binder",
        "pointer": head or str(result.get("target", "")).strip() or "binder-run",
        "observed": raw_verdict or "NONE",
    }
    target = str(result.get("target", "")).strip()
    claim = f"binder verdict {raw_verdict or 'NONE'} for {target or 'target'}" + (f" @ {head}" if head else "")
    return append_binder_verdict(
        project_root,
        claim=claim,
        verdict=verdict,
        reproduce=reproduce,
        ground_truth=ground_truth,
        subject=subject,
        source=source,
        source_ref=head,
        method="forge bind",
        observer=observer,
        note=str(result.get("truth_boundary", "")),
        supersedes=supersedes,
    )


def verify_ledger(project_root: Path) -> dict[str, Any]:
    """Verify chain integrity and report verdict tallies. Chain integrity only — not verdict correctness."""
    path = truth_ledger_path(project_root)
    rows, syntax_issues = read_jsonl_report(path)
    issues: list[dict[str, Any]] = [issue.to_dict() for issue in syntax_issues]
    unbound_confirmed: list[str] = []
    previous_hash = ""
    for index, row in enumerate(rows, 1):
        actual = str(row.get("entry_hash", ""))
        expected = _canonical_hash(row)
        if not actual:
            issues.append({"path": str(path), "line": index, "message": "truth-ledger entry is missing its entry hash"})
        elif actual != expected:
            issues.append({"path": str(path), "line": index, "message": "truth-ledger entry hash does not match its content"})
        declared_previous = str(row.get("previous_entry_hash", ""))
        if declared_previous != previous_hash:
            issues.append({"path": str(path), "line": index, "message": "truth-ledger previous-entry hash does not match the preceding record"})
        verdict = str(row.get("verdict", ""))
        if verdict not in VERDICTS:
            issues.append({"path": str(path), "line": index, "message": f"truth-ledger entry has an unknown verdict: {verdict!r}"})
        elif verdict == "CONFIRMED" and not _is_binder_backed(row.get("derivation"), row.get("reproduce"), row.get("ground_truth")):
            # A CONFIRMED that is not binder-backed must not exist: it slipped past the
            # constructor (hand-edited, tampered, or written under an older schema). Flag
            # it rather than render an unbound assertion as verified truth.
            unbound_confirmed.append(str(row.get("id", "")))
            issues.append({
                "path": str(path),
                "line": index,
                "message": "CONFIRMED entry is not binder-backed (needs derivation='binder', a reproduce command, and a ground-truth binding); it must be ATTESTED",
            })
        previous_hash = expected
    tip_ids = _tip_ids(rows)
    tallies_all = _tally(rows)
    tallies_current = _tally([row for row in rows if str(row.get("id", "")) in tip_ids])
    return {
        "schema": SCHEMA,
        "status": "BLOCKED" if issues else "HEALTHY",
        "records": len(rows),
        "lineage_count": len({str(row.get("lineage", "")) for row in rows}),
        "tallies_current": tallies_current,
        "tallies_all": tallies_all,
        "derivations_current": _derivation_tally([row for row in rows if str(row.get("id", "")) in tip_ids]),
        "unbound_confirmed": unbound_confirmed,
        "contradicted_tips": sorted(
            str(row.get("id", "")) for row in rows if str(row.get("id", "")) in tip_ids and row.get("verdict") == "CONTRADICTED"
        ),
        "issues": issues,
        "truth_boundary": TRUTH_LEDGER_BOUNDARY,
    }


def _tally(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {verdict: 0 for verdict in sorted(VERDICTS)}
    for row in rows:
        verdict = str(row.get("verdict", ""))
        if verdict in counts:
            counts[verdict] += 1
    return counts


def _derivation_tally(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {name: 0 for name in sorted(DERIVATIONS)}
    for row in rows:
        # Entries written before schema 2 carry no derivation; they are unbound by default.
        derivation = str(row.get("derivation", "asserted") or "asserted")
        if derivation in counts:
            counts[derivation] += 1
    return counts


def _ordered_lineage(root: dict[str, Any], by_supersedes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = [root]
    current_id = str(root.get("id", ""))
    seen = {current_id}
    while current_id in by_supersedes:
        nxt = by_supersedes[current_id]
        nxt_id = str(nxt.get("id", ""))
        if nxt_id in seen:  # defensive: never loop on a malformed chain
            break
        ordered.append(nxt)
        seen.add(nxt_id)
        current_id = nxt_id
    return ordered


def current_view(project_root: Path) -> dict[str, Any]:
    """Fold supersession: the current verdict per claim-lineage, with history and verdict flips."""
    rows = read_ledger(project_root)
    by_supersedes: dict[str, dict[str, Any]] = {}
    for row in rows:
        parent = str(row.get("supersedes", ""))
        if parent:
            by_supersedes[parent] = row
    lineage_groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        lineage_groups.setdefault(str(row.get("lineage", "")), []).append(row)

    lineages: list[dict[str, Any]] = []
    total_flips = 0
    for lineage_id, group in lineage_groups.items():
        root = next((row for row in group if not str(row.get("supersedes", ""))), group[0])
        ordered = _ordered_lineage(root, by_supersedes)
        flips: list[dict[str, str]] = []
        for earlier, later in zip(ordered, ordered[1:]):
            if earlier.get("verdict") != later.get("verdict"):
                flips.append({
                    "from_verdict": str(earlier.get("verdict", "")),
                    "to_verdict": str(later.get("verdict", "")),
                    "from_id": str(earlier.get("id", "")),
                    "to_id": str(later.get("id", "")),
                })
        total_flips += len(flips)
        tip = ordered[-1]
        lineages.append({
            "lineage": lineage_id,
            "subject": str(tip.get("subject", "")),
            "claim": tip.get("claim", {}).get("text", "") if isinstance(tip.get("claim"), dict) else "",
            "current_verdict": str(tip.get("verdict", "")),
            "current_derivation": str(tip.get("derivation", "asserted") or "asserted"),
            "tip_id": str(tip.get("id", "")),
            "revisions": len(ordered) - 1,
            "verdict_flips": flips,
            "history": [
                {"id": str(item.get("id", "")), "verdict": str(item.get("verdict", "")), "utc": str(item.get("utc", ""))}
                for item in ordered
            ],
        })
    lineages.sort(key=lambda item: item["lineage"])
    return {
        "schema": SCHEMA,
        "lineage_count": len(lineages),
        "verdict_flip_count": total_flips,
        "tallies_current": _tally([
            next(row for row in rows if str(row.get("id", "")) == lineage["tip_id"]) for lineage in lineages
        ]) if lineages else _tally([]),
        "lineages": lineages,
        "truth_boundary": TRUTH_LEDGER_BOUNDARY,
    }
