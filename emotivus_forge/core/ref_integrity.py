"""Head-integrity guard shared by every G1 binder (R8: stale-ref / force-fetch).

The gap this closes was proven in the LineCheck engagement (see
planning/OBSERVED-MISS-stale-ref-false-contradiction.md): a claim about a PR was
evaluated at a stale local ref and nearly issued a false CONTRADICTED; only a
force-fetch surfaced the corrected truth. The binder track gated on object
*existence* (`git cat-file -t`), which is necessary but not sufficient:

- a rebased/force-pushed-away head still exists in the object store until gc,
  so an existence gate happily binds "current" claims to a superseded commit;
- a remote-tracking name (`origin/feature`) resolves silently to whatever the
  last fetch saw, with no record that freshness was never established.

``assess_head`` classifies an anchor ref BEFORE any binder logic runs. The core
invariant extends naturally: never upgrade NOT_RUN to PASS becomes never bind a
claim to an anchor whose currency is unverified. A guard refusal maps to the
binder's NOT_RUN (and, through the truth ledger, to terminal UNVERIFIABLE) —
never to a content verdict, so never to a false CONTRADICTED.

Boundary: freshness is a point-in-time read; a force-push racing the check wins.
Re-binding is cheap and deterministic — the remedy is re-run, not trust.
"""
from __future__ import annotations

import subprocess

# Anchor statuses.
FRESH = "FRESH"                        # safe to bind: reachable object id, or local name
MISSING = "MISSING"                    # ref does not resolve at all
NOT_A_COMMIT = "NOT_A_COMMIT"          # resolves, but not to a commit object
SUPERSEDED = "SUPERSEDED"              # object id exists but no current local ref reaches it
STALE_REMOTE_REF = "STALE_REMOTE_REF"  # remote-tracking name lags/diverges from the remote
REMOTE_UNVERIFIED = "REMOTE_UNVERIFIED"  # remote-tracking name; remote not contactable

REF_INTEGRITY_TRUTH_BOUNDARY = (
    "The head-integrity guard classifies a binder anchor before binding: an exact SHA must "
    "still be reachable from a current ref, and a remote-tracking name must match what the "
    "remote reports now. It proves anchor currency at check time, not claim correctness; a "
    "force-push racing the check wins, and the remedy is to re-run the bind."
)


def _git(repo: str, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=timeout)


def _object_type(repo: str, ref: str) -> str | None:
    proc = _git(repo, ["cat-file", "-t", ref])
    return proc.stdout.strip() if proc.returncode == 0 else None


