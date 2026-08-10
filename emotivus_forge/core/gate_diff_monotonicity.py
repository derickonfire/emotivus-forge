"""Gate-diff monotonicity (G1 project-truth).

The gap this closes was proven twice in the LineCheck engagement: a change edited
the project's own gate/check scripts (a schema-pin bump across ~12 checks; a
proposed CI probe-hardening), and the only thing between "legitimate maintenance"
and "silently weakened gate" was a human reading the diff. A green gate after a
gate-script edit proves nothing about whether the edit weakened the gate.

This instrument binds, over a diff scoped to declared gate/check paths, that the
change is **monotonic**: the assertion count did not decrease and no new SKIP path
was introduced. It is deterministic, read-only, and advisory.

Boundary: it certifies assertion-count non-decrease and no-new-SKIP by counting
marker occurrences at both trees. It does NOT detect a threshold lowered *inside*
a retained assertion, nor prove the assertions are meaningful — that is the
reviewer's domain. An unreachable ref yields NOT_RUN, never a confirmation.
"""
from __future__ import annotations

import fnmatch
import subprocess

from .truth import TRUTH_STATES

CONFIRMED = "CONFIRMED"
CONTRADICTED = "CONTRADICTED"
NOT_RUN = "NOT_RUN"
assert {CONFIRMED, CONTRADICTED, NOT_RUN} <= set(TRUTH_STATES)

DEFAULT_ASSERTION_MARKERS = ["$ok(", "ok(", "is_eq(", "assertEqual", "assertTrue", "assertFalse", "expect("]
DEFAULT_SKIP_MARKERS = ["SKIP", "skip(", "markTestSkipped", "->skip", "skipTest", "assertSkip"]

GATE_DIFF_MONOTONICITY_TRUTH_BOUNDARY = (
    "Forge binds, over a diff scoped to declared gate/check paths, that the assertion count "
    "did not decrease and no new SKIP path was introduced, by counting marker occurrences at "
    "both trees. Forge does not detect a numeric threshold lowered inside a retained assertion, "
    "does not judge whether the assertions are meaningful, and is only as complete as the "
    "declared gate_paths and marker lists. An unreachable ref yields NOT_RUN."
)


class GitError(RuntimeError):
    pass


def _git(repo: str, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def _is_commit(repo: str, ref: str) -> bool:
    proc = _git(repo, ["cat-file", "-t", ref])
    return proc.returncode == 0 and proc.stdout.strip() == "commit"


def _show(repo: str, ref: str, path: str) -> str | None:
    proc = _git(repo, ["show", f"{ref}:{path}"])
    return proc.stdout if proc.returncode == 0 else None


def _changed_files(repo: str, base: str, head: str) -> list[str]:
    proc = _git(repo, ["diff", "--name-only", f"{base}", f"{head}"])
    if proc.returncode != 0:
        raise GitError(proc.stderr.strip() or f"git diff {base} {head} failed")
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _count_markers(text: str, markers: list[str]) -> int:
    return sum(text.count(m) for m in markers)


def _match_any(path: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in globs)


def _finding(check: str, state: str, detail: str, reproduce: str = "") -> dict:
    return {"check": check, "state": state, "detail": detail, "reproduce": reproduce}


def report_gate_diff_monotonicity(repo: str, base: str, head: str, config: dict) -> dict:
    """Certify a base..head diff over gate/check paths removed no assertion and added no SKIP.

    config keys:
      gate_paths[]           — globs for gate/check scripts to scope the diff
      [assertion_markers[]]  — substrings identifying an assertion (defaults provided)
      [skip_markers[]]       — substrings identifying a SKIP path (defaults provided)
    """
    findings: list[dict] = []

    def result(verdict: str) -> dict:
        return {
            "target": repo,
            "base": base,
            "head": head,
            "verdict": verdict,
            "truth_boundary": GATE_DIFF_MONOTONICITY_TRUTH_BOUNDARY,
            "findings": findings,
        }

    for ref, label in ((base, "base"), (head, "head")):
        if not _is_commit(repo, ref):
            findings.append(_finding("reachability", NOT_RUN,
                                     f"{label} {ref} is not a reachable commit in {repo}.",
                                     f"git -C {repo} cat-file -t {ref}"))
            return result(NOT_RUN)

    gate_paths = config["gate_paths"]
    assertion_markers = config.get("assertion_markers", DEFAULT_ASSERTION_MARKERS)
    skip_markers = config.get("skip_markers", DEFAULT_SKIP_MARKERS)

    try:
        changed = [p for p in _changed_files(repo, base, head) if _match_any(p, gate_paths)]
    except GitError as exc:
        findings.append(_finding("diff", NOT_RUN, str(exc)))
        return result(NOT_RUN)

    if not changed:
        findings.append(_finding("scope", CONFIRMED,
                                 f"no gate/check files matching {gate_paths} changed in {base[:12]}..{head[:12]}; "
                                 f"nothing to weaken."))
        return result(CONFIRMED)

    # Monotonicity is about not weakening what is already there. Classify each changed
    # file as modified (in both trees), deleted, or added. A modified file that loses
    # assertions or gains a SKIP is a weakening; a deleted check removes coverage; an
    # ADDED check is additive — its own skip-guards are not a weakening of existing gates.
    weakened_assertions: list[str] = []   # modified files that lost assertions, or deleted checks
    new_skip_files: list[str] = []        # modified files that gained a SKIP path
    added_assertions = 0
    modified_count = 0
    for f in changed:
        base_text = _show(repo, base, f)
        head_text = _show(repo, head, f)
        if base_text is not None and head_text is not None:  # modified
            modified_count += 1
            a_delta = _count_markers(head_text, assertion_markers) - _count_markers(base_text, assertion_markers)
            s_delta = _count_markers(head_text, skip_markers) - _count_markers(base_text, skip_markers)
            if a_delta < 0:
                weakened_assertions.append(f"{f} (assertions {a_delta})")
            if s_delta > 0:
                new_skip_files.append(f"{f} (+{s_delta} SKIP)")
        elif base_text is not None and head_text is None:  # deleted check
            removed = _count_markers(base_text, assertion_markers)
            if removed > 0:
                weakened_assertions.append(f"{f} (deleted; -{removed} assertions)")
        elif head_text is not None:  # added check — additive
            added_assertions += _count_markers(head_text, assertion_markers)

    repro = f"git -C {repo} diff {base[:12]}..{head[:12]} -- " + " ".join(changed)

    if weakened_assertions:
        findings.append(_finding("assertion-preservation", CONTRADICTED,
                                 "assertions removed from existing gate files or a check deleted: "
                                 + "; ".join(weakened_assertions), repro))
    else:
        findings.append(_finding("assertion-preservation", CONFIRMED,
                                 f"no existing gate file lost assertions across {modified_count} modified "
                                 f"file(s); +{added_assertions} assertion(s) in added checks."))

    if new_skip_files:
        findings.append(_finding("no-new-skip", CONTRADICTED,
                                 "a new SKIP path was introduced into existing gate file(s): "
                                 + "; ".join(new_skip_files), repro))
    else:
        findings.append(_finding("no-new-skip", CONFIRMED,
                                 "no existing gate file gained a SKIP path (skip-guards inside newly added "
                                 "checks are additive, not a weakening)."))

    verdict = CONTRADICTED if (weakened_assertions or new_skip_files) else CONFIRMED
    return result(verdict)
