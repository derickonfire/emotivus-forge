"""Gate-coverage differ (G1 project-truth).

The gap this reports was proven in the LineCheck engagement: a behaviour check
(`check_worklist_behavior.php`, 76 assertions) existed in the tree but was never
invoked by the CI gate, so its PASS rested on the author's word. A green gate that
silently omits a check reads as "covered" when it is not.

This instrument enumerates the check scripts present in the tree and reports which
ones are not referenced by the project's declared gate-invocation sources at an
exact head — the checks the gate effectively treats as NOT_RUN.

Honesty guard: many gates invoke checks by a glob/loop rather than by name (e.g.
``for f in tools/check_*.php``). Per-check coverage is meaningless there, so the
differ DETECTS that case and returns NOT_RUN rather than falsely reporting every
check as a gap. It never upgrades an undeterminable state to "covered".
"""
from __future__ import annotations

import fnmatch
import subprocess

from .truth import TRUTH_STATES

COVERED = "COVERED"       # every inventoried check is referenced by a declared gate source
GAPS = "GAPS"             # one or more inventoried checks are not gate-wired
NOT_RUN = "NOT_RUN"       # could not assess (unreachable, no inventory, no gate sources, or swept)
assert NOT_RUN in set(TRUTH_STATES)

GATE_COVERAGE_TRUTH_BOUNDARY = (
    "Forge enumerates check scripts present in the tree and reports which are not referenced "
    "by the project's declared gate-invocation sources at an exact head. A reference is textual: "
    "Forge confirms a check is named by a declared gate source, not that it actually executes, "
    "and an unreferenced check may still run via dynamic or indirect invocation. When a gate "
    "invokes checks by glob/loop, per-check coverage is indeterminate and Forge returns NOT_RUN. "
    "Forge matches a check by path, basename, or basename-stem, so it models gates that invoke "
    "checks by name or module reference; it does not model architectures where check logic lives "
    "in separately-tested modules behind thin CLI wrappers. Coverage is only as complete as the "
    "declared gate_sources list; this is a coverage report, not proof that any check ran."
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


def _ls_tree(repo: str, ref: str) -> list[str]:
    proc = _git(repo, ["ls-tree", "-r", "--name-only", ref])
    if proc.returncode != 0:
        raise GitError(proc.stderr.strip() or f"git ls-tree {ref} failed")
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _match_any(path: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in globs)


def _finding(check: str, state: str, detail: str, reproduce: str = "") -> dict:
    return {"check": check, "state": state, "detail": detail, "reproduce": reproduce}


def report_gate_coverage(repo: str, head: str, config: dict) -> dict:
    """Report inventoried checks not referenced by the declared gate sources at ``head``.

    config keys:
      check_inventory[]  — globs for check scripts, e.g. ["site/tools/check_*.php"]
      gate_sources[]     — globs for files that declare what the gate invokes,
                           e.g. [".github/workflows/*.yml", "run.sh"]
      [sweep_markers[]]  — substrings that indicate glob/loop invocation of the
                           inventory; defaults derived from check_inventory basenames.
    """
    findings: list[dict] = []
    unwired: list[str] = []
    checks: list[str] = []

    def result(verdict: str) -> dict:
        return {
            "target": repo,
            "head": head,
            "verdict": verdict,
            "truth_boundary": GATE_COVERAGE_TRUTH_BOUNDARY,
            "inventory_count": len(checks),
            "unwired_checks": unwired,
            "findings": findings,
        }

    if not _is_commit(repo, head):
        findings.append(_finding("reachability", NOT_RUN,
                                 f"head {head} is not a reachable commit in {repo}.",
                                 f"git -C {repo} cat-file -t {head}"))
        return result(NOT_RUN)

    try:
        tree = _ls_tree(repo, head)
    except GitError as exc:
        findings.append(_finding("tree-read", NOT_RUN, str(exc)))
        return result(NOT_RUN)

    check_globs = config["check_inventory"]
    checks = sorted(p for p in tree if _match_any(p, check_globs))
    if not checks:
        findings.append(_finding("check-inventory", NOT_RUN,
                                 f"no check files matched {check_globs} at {head}."))
        return result(NOT_RUN)

    gate_paths = sorted(p for p in tree if _match_any(p, config["gate_sources"]))
    if not gate_paths:
        findings.append(_finding("gate-sources", NOT_RUN,
                                 f"no declared gate sources matched {config['gate_sources']} at {head}; "
                                 f"cannot assess coverage."))
        return result(NOT_RUN)
    gate_text = "\n".join(_show(repo, head, p) or "" for p in gate_paths)

    # Honesty guard: detect glob/loop invocation of the inventory. Use the full
    # basename-glob and the dir-qualified glob (e.g. "check_*.py", "tools/check_*.py")
    # rather than a bare prefix, so an unrelated "check_" mention does not false-trigger.
    sweep_markers = config.get("sweep_markers")
    if sweep_markers is None:
        sweep_markers = []
        for g in check_globs:
            base = g.rsplit("/", 1)[-1]
            if "*" in base:
                sweep_markers.append(base)   # "check_*.py"
                sweep_markers.append(g)      # "tools/check_*.py"
    swept = [mk for mk in sweep_markers if mk and mk in gate_text]
    if swept:
        findings.append(_finding(
            "invocation-style", NOT_RUN,
            f"gate sources reference the inventory by pattern ({', '.join(sorted(set(swept)))}); "
            f"per-check coverage is indeterminate. Declare explicit check names to assess.",
            f"git -C {repo} grep -nE '{'|'.join(sorted(set(swept)))}' {head} -- " + " ".join(gate_paths)))
        return result(NOT_RUN)

    # Match by full path, basename, and (by default) the basename stem — so both
    # by-filename shell invocation (`php check_foo.php`) and by-stem/module reference
    # (`from tools.check_foo import`, `python -m ... check_foo`) count as wired.
    match_stem = config.get("match_stem", True)
    for c in checks:
        name = c.rsplit("/", 1)[-1]
        stem = name.rsplit(".", 1)[0]
        refs = [c, name] + ([stem] if match_stem else [])
        if any(r in gate_text for r in refs):
            continue
        unwired.append(c)

    repro = (f"compare `git -C {repo} ls-tree -r --name-only {head}` filtered to the inventory "
             f"against references in: " + " ".join(gate_paths))
    if unwired:
        for c in unwired:
            findings.append(_finding(c, NOT_RUN,
                                     f"{c} exists but is not referenced by any declared gate source; "
                                     f"the gate treats it as NOT_RUN."))
        findings.append(_finding("summary", NOT_RUN,
                                 f"{len(unwired)} of {len(checks)} inventoried checks are not gate-wired.",
                                 repro))
        return result(GAPS)

    findings.append(_finding("summary", COVERED,
                             f"all {len(checks)} inventoried checks are referenced by the declared gate "
                             f"sources ({len(gate_paths)} source file(s)).", repro))
    return result(COVERED)