def _resolve(repo: str, ref: str) -> str | None:
    proc = _git(repo, ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"])
    value = proc.stdout.strip()
    return value if proc.returncode == 0 and value else None


def _symbolic_full_name(repo: str, ref: str) -> str:
    """The ref's symbolic full name (refs/heads/…, refs/remotes/…), or "" for a raw
    object id. This — not the id's character length — is how an anchor is classified: an
    abbreviated or uppercase commit id has no symbolic name and must still run the
    reachability (SUPERSEDED) check, while a branch or remote-tracking NAME does not."""
    proc = _git(repo, ["rev-parse", "--symbolic-full-name", ref])
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _is_reachable_from_local_ref(repo: str, sha: str) -> bool:
    """True when a current LOCAL ref (branch or tag) or HEAD reaches ``sha``.

    Remote-tracking refs are deliberately EXCLUDED: they are unverified local snapshots of
    remote state (verified separately via ls-remote), so a commit kept alive only by a
    possibly-stale remote-tracking ref must not be laundered into FRESH. Reachable solely
    that way falls to SUPERSEDED — a NOT_RUN refusal, which is the safe direction.
    """
    proc = _git(repo, ["for-each-ref", f"--contains={sha}", "--count=1",
                       "--format=%(refname)", "refs/heads", "refs/tags"])
    if proc.returncode == 0 and proc.stdout.strip():
        return True
    # for-each-ref does not consider a detached HEAD; check it separately.
    head = _git(repo, ["merge-base", "--is-ancestor", sha, "HEAD"])
    return head.returncode == 0


def _remote_head(repo: str, remote: str, branch: str, timeout: int) -> str | None:
    """What the remote reports for ``branch`` right now; None when unreachable/absent."""
    try:
        proc = _git(repo, ["ls-remote", "--heads", remote, branch], timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[1].strip() == f"refs/heads/{branch}":
            return parts[0].strip()
    return None


def assess_head(repo: str, ref: str, *, remote_timeout: int = 30) -> dict:
    """Classify a binder anchor. Returns {ref, resolved, status, anchor_kind, detail, reproduce}.
    anchor_kind is object_id / local_ref / remote_ref (or "" when unresolved).

    FRESH is the only status a binder may bind on. Everything else is a refusal
    with the exact remedy in ``detail`` — the binder maps it to NOT_RUN and the
    truth ledger maps that to terminal UNVERIFIABLE.
    """
    ref = str(ref or "").strip()
    report = {"ref": ref, "resolved": "", "status": MISSING, "anchor_kind": "", "detail": "", "reproduce": "", "truth_boundary": REF_INTEGRITY_TRUTH_BOUNDARY}
    if not ref:
        report["detail"] = "empty ref."
        return report

    resolved = _resolve(repo, ref)
    if resolved is None:
        obj_type = _object_type(repo, ref)
        if obj_type is not None:
            report.update(status=NOT_A_COMMIT,
                          detail=f"{ref} resolves to a {obj_type}, not a commit.",
                          reproduce=f"git -C {repo} cat-file -t {ref}")
        else:
            report.update(detail=f"{ref} does not resolve in {repo} (never fetched, pruned, or mistyped).",
                          reproduce=f"git -C {repo} rev-parse --verify {ref}")
        return report
    report["resolved"] = resolved

    symbolic = _symbolic_full_name(repo, ref)
    # anchor_kind lets callers (e.g. protocol verify) distinguish an exact-pinned commit
    # id from a moving ref NAME, independent of currency status.
    report["anchor_kind"] = ("remote_ref" if symbolic.startswith("refs/remotes/")
                             else "local_ref" if symbolic.startswith("refs/")
                             else "object_id")

    if symbolic.startswith("refs/remotes/"):
        # A remote-tracking name is a local snapshot of remote state; verify it against
        # what the remote reports NOW. Unverifiable freshness is refused, not assumed.
        remote, _, branch = symbolic[len("refs/remotes/"):].partition("/")
        current = _remote_head(repo, remote, branch, remote_timeout)
        repro = f"git -C {repo} ls-remote --heads {remote} {branch}"
        if not branch or current is None:
            report.update(status=REMOTE_UNVERIFIED,
                          detail=(f"{ref} is a remote-tracking name but {remote!r} could not be contacted "
                                  f"(or no longer has branch {branch!r}); freshness cannot be established. "
                                  f"Pin an exact reachable SHA or restore connectivity."),
                          reproduce=repro)
        elif current != resolved:
            report.update(status=STALE_REMOTE_REF,
                          detail=(f"local {ref} is {resolved[:12]} but the remote reports {current[:12]} — "
                                  f"the snapshot is stale. Run git -C {repo} fetch --force {remote} {branch} "
                                  f"and re-bind."),
                          reproduce=repro)
        else:
            report.update(status=FRESH,
                          detail=f"{ref} ({resolved[:12]}) matches what {remote} reports now.",
                          reproduce=repro)
        return report

    if symbolic.startswith("refs/"):
        # A local branch or tag: local truth by definition — a claim about local state
        # cannot be stale with respect to itself.
        report.update(status=FRESH, detail=f"{ref} is a local ref resolving to {resolved[:12]}.",
                      reproduce=f"git -C {repo} rev-parse {ref}")
        return report

    # A raw object id (full, abbreviated, or uppercase — none carry a symbolic name), or a
    # relative expression such as HEAD~1. Existence is NOT currency: a commit that no
    # current local ref reaches is the signature of a rebased/force-pushed-away head, and
    # must not read as current truth (that is the false CONTRADICTED the guard refuses).
    if _is_reachable_from_local_ref(repo, resolved):
        report.update(status=FRESH,
                      detail=f"exact commit {resolved[:12]} is reachable from a current local ref.",
                      reproduce=f"git -C {repo} for-each-ref --contains={resolved[:12]} refs/heads refs/tags")
    else:
        report.update(status=SUPERSEDED,
                      detail=(f"exact commit {resolved[:12]} exists but no current local ref (branch/tag/HEAD) "
                              f"reaches it — a rebase/force-push likely replaced it, or it survives only in a "
                              f"remote-tracking snapshot whose freshness is unverified. Force-fetch and re-bind "
                              f"at the current head, or pin a local ref (git -C {repo} fetch --force --all)."),
                      reproduce=f"git -C {repo} for-each-ref --contains={resolved[:12]} refs/heads refs/tags")
    return report


def guard_finding(repo: str, ref: str, *, label: str = "head", allow_superseded: bool = False,
                  remote_timeout: int = 30) -> tuple[dict | None, dict]:
    """Run the guard and shape the outcome as a binder finding.

    Returns ``(blocking_finding, assessment)``. ``blocking_finding`` is None when the
    binder may proceed; otherwise it is a NOT_RUN-state finding ready to append, and
    the binder must stop before any content verdict. With ``allow_superseded`` a
    SUPERSEDED anchor proceeds (deliberately historical binds), but the currency
    finding is still returned inside the assessment for the binder to record — the
    result must not masquerade as current truth.
    """
    assessment = assess_head(repo, ref, remote_timeout=remote_timeout)
    status = assessment["status"]
    if status == FRESH:
        return None, assessment
    if status == SUPERSEDED and allow_superseded:
        return None, assessment
    finding = {
        "check": f"{label}-integrity",
        "state": "NOT_RUN",
        "detail": f"[{status}] {assessment['detail']}",
        "reproduce": assessment["reproduce"],
    }
    return finding, assessment
