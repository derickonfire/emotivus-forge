"""Protocol verify for a multi-agent git collaboration (G1 project-truth; R9, folds R5).

The gap (planning/OBSERVED-MISS-protocol-invariants-only-in-prose.md): the
Claude+Codex collaboration's protocol invariants — claims pin exact heads,
accepts carry bindable receipts, state is structured not prose, supersession
preserves history, irreversible acts are owner-gated, one party holds the baton —
were enforced only by agents reading each other's prose. Prose agreeing with
prose is not verification; a real record in this repo pins a claim to a moving
`main@1780e3b` at a stale head, and the ceremony never caught it.

This instrument checks a DECLARED protocol — structured records supplied in a
config, so the verifier is coupled to no particular bus's markdown and reads no
coordination data it is not handed — against six deterministic invariants. Head
currency reuses the R8 guard (`ref_integrity`), so a moving ref or a
rebased/force-pushed-away head is a CONTRADICTED, never a pass. Verdicts use the
binder vocabulary so a run feeds the truth ledger via ``record_binder_result``.

Advisory, read-only, never authority. It reports what the protocol's own records
do and don't satisfy; it does not authorize anything.
"""
from __future__ import annotations

from typing import Any

from .ref_integrity import FRESH, assess_head

CONFIRMED = "CONFIRMED"
CONTRADICTED = "CONTRADICTED"
NOT_RUN = "NOT_RUN"

RECORD_TYPES = ("claim", "accept", "handoff", "act")
_HEAD_PINNING_TYPES = ("claim", "accept")

PROTOCOL_VERIFY_TRUTH_BOUNDARY = (
    "Forge checks a declared protocol's structured records against fixed invariants: exact "
    "current-head claims (head currency via the R8 guard when --repo is given), bindable "
    "receipts on accepts, structured (not prose-only) state, history-preserving supersession, "
    "owner-gated irreversible acts, and single-baton liveness. It verifies the records it is "
    "handed; it does not parse free prose into records, judge whether a receipt is substantively "
    "adequate, or prove an owner-authorization flag was truly set by the owner. Without --repo, "
    "head PINNING is checked syntactically and currency is not. An unassessable protocol is NOT_RUN."
)


def _finding(check: str, state: str, detail: str, reproduce: str = "") -> dict:
    return {"check": check, "state": state, "detail": detail, "reproduce": reproduce}


def _looks_like_object_id(value: str) -> bool:
    v = value.strip().lower()
    return 7 <= len(v) <= 64 and all(c in "0123456789abcdef" for c in v)


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in ("", "false", "no", "0", "none", "null")
    return bool(value)


def _rid(record: dict, index: int) -> str:
    return str(record.get("id", "")).strip() or f"record[{index}]"


def _superseded_ids(records: list[dict]) -> set[str]:
    return {str(r.get("supersedes", "")).strip() for r in records if str(r.get("supersedes", "")).strip()}


def _self_repro(source: str, rid: str) -> str:
    where = f" --config {source}" if source else ""
    return f"forge protocol verify{where}  # deterministic re-check of record {rid}"


def _check_structured_state(records: list[dict], source: str) -> list[dict]:
    """No state lives only in prose: every record declares a recognized type and party,
    and record ids are unique (many invariants key on the id)."""
    findings: list[dict] = []
    seen: dict[str, int] = {}
    for index, rec in enumerate(records):
        rid = _rid(rec, index)
        rtype = str(rec.get("type", "")).strip()
        party = str(rec.get("party", "")).strip()
        problems = []
        if rtype not in RECORD_TYPES:
            problems.append(f"type {rtype!r} is not one of {list(RECORD_TYPES)}")
        if not party:
            problems.append("no party is named")
        if str(rec.get("id", "")).strip():
            if rid in seen:
                problems.append(f"duplicate record id (also record #{seen[rid] + 1})")
            else:
                seen[rid] = index
        if problems:
            findings.append(_finding(f"structured-state:{rid}", CONTRADICTED,
                                     f"{rid} is prose-only / malformed: " + "; ".join(problems),
                                     _self_repro(source, rid)))
        else:
            findings.append(_finding(f"structured-state:{rid}", CONFIRMED,
                                     f"{rid} is a structured {rtype} by {party}.",
                                     _self_repro(source, rid)))
    return findings


