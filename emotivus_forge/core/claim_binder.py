"""Generalized structured-claim binder (G1 truth core; R3).

`forge bind` began with three hard-wired claim shapes (release-truth,
gate-coverage, gate-diff). The multi-agent protocol work needs the general
primitive underneath them: **a structured claim, deterministically evaluated
against git ground truth, yielding a verdict that carries its own reproduce
command** — so "every claim pins an exact head; every accept carries a bindable
receipt" is checkable by machine rather than by prose.

Claim types (each drawn from a real LineCheck receipt shape):
  head-equals    — ref R currently resolves to SHA X (the "claim pins an exact
                   head" primitive; remote-name freshness enforced by the guard)
  ancestry       — commit A is an ancestor of commit B (merge-base --is-ancestor)
  blob-identity  — path P at ref X is byte-identical to P at ref Y, or to a
                   given blob SHA (the "verbatim received source unchanged" check)
  file-sha256    — file bytes at an exact head hash to a stated value
  file-regex     — file at an exact head matches a pattern / captures a value

Every referenced ref passes the shared head-integrity guard first (R8): a
missing, superseded, or stale anchor yields NOT_RUN — never a content verdict,
so never a false CONTRADICTED authored by staleness. Results are shaped like
the other binders' so ``record_binder_result`` can feed the truth ledger, where
CONFIRMED arrives binder-derived and NOT_RUN lands as terminal UNVERIFIABLE.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from typing import Any

from .ref_integrity import guard_finding
from .truth import TRUTH_STATES

CONFIRMED = "CONFIRMED"
CONTRADICTED = "CONTRADICTED"
NOT_RUN = "NOT_RUN"
assert {CONFIRMED, CONTRADICTED, NOT_RUN} <= set(TRUTH_STATES)

CLAIM_TYPES = ("head-equals", "ancestry", "blob-identity", "file-sha256", "file-regex")

CLAIM_BINDER_TRUTH_BOUNDARY = (
    "Forge evaluates each structured claim against git ground truth at guarded anchors and "
    "reports a per-claim verdict with a reproduce command. A confirmation means the stated "
    "relation held at check time in this repository; it does not prove the claim's broader "
    "intent, authenticate its author, or survive a later force-push. An anchor whose currency "
    "cannot be established yields NOT_RUN, never a content verdict."
)


def _git(repo: str, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=timeout)


def _finding(check: str, state: str, detail: str, reproduce: str = "") -> dict:
    return {"check": check, "state": state, "detail": detail, "reproduce": reproduce}


def _require(claim: dict, keys: tuple[str, ...]) -> list[str]:
    return [k for k in keys if not str(claim.get(k, "")).strip()]


def _oid_matches(actual: str, expected: str) -> bool:
    """Exact, or a valid hex prefix (>=7 chars, git's short-oid convention) of ``actual``.

    ``actual`` is always a fully-resolved, unique git object id / content hash, so a hex
    prefix of it cannot collide with a different object — accepting an abbreviated claimed
    id (git's own normal form) cannot introduce a false CONFIRMED, only avoid a false
    CONTRADICTED when a true claim is stated in short form.
    """
    a, e = actual.strip().lower(), expected.strip().lower()
    if not e:
        return False
    if a == e:
        return True
    return 7 <= len(e) < len(a) and all(c in "0123456789abcdef" for c in e) and a.startswith(e)


def _guard_refs(repo: str, claim: dict, claim_id: str, refs: tuple[str, ...],
                allow_superseded: bool) -> dict | None:
    """Guard every anchor a claim references; a refusal is the claim's finding.

    An empty optional ref (e.g. blob-identity's other_ref when a literal blob_sha is used
    instead) is skipped, not treated as MISSING — the evaluator handles the absent case.
    """
    for key in refs:
        ref = str(claim.get(key, "")).strip()
        if not ref:
            continue
        blocking, _ = guard_finding(repo, ref, label=f"{claim_id}:{key}",
                                    allow_superseded=allow_superseded)
        if blocking is not None:
            return blocking
    return None


def _eval_head_equals(repo: str, claim: dict, claim_id: str) -> dict:
    ref, expected = str(claim["ref"]).strip(), str(claim["sha"]).strip().lower()
    proc = _git(repo, ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"])
    actual = proc.stdout.strip().lower()
    repro = f"git -C {repo} rev-parse {ref}"
    if proc.returncode != 0 or not actual:
        return _finding(claim_id, NOT_RUN, f"{ref} does not resolve.", repro)
    if _oid_matches(actual, expected):
        return _finding(claim_id, CONFIRMED, f"{ref} resolves to {expected} as claimed.", repro)
    return _finding(claim_id, CONTRADICTED,
                    f"{ref} resolves to {actual[:12]}, not the claimed {expected[:12]}.", repro)


def _eval_ancestry(repo: str, claim: dict, claim_id: str) -> dict:
    ancestor, descendant = str(claim["ancestor"]).strip(), str(claim["descendant"]).strip()
    proc = _git(repo, ["merge-base", "--is-ancestor", ancestor, descendant])
    repro = f"git -C {repo} merge-base --is-ancestor {ancestor} {descendant}"
    if proc.returncode == 0:
        return _finding(claim_id, CONFIRMED, f"{ancestor[:12]} is an ancestor of {descendant[:12]}.", repro)
    if proc.returncode == 1:
        return _finding(claim_id, CONTRADICTED,
                        f"{ancestor[:12]} is NOT an ancestor of {descendant[:12]} — the descendant does "
                        f"not build on the claimed base (rebase or unrelated history).", repro)
    return _finding(claim_id, NOT_RUN, proc.stderr.strip() or "merge-base failed.", repro)


def _blob_sha(repo: str, ref: str, path: str) -> str | None:
    proc = _git(repo, ["rev-parse", "--verify", "--quiet", f"{ref}:{path}"])
    value = proc.stdout.strip()
    return value if proc.returncode == 0 and value else None


def _eval_blob_identity(repo: str, claim: dict, claim_id: str) -> dict:
    ref, path = str(claim["ref"]).strip(), str(claim["path"]).strip()
    actual = _blob_sha(repo, ref, path)
    if actual is None:
        return _finding(claim_id, NOT_RUN, f"{path} absent at {ref}.",
                        f"git -C {repo} rev-parse {ref}:{path}")
    other_ref = str(claim.get("other_ref", "")).strip()
    if other_ref:
        other_path = str(claim.get("other_path", "")).strip() or path
        expected = _blob_sha(repo, other_ref, other_path)
        repro = f"git -C {repo} rev-parse {ref}:{path} {other_ref}:{other_path}"
        if expected is None:
            return _finding(claim_id, NOT_RUN, f"{other_path} absent at {other_ref}.", repro)
        expectation = f"{other_ref}:{other_path}"
    else:
        expected = str(claim.get("blob_sha", "")).strip()
        repro = f"git -C {repo} rev-parse {ref}:{path}"
        expectation = f"blob {expected[:12]}"
        if not expected:
            # Neither a comparison ref nor a literal blob was supplied: unassessable, so
            # NOT_RUN — never a content verdict (a false CONTRADICTED) against an empty target.
            return _finding(claim_id, NOT_RUN,
                            f"blob-identity for {path} at {ref} supplies neither other_ref nor blob_sha; "
                            f"nothing to compare.", repro)
    if _oid_matches(actual, expected):
        return _finding(claim_id, CONFIRMED,
                        f"{path} at {ref} is byte-identical to {expectation} (blob {actual[:12]}).", repro)
    return _finding(claim_id, CONTRADICTED,
                    f"{path} at {ref} is blob {actual[:12]}, not {expectation} — the bytes differ.", repro)


def _file_at(repo: str, ref: str, path: str) -> bytes | None:
    proc = subprocess.run(["git", "-C", repo, "show", f"{ref}:{path}"], capture_output=True, timeout=30)
    return proc.stdout if proc.returncode == 0 else None


def _eval_file_sha256(repo: str, claim: dict, claim_id: str) -> dict:
    ref, path = str(claim["ref"]).strip(), str(claim["path"]).strip()
    expected = str(claim["sha256"]).strip().lower()
    blob = _file_at(repo, ref, path)
    repro = f"git -C {repo} show {ref}:{path} | sha256sum"
    if blob is None:
        return _finding(claim_id, NOT_RUN, f"{path} absent at {ref}.", repro)
    actual = hashlib.sha256(blob).hexdigest()
    if _oid_matches(actual, expected):
        return _finding(claim_id, CONFIRMED, f"{path} at {ref} hashes to the claimed {expected[:12]}….", repro)
    return _finding(claim_id, CONTRADICTED,
                    f"{path} at {ref} hashes to {actual[:12]}…, not the claimed {expected[:12]}….", repro)


def _eval_file_regex(repo: str, claim: dict, claim_id: str) -> dict:
    ref, path = str(claim["ref"]).strip(), str(claim["path"]).strip()
    pattern = str(claim["regex"])
    blob = _file_at(repo, ref, path)
    repro = f"git -C {repo} show {ref}:{path} | grep -E {pattern!r}"
    if blob is None:
        return _finding(claim_id, NOT_RUN, f"{path} absent at {ref}.", repro)
    try:
        match = re.search(pattern, blob.decode("utf-8", errors="replace"))
    except re.error as exc:
        return _finding(claim_id, NOT_RUN, f"invalid regex: {exc}", repro)
    expected = str(claim.get("expect", "")).strip()
    if match is None:
        return _finding(claim_id, CONTRADICTED, f"{path} at {ref} does not match /{pattern}/.", repro)
    if expected:
        captured = match.group(1) if match.groups() else match.group(0)
        if captured is None:  # an optional first group did not participate; fall back
            captured = match.group(0)
        if captured != expected:
            return _finding(claim_id, CONTRADICTED,
                            f"{path} at {ref} matches /{pattern}/ but captures {captured!r}, "
                            f"not the claimed {expected!r}.", repro)
        return _finding(claim_id, CONFIRMED,
                        f"{path} at {ref} matches /{pattern}/ and captures the claimed {expected!r}.", repro)
    return _finding(claim_id, CONFIRMED, f"{path} at {ref} matches /{pattern}/.", repro)


# type -> (required keys, refs to guard, evaluator)
_EVALUATORS: dict[str, tuple[tuple[str, ...], tuple[str, ...], Any]] = {
    # head-equals: the *ref* is what the claim is about, so the guard must not
    # pre-resolve failures into refusals of the comparison itself — but a stale
    # remote-tracking snapshot would make the comparison a lie, so the ref is
    # still guarded. The claimed sha is data, not an anchor.
    "head-equals": (("ref", "sha"), ("ref",), _eval_head_equals),
    "ancestry": (("ancestor", "descendant"), ("ancestor", "descendant"), _eval_ancestry),
    "blob-identity": (("ref", "path"), ("ref", "other_ref"), _eval_blob_identity),
    "file-sha256": (("ref", "path", "sha256"), ("ref",), _eval_file_sha256),
    "file-regex": (("ref", "path", "regex"), ("ref",), _eval_file_regex),
}


def _resolve_verdict(findings: list[dict]) -> str:
    states = {f["state"] for f in findings}
    if CONTRADICTED in states:
        return CONTRADICTED
    if NOT_RUN in states:
        return NOT_RUN
    return CONFIRMED


def bind_claims(repo: str, config: dict) -> dict:
    """Evaluate every structured claim in ``config["claims"]`` at guarded anchors.

    Verdict precedence matches the other binders: any CONTRADICTED wins, else any
    NOT_RUN, else CONFIRMED. An empty or malformed claim list is NOT_RUN — an
    absent claim set is not a confirmed one.
    """
    findings: list[dict] = []
    allow_superseded = bool(config.get("allow_superseded_head", False))

    def result(verdict: str) -> dict:
        return {
            "target": repo,
            "verdict": verdict,
            "truth_boundary": CLAIM_BINDER_TRUTH_BOUNDARY,
            "claim_count": len(config.get("claims", []) or []),
            "findings": findings,
        }

    claims = config.get("claims")
    if not isinstance(claims, list) or not claims:
        findings.append(_finding("claims", NOT_RUN, "config contains no claims to bind."))
        return result(NOT_RUN)

    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            findings.append(_finding(f"claim[{index}]", NOT_RUN, "claim is not an object."))
            continue
        claim_id = str(claim.get("id", "")).strip() or f"claim[{index}]"
        ctype = str(claim.get("type", "")).strip()
        entry = _EVALUATORS.get(ctype)
        if entry is None:
            findings.append(_finding(claim_id, NOT_RUN,
                                     f"unknown claim type {ctype!r}; expected one of {list(CLAIM_TYPES)}."))
            continue
        required, guarded_refs, evaluator = entry
        missing = _require(claim, required)
        if missing:
            findings.append(_finding(claim_id, NOT_RUN,
                                     f"claim is missing required field(s): {', '.join(missing)}."))
            continue
        blocking = _guard_refs(repo, claim, claim_id, guarded_refs, allow_superseded)
        if blocking is not None:
            findings.append(blocking)
            continue
        findings.append(evaluator(repo, claim, claim_id))

    return result(_resolve_verdict(findings))
