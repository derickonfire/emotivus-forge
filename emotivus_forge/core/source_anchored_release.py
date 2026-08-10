"""Source-anchored release verification (G1 truth core).

The gap this closes was proven in the LineCheck engagement: a release was marked
*accepted* at a schema its accepted source never shipped, with the accepted and
public surfaces rewritten to the candidate schema. Every internal-consistency
gate stayed green because RELEASE-STATE and the documents agreed with each other
— "internal agreement is not exact-source acceptance." ``release_facts`` compares
*project-declared* fields to each other; it cannot catch a declaration that has
been moved ahead of the code the accepted release actually shipped.

This module supplies the missing anchor. The accepted release's true schema is
derived from the exact **accepted source commit's** code, and the declared
release-state plus accepted/public surfaces are bound to that source-derived
truth at an exact head. It is deterministic, read-only, and advisory.

Core invariant honoured: an unreachable object or missing anchor yields
``NOT_RUN`` — never silently upgraded to a confirmation.
"""
from __future__ import annotations

import json
import re
import subprocess
from typing import Any

from .ref_integrity import SUPERSEDED, guard_finding
from .truth import TRUTH_STATES

# Finding / verdict states, drawn from the core truth vocabulary.
CONFIRMED = "CONFIRMED"
CONTRADICTED = "CONTRADICTED"
NOT_RUN = "NOT_RUN"
assert {CONFIRMED, CONTRADICTED, NOT_RUN} <= set(TRUTH_STATES)

SOURCE_ANCHORED_TRUTH_BOUNDARY = (
    "Forge derives the accepted release's true schema from the exact accepted source "
    "commit's code and binds the project-declared release-state and accepted/public "
    "surfaces to it at an exact head. Forge does not review application logic, prove "
    "substantive correctness, or authenticate the declaring authority. A confirmation "
    "means exact-source consistency at this tree, not that the release is otherwise complete."
)


class GitError(RuntimeError):
    """A git read failed in a way the caller should surface rather than swallow."""