def _check_exact_head(records: list[dict], repo: str, source: str, superseded: set[str]) -> list[dict]:
    """Every CURRENT claim/accept pins an exact head; with --repo, that head must be
    current (R8). Superseded records are history — a claim later revised because its head
    went stale must not be re-flagged, which would false-CONTRADICT the healthy pattern."""
    findings: list[dict] = []
    for index, rec in enumerate(records):
        if str(rec.get("type", "")).strip() not in _HEAD_PINNING_TYPES:
            continue
        rid = _rid(rec, index)
        if rid in superseded:
            continue
        head = str(rec.get("pins_head", "")).strip()
        check = f"exact-head:{rid}"
        if not head:
            findings.append(_finding(check, CONTRADICTED,
                                     f"{rid} pins no head; a claim must pin an exact commit head.",
                                     _self_repro(source, rid)))
            continue
        looks_exact = _looks_like_object_id(head)
        if repo:
            a = assess_head(repo, head)
            kind = a["anchor_kind"]
            if kind in ("local_ref", "remote_ref"):
                findings.append(_finding(check, CONTRADICTED,
                                         f"{rid} pins {head!r}, a {kind} that moves, not an exact commit head.",
                                         a["reproduce"]))
            elif kind == "object_id":
                if a["status"] == FRESH:
                    findings.append(_finding(check, CONFIRMED,
                                             f"{rid} pins current exact head {a['resolved'][:12]}.", a["reproduce"]))
                else:
                    findings.append(_finding(check, CONTRADICTED,
                                             f"{rid} pins {head[:12]} but that head is not current: "
                                             f"[{a['status']}] {a['detail']}", a["reproduce"]))
            elif looks_exact:
                # object-id-shaped but absent from THIS repo: cannot assess currency here
                # (may be a shallow clone or wrong repo) — NOT_RUN, never a false verdict.
                findings.append(_finding(check, NOT_RUN,
                                         f"{rid} pins {head[:12]}, an exact id not present in {repo}; "
                                         f"currency cannot be assessed here.", a["reproduce"]))
            else:
                findings.append(_finding(check, CONTRADICTED,
                                         f"{rid} pins {head!r}, neither an exact commit id nor a resolvable "
                                         f"ref — not pinned to an exact head.", a["reproduce"]))
        elif looks_exact:
            findings.append(_finding(check, CONFIRMED,
                                     f"{rid} pins an exact commit id {head[:12]} (currency not checked: no --repo).",
                                     _self_repro(source, rid)))
        else:
            findings.append(_finding(check, CONTRADICTED,
                                     f"{rid} pins {head!r}, a moving ref name, not an exact commit head.",
                                     _self_repro(source, rid)))
    return findings


def _check_receipts(records: list[dict], source: str, superseded: set[str]) -> list[dict]:
    """Every CURRENT accept carries a bindable receipt: an exact reviewed head + a verifiable id."""
    findings: list[dict] = []
    for index, rec in enumerate(records):
        if str(rec.get("type", "")).strip() != "accept":
            continue
        rid = _rid(rec, index)
        if rid in superseded:
            continue
        receipt = rec.get("receipt")
        check = f"bindable-receipt:{rid}"
        if not isinstance(receipt, dict):
            findings.append(_finding(check, CONTRADICTED,
                                     f"{rid} is an accept with no structured receipt.", _self_repro(source, rid)))
            continue
        reviewed = str(receipt.get("reviewed_head", "")).strip()
        evidence = str(receipt.get("review_id", "") or receipt.get("evidence", "")).strip()
        problems = []
        if not _looks_like_object_id(reviewed):
            problems.append(f"reviewed_head {reviewed!r} is not an exact commit id")
        if not evidence:
            problems.append("no verifiable review_id/evidence")
        if problems:
            findings.append(_finding(check, CONTRADICTED,
                                     f"{rid} receipt is not bindable: " + "; ".join(problems),
                                     _self_repro(source, rid)))
        else:
            findings.append(_finding(check, CONFIRMED,
                                     f"{rid} accept carries a bindable receipt (reviewed {reviewed[:12]}, "
                                     f"id {evidence}).", _self_repro(source, rid)))
    return findings


def _check_supersession(records: list[dict], source: str) -> list[dict]:
    """Supersession preserves history: targets exist, none superseded twice, acyclic."""
    findings: list[dict] = []
    ids = {_rid(rec, i) for i, rec in enumerate(records)}
    superseded_by: dict[str, str] = {}
    forks: list[str] = []
    for index, rec in enumerate(records):
        rid = _rid(rec, index)
        target = str(rec.get("supersedes", "")).strip()
        if not target:
            continue
        check = f"supersession:{rid}"
        if target not in ids:
            findings.append(_finding(check, CONTRADICTED,
                                     f"{rid} supersedes {target!r}, which is not a recorded entry — history "
                                     f"is not preserved.", _self_repro(source, rid)))
            continue
        if target in superseded_by:
            forks.append(f"{target} (by {superseded_by[target]} and {rid})")
            findings.append(_finding(check, CONTRADICTED,
                                     f"{rid} supersedes {target}, already superseded by "
                                     f"{superseded_by[target]} — a fork, not a linear history.",
                                     _self_repro(source, rid)))
            continue
        superseded_by[target] = rid
        findings.append(_finding(check, CONFIRMED,
                                 f"{rid} supersedes {target} (prior entry preserved).",
                                 _self_repro(source, rid)))
    # Cycle detection: follow supersedes pointers; revisiting an id is a cycle (a
    # supersession loop cannot be an append-only history).
    id_to_supersedes = {_rid(r, i): str(r.get("supersedes", "")).strip() for i, r in enumerate(records)}
    reported = False
    for start in id_to_supersedes:
        seen: set[str] = set()
        cur = start
        while cur and cur in id_to_supersedes and not reported:
            if cur in seen:
                findings.append(_finding("supersession:cycle", CONTRADICTED,
                                         f"supersession cycle detected involving {cur}.", _self_repro(source, cur)))
                reported = True
                break
            seen.add(cur)
            cur = id_to_supersedes.get(cur, "")
    return findings


def _check_owner_gate(records: list[dict], source: str, superseded: set[str]) -> list[dict]:
    """Every CURRENT record marked irreversible carries owner authorization."""
    findings: list[dict] = []
    for index, rec in enumerate(records):
        if not _truthy(rec.get("irreversible")):
            continue
        rid = _rid(rec, index)
        if rid in superseded:
            continue
        check = f"owner-gated:{rid}"
        if _truthy(rec.get("owner_authorized")):
            findings.append(_finding(check, CONFIRMED,
                                     f"{rid} is an irreversible act and carries owner authorization "
                                     f"({str(rec.get('owner_authorized'))!r}).", _self_repro(source, rid)))
        else:
            findings.append(_finding(check, CONTRADICTED,
                                     f"{rid} is an irreversible act with no owner authorization — it must be "
                                     f"owner-gated.", _self_repro(source, rid)))
    return findings


def _check_liveness(config: dict, records: list[dict], source: str) -> list[dict]:
    """Single-baton: replay handoffs from initial_holder; every transfer comes from the
    current holder (baton conserved) and exactly one party holds it at the tip, else STALLED."""
    superseded = {str(rec.get("supersedes", "")).strip() for rec in records if str(rec.get("supersedes", "")).strip()}
    handoffs = [
        (i, rec) for i, rec in enumerate(records)
        if str(rec.get("type", "")).strip() == "handoff" and _rid(rec, i) not in superseded
    ]
    holder = str(config.get("initial_holder", "")).strip()
    findings: list[dict] = []
    for index, rec in handoffs:
        rid = _rid(rec, index)
        frm = str(rec.get("from", "")).strip()
        to = str(rec.get("to", "")).strip()
        if not holder:
            findings.append(_finding("liveness", CONTRADICTED,
                                     f"STALLED: {rid} transfers the baton but no party currently holds it "
                                     f"(no initial_holder or the baton was dropped).", _self_repro(source, rid)))
            return findings
        if frm != holder:
            findings.append(_finding("liveness", CONTRADICTED,
                                     f"STALLED: {rid} passes the baton from {frm!r}, but {holder!r} holds it — "
                                     f"a forged or contended transfer, not a single conserved baton.",
                                     _self_repro(source, rid)))
            return findings
        if not to:
            findings.append(_finding("liveness", CONTRADICTED,
                                     f"STALLED: {rid} drops the baton (no recipient); no party holds it.",
                                     _self_repro(source, rid)))
            return findings
        holder = to
    if not holder:
        findings.append(_finding("liveness", CONTRADICTED,
                                 "STALLED: no party holds the baton (declare initial_holder or a handoff).",
                                 _self_repro(source, "liveness")))
    else:
        findings.append(_finding("liveness", CONFIRMED,
                                 f"LIVE: exactly one party holds the baton — {holder!r} — after "
                                 f"{len(handoffs)} conserved handoff(s).", _self_repro(source, "liveness")))
    return findings


def _resolve_verdict(findings: list[dict]) -> str:
    states = {f["state"] for f in findings}
    if CONTRADICTED in states:
        return CONTRADICTED
    if NOT_RUN in states or not findings:
        return NOT_RUN
    return CONFIRMED


def verify_protocol(config: dict, *, repo: str = "", check_liveness: bool = False,
                    source: str = "") -> dict:
    """Verify a declared protocol's records against the six invariants.

    ``config`` keys: records[] (each: id, party, type, pins_head, receipt{reviewed_head,
    review_id}, supersedes, from, to, irreversible, owner_authorized), initial_holder,
    [repo]. Verdict precedence matches the binders: any CONTRADICTED wins, else any
    NOT_RUN (or no records) is NOT_RUN, else CONFIRMED.
    """
    repo = str(repo or config.get("repo", "") or "").strip()
    raw = config.get("records")
    records = [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []

    def result(verdict: str, findings: list[dict]) -> dict:
        return {
            "target": repo or "protocol",
            "verdict": verdict,
            "record_count": len(records),
            "liveness_checked": bool(check_liveness),
            "head_currency_checked": bool(repo),
            "truth_boundary": PROTOCOL_VERIFY_TRUTH_BOUNDARY,
            "findings": findings,
        }

    if not records:
        return result(NOT_RUN, [_finding("records", NOT_RUN,
                                         "protocol config declares no structured records to verify.",
                                         _self_repro(source, "records"))])

    superseded = _superseded_ids(records)
    findings: list[dict] = []
    findings += _check_structured_state(records, source)
    findings += _check_exact_head(records, repo, source, superseded)
    findings += _check_receipts(records, source, superseded)
    findings += _check_supersession(records, source)
    findings += _check_owner_gate(records, source, superseded)
    if check_liveness:
        findings += _check_liveness(config, records, source)
    return result(_resolve_verdict(findings), findings)