def _git(repo: str, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def _object_type(repo: str, ref: str) -> str | None:
    proc = _git(repo, ["cat-file", "-t", ref])
    return proc.stdout.strip() if proc.returncode == 0 else None


def _is_commit(repo: str, ref: str) -> bool:
    return _object_type(repo, ref) == "commit"


def _file_at(repo: str, ref: str, path: str) -> str | None:
    proc = _git(repo, ["show", f"{ref}:{path}"])
    return proc.stdout if proc.returncode == 0 else None


def _changed_paths(repo: str, base: str, head: str, paths: list[str]) -> list[str]:
    proc = _git(repo, ["diff", "--name-only", f"{base}..{head}", "--", *paths])
    if proc.returncode != 0:
        raise GitError(proc.stderr.strip() or f"git diff {base}..{head} failed")
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _pointer(doc: Any, pointer: str) -> tuple[bool, Any]:
    """Minimal RFC-6901 JSON Pointer resolve. Returns (found, value)."""
    if pointer in ("", "/"):
        return True, doc
    cur = doc
    for raw in pointer.lstrip("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict) and token in cur:
            cur = cur[token]
        elif isinstance(cur, list) and token.isdigit() and int(token) < len(cur):
            cur = cur[int(token)]
        else:
            return False, None
    return True, cur


def _finding(check: str, state: str, detail: str, reproduce: str = "") -> dict:
    return {"check": check, "state": state, "detail": detail, "reproduce": reproduce}


def _resolve(findings: list[dict]) -> str:
    """Verdict precedence: a real contradiction wins; absence never becomes a confirmation."""
    states = {f["state"] for f in findings}
    if CONTRADICTED in states:
        return CONTRADICTED
    if NOT_RUN in states:
        return NOT_RUN
    return CONFIRMED


def bind_source_anchored_release(repo: str, head: str, config: dict) -> dict:
    """Bind the accepted-vs-candidate release truth at ``head`` against the accepted source.

    ``config`` keys:
      release_state_file, accepted_schema_pointer, accepted_source_pointer,
      schema_source={file, regex}, candidate_schema_pointer, candidate_status_pointer,
      candidate_not_accepted_statuses[], candidate_acceptance_evidence_pointer,
      accepted_surfaces[], schema_claim_regex, [baseline_invariance={certified_head, paths[]}]
    """
    findings: list[dict] = []

    def result() -> dict:
        return {
            "target": repo,
            "head": head,
            "verdict": _resolve(findings),
            "truth_boundary": SOURCE_ANCHORED_TRUTH_BOUNDARY,
            "findings": findings,
        }

    # --- Head-integrity gate (R8): never bind to a missing, superseded, or stale anchor.
    # A rebased/force-pushed-away head still exists in the object store; a stale
    # remote-tracking name resolves silently to old truth. Either could author a
    # false CONTRADICTED for the claim, so the guard refuses with NOT_RUN instead.
    blocking, assessment = guard_finding(
        repo, head, label="head",
        allow_superseded=bool(config.get("allow_superseded_head", False)))
    if blocking is not None:
        findings.append(blocking)
        return result()
    if assessment["status"] == SUPERSEDED:
        # Deliberately historical bind: record the waived currency so the result
        # cannot masquerade as current truth.
        findings.append(_finding("head-integrity", CONFIRMED,
                                 f"head currency waived by allow_superseded_head: {assessment['detail']}",
                                 assessment["reproduce"]))

    rs_file = config["release_state_file"]
    rs_text = _file_at(repo, head, rs_file)
    if rs_text is None:
        findings.append(_finding("release-state-present", NOT_RUN, f"{rs_file} absent at {head}.",
                                 f"git -C {repo} show {head}:{rs_file}"))
        return result()
    try:
        rs = json.loads(rs_text)
    except json.JSONDecodeError as exc:
        findings.append(_finding("release-state-parse", CONTRADICTED, f"{rs_file} is not valid JSON: {exc}"))
        return result()

    # --- Derive the TRUE accepted schema from the accepted source commit ---
    ok_src, accepted_source = _pointer(rs, config["accepted_source_pointer"])
    accepted_source = str(accepted_source) if ok_src and accepted_source else ""
    if not accepted_source:
        findings.append(_finding("accepted-source-present", NOT_RUN,
                                 f"no accepted source at {config['accepted_source_pointer']}."))
        return result()
    if not _is_commit(repo, accepted_source):
        findings.append(_finding("accepted-source-reachable", NOT_RUN,
                                 f"accepted source {accepted_source} unreachable; cannot derive true schema.",
                                 f"git -C {repo} cat-file -t {accepted_source}"))
        return result()

    src_file = config["schema_source"]["file"]
    src_text = _file_at(repo, accepted_source, src_file)
    m = re.search(config["schema_source"]["regex"], src_text) if src_text is not None else None
    if not m:
        findings.append(_finding("true-accepted-schema", NOT_RUN,
                                 f"schema literal not found in {src_file} at accepted source {accepted_source[:12]}.",
                                 f"git -C {repo} show {accepted_source[:12]}:{src_file}"))
        return result()
    true_schema = m.group(1)
    findings.append(_finding("true-accepted-schema", CONFIRMED,
                             f"accepted schema {true_schema}, derived from accepted source "
                             f"{accepted_source[:12]} ({src_file}).",
                             f"git -C {repo} show {accepted_source[:12]}:{src_file}"))

    # --- Check 1: RELEASE-STATE top schema matches the source-derived truth ---
    ok_top, top_schema = _pointer(rs, config["accepted_schema_pointer"])
    top_schema = str(top_schema)
    if not ok_top:
        findings.append(_finding("release-state-top-schema", CONTRADICTED,
                                 f"no schema at {config['accepted_schema_pointer']}."))
    elif top_schema != true_schema:
        findings.append(_finding(
            "release-state-top-schema", CONTRADICTED,
            f"RELEASE-STATE declares accepted schema {top_schema}, but accepted source "
            f"{accepted_source[:12]} shipped {true_schema}. Internal agreement is not exact-source acceptance.",
            f"git -C {repo} show {head}:{rs_file}"))
    else:
        findings.append(_finding("release-state-top-schema", CONFIRMED,
                                 f"RELEASE-STATE accepted schema {top_schema} == source-derived {true_schema}."))

    # --- Check 2: candidate labelled not-accepted with null acceptance evidence ---
    ok_cs, cand_schema = _pointer(rs, config["candidate_schema_pointer"])
    cand_schema = str(cand_schema) if ok_cs else None
    if ok_cs:
        _, cand_status = _pointer(rs, config["candidate_status_pointer"])
        ok_ev, cand_evidence = _pointer(rs, config["candidate_acceptance_evidence_pointer"])
        not_accepted = set(config.get("candidate_not_accepted_statuses", []))
        problems = []
        if cand_status not in not_accepted:
            problems.append(f"status {cand_status!r} is not one of {sorted(not_accepted)}")
        if not (ok_ev and cand_evidence is None):
            problems.append(f"acceptance_evidence is {cand_evidence!r}, expected null")
        if problems:
            findings.append(_finding("candidate-labelled-not-accepted", CONTRADICTED,
                                     f"candidate schema {cand_schema} is mislabelled: " + "; ".join(problems),
                                     f"git -C {repo} show {head}:{rs_file}"))
        else:
            findings.append(_finding("candidate-labelled-not-accepted", CONFIRMED,
                                     f"candidate schema {cand_schema}: status {cand_status!r}, acceptance_evidence null."))

    # --- Check 3: accepted/public surfaces must state the true accepted schema ---
    # mode "candidate" (default, backward-compatible): flag only a claim equal to the
    #   candidate value — precise, low false-positive.
    # mode "strict": flag ANY schema-claim that is neither the true accepted schema nor
    #   a configured historical value — catches a wrong or candidate value even when no
    #   current_candidate block is present (the exact gap the LineCheck 872289b head showed).
    claim_re = re.compile(config["schema_claim_regex"], re.IGNORECASE)
    named = "n" in claim_re.groupindex
    mode = config.get("surface_schema_mode", "candidate")
    allowlist = {str(x) for x in config.get("historical_schema_allowlist", [])}

    def _digit(match: "re.Match") -> str | None:
        if named:
            return match.group("n")
        groups = [g for g in match.groups() if g]
        return groups[-1] if groups else None

    surfaces = config.get("accepted_surfaces", [])
    leaks: list[str] = []
    stated_true = 0
    for surf in surfaces:
        text = _file_at(repo, head, surf)
        if text is None:
            continue
        for match in claim_re.finditer(text):
            num = _digit(match)
            if num is None:
                continue
            line_no = text.count("\n", 0, match.start()) + 1
            if num == true_schema:
                stated_true += 1
                continue
            if num in allowlist:
                continue
            if mode == "strict":
                tag = " (candidate)" if num == cand_schema else ""
                leaks.append(f"{surf}:{line_no} claims schema {num}{tag}, not the accepted {true_schema}")
            elif cand_schema is not None and num == cand_schema:
                leaks.append(f"{surf}:{line_no} claims schema {num} (candidate) for the accepted release")
    nums = "|".join(sorted({n for n in (true_schema, cand_schema) if n}))
    grep = f"git -C {repo} grep -niE 'schema[^0-9]*({nums})' {head} -- " + " ".join(surfaces)
    if leaks:
        findings.append(_finding("accepted-surface-states-true-schema", CONTRADICTED,
                                 f"accepted/public surfaces state a schema other than the accepted {true_schema}: "
                                 + "; ".join(leaks), grep))
    else:
        findings.append(_finding("accepted-surface-states-true-schema", CONFIRMED,
                                 f"every accepted/public surface schema-claim is the accepted {true_schema} "
                                 f"({stated_true} mention(s)); mode={mode}.", grep))

    # --- Optional Check 4: byte-identical release-truth invariance vs a certified head ---
    baseline = config.get("baseline_invariance")
    if baseline:
        cert, paths = baseline["certified_head"], baseline["paths"]
        if not _is_commit(repo, cert):
            findings.append(_finding("baseline-invariance", NOT_RUN, f"certified baseline {cert} unreachable.",
                                     f"git -C {repo} cat-file -t {cert}"))
        else:
            changed = _changed_paths(repo, cert, head, paths)
            repro = f"git -C {repo} diff --stat {cert}..{head} -- " + " ".join(paths)
            if changed:
                findings.append(_finding("baseline-invariance", CONTRADICTED,
                                         f"release-truth paths diverged from certified {cert[:12]}: " + ", ".join(changed), repro))
            else:
                findings.append(_finding("baseline-invariance", CONFIRMED,
                                         f"release-truth paths byte-identical to certified {cert[:12]}.", repro))

    return result()
