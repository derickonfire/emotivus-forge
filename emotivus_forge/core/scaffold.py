"""Scaffold Forge's truth+protocol layer into a project repo (R10, north-star headline).

The gap (planning/OBSERVED-MISS-discipline-has-no-onramp.md): Forge can CHECK a
multi-agent protocol (Phase 3) but not ESTABLISH one, so every adopter hand-
assembles the very ceremony the field note warns is the disease. `forge init`
plants the discipline in ONE command, strictly additively (never overwrites; every
skipped path is reported), and emits a seed protocol that `forge protocol verify`
certifies on day one.

Ceremony is opt-in and scaled to collaboration size:
  truth (default) — the truth layer only (seed protocol + gate + note)
  pair            — + a short AI operating agreement
  fleet           — + the harvested LineCheck coordination substrate

Deterministic and advisory. It writes into the TARGET repo, never Forge's own
tree; version-bump / seal / distributable stay the owner's act.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .protocol_verify import CONFIRMED, verify_protocol

PROFILES = ("truth", "pair", "fleet")
CI_CHOICES = ("none", "github")


def seed_protocol() -> dict:
    """The minimal well-formed protocol that verifies CONFIRMED/LIVE on day one and
    does not rot.

    An empty protocol is NOT_RUN — not a pass. A seed claim pinning today's HEAD
    would flip to CONTRADICTED under --repo after the next commit (the R8 head-
    currency guard doing its job). So the seed is a genesis ``act`` (a structured
    event, NOT head-pinning) plus a single ``initial_holder``: structured-state
    CONFIRMED, single conserved baton LIVE, and nothing to fail on exact-head /
    receipts / supersession / owner-gate — while claiming no verification that was
    not earned. Real claims / accepts / handoffs supersede it as work proceeds.
    """
    return {
        "initial_holder": "owner",
        "records": [
            {
                "id": "genesis",
                "type": "act",
                "party": "owner",
                "detail": (
                    "Protocol established by forge init. Record real claims, accepts, "
                    "and handoffs as work proceeds; supersede this genesis marker."
                ),
            }
        ],
    }


_GATE_SH = """#!/bin/sh
# Forge truth gate — run the deterministic checks that back this repo's project truth.
# Advisory today, CI-enforceable tomorrow. It honors Forge's one invariant:
#   NEVER upgrade NOT_RUN to PASS. A check that cannot run FAILS the gate (nonzero)
#   rather than passing silently. Verification is earned, never assumed.
#
# Forge is invoked via $FORGE (default: forge); set FORGE if your install is not on
# PATH — it is expanded unquoted so a multi-word command works, so keep it free of
# paths containing spaces, e.g.  FORGE="python3 /path/to/forge.py" ./forge-gate.sh
set -eu

cd "$(dirname "$0")"
FORGE="${FORGE:-forge}"

echo "forge-gate: protocol verify"
$FORGE protocol verify --config .forge/protocol.json --liveness

# Add binder invocations here as this repo declares claims to bind, e.g.:
#   $FORGE bind claims --repo . --config .forge/claims.json
#   $FORGE bind gate-coverage --repo . --head HEAD --config .forge/gate.json

echo "forge-gate: OK"
"""


_FORGE_README = """# Forge truth layer

Deterministic project-truth artifacts Forge checks. Planted by `forge init`; safe
to edit and extend. Forge is *advisory* — nothing here authorizes anything; it
makes this repo's truth falsifiable.

## The gate

`../forge-gate.sh` runs the checks that back this repo's truth. Wire it into CI or
a pre-push hook. It invokes Forge as `${FORGE:-forge}`; set `FORGE` if your install
is not on `PATH` (e.g. `FORGE="python3 /path/to/forge.py"`).

## The one invariant

**Never upgrade NOT_RUN to PASS.** A check that cannot run fails the gate; it is
never smoothed into a pass. Verification is earned, never assumed.

## protocol.json

A declared multi-agent collaboration protocol, checked by `forge protocol verify`
against six invariants: exact-head claims, bindable receipts on accepts, structured
(not prose-only) state, history-preserving supersession, owner-gated irreversible
acts, and single-baton liveness. It ships with a genesis marker; record real
claims / accepts / handoffs as work proceeds and supersede — never edit — history.
"""


_OPERATING_AGREEMENT = """# AI operating agreement

A minimal, checkable protocol for the AI (and human) collaborators on this repo.
The machine-checkable half lives in `.forge/protocol.json` and is verified by
`forge protocol verify`; this document is the human-readable half. Keep them in
step: if a rule is not in `protocol.json`, the gate does not enforce it.

## Roles

- **owner** — sole merger; the only party who authorizes irreversible acts.
- **peer(s)** — propose claims and accepts; hold the baton only via an explicit handoff.

## Record shapes (what protocol.json stores)

- **claim** — pins an *exact* commit head (never a moving branch name).
- **accept** — carries a bindable receipt: an exact reviewed head + a verifiable id.
- **handoff** — transfers the single baton from the current holder to a named party.
- **act** — a structured event; if `irreversible`, it must carry owner authorization.

## The rules the gate enforces

1. Every current claim/accept pins an exact, current head (a stale or moving ref fails).
2. Every current accept carries a bindable receipt.
3. State is structured, not prose-only.
4. Supersession preserves history — no forks, no cycles; supersede, never edit.
5. Irreversible acts are owner-gated.
6. Exactly one party holds the baton, or the protocol is STALLED.
"""


_BUS_README = """# Coordination bus

An append-only coordination surface for multi-agent work. Each message is an
immutable numbered lane record; state is superseded, never edited. This is the
*reusable shape* harvested from a real Claude+Codex collaboration — the domain
checks that collaboration ran are deliberately NOT included.

## Convention

```
exchange/threads/<THREAD-ID>/<party>/<NNNN>-<slug>.md
```

- `<THREAD-ID>` — a stable topic id (e.g. `ARCH-1`, `RELEASE`).
- `<party>` — the author (`owner`, a peer name).
- `<NNNN>` — a zero-padded, monotonically increasing lane number.

## Rules

- Append only. To revise, write a NEW record that supersedes the old one; never
  rewrite history.
- A claim about a git head names an **exact commit**, never a moving branch ref.
- An acceptance carries a **bindable receipt** (exact reviewed head + verifiable id).
- Mirror consequential records into `.forge/protocol.json` so `forge protocol
  verify` can certify the protocol — prose alone is not verification.
"""


_AUTHORITY_INDEX = """# Authority index

Who may authorize what. Forge does not authenticate human identity; this index is
project-declared and reviewed. Irreversible acts (merge, release, deploy) are
owner-gated and the gate checks that the corresponding `protocol.json` record
carries owner authorization.

| Authority | Holder | Scope | Evidence |
|---|---|---|---|
| Sole merger | owner | Merge to the default branch | (link) |
| Release | owner | Tag / publish an exact package | (link) |
| Review | (peer) | Produce bindable acceptance receipts | (link) |

Replace the placeholders. Add rows as the collaboration grows; keep it in step
with `ROLE-MATRIX.md` and `.forge/protocol.json`.
"""


_WORK_REGISTER = """# Work register

Append-only record of units of work and their current truth state. Supersede a
row by adding a new one that points at it; never edit history. Where a row makes a
checkable claim, bind it (`forge bind` / `forge protocol verify`) rather than
asserting it in prose.

| Id | Work | Party | State | Ground-truth binding |
|---|---|---|---|---|
| W-0001 | (describe) | (party) | OPEN / DONE | (exact head / receipt / NOT_RUN) |

`State` never carries a PASS that was not earned: an unrun check is `NOT_RUN`, and
NOT_RUN is terminal until a binder actually re-derives it.
"""


_ROLE_MATRIX = """# Role matrix

The owner/sole-merger split the gate enforces. This is the coordination invariant
harvested from the field: exactly one party merges, and irreversible acts are
owner-gated.

| Capability | owner | peer |
|---|---|---|
| Propose a claim | yes | yes |
| Produce an acceptance receipt | yes | yes |
| Hold the baton (via handoff) | yes | yes |
| Merge to the default branch | **yes (sole)** | no |
| Authorize an irreversible act | **yes** | no |

Exactly one baton exists; a party acts only while it holds the baton. A forged or
dropped baton is STALLED, and `forge protocol verify --liveness` catches it.
"""


_GH_WORKFLOW = """name: forge-gate
on: [push, pull_request]
jobs:
  forge-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      # Make Forge available to the gate. Pick ONE and uncomment:
      #   - run: pip install emotivus-forge
      #   - run: echo "FORGE=python3 $PWD/vendor/forge/forge.py" >> "$GITHUB_ENV"
      - name: Run Forge truth gate
        run: sh ./forge-gate.sh
"""


@dataclass(frozen=True)
class _Template:
    path: str          # relative to the target root
    content: str
    executable: bool = False


def _templates(profile: str, ci: str) -> list[_Template]:
    """The exact file set a (profile, ci) combination emits. Deterministic."""
    seed = json.dumps(seed_protocol(), indent=2, ensure_ascii=False) + "\n"
    files = [
        _Template(".forge/protocol.json", seed),
        _Template("forge-gate.sh", _GATE_SH, executable=True),
        _Template(".forge/README.md", _FORGE_README),
    ]
    if profile in ("pair", "fleet"):
        files.append(_Template("AI-OPERATING-AGREEMENT.md", _OPERATING_AGREEMENT))
    if profile == "fleet":
        files += [
            _Template("exchange/README.md", _BUS_README),
            _Template("AUTHORITY-INDEX.md", _AUTHORITY_INDEX),
            _Template("WORK-REGISTER.md", _WORK_REGISTER),
            _Template("ROLE-MATRIX.md", _ROLE_MATRIX),
        ]
    if ci == "github":
        files.append(_Template(".github/workflows/forge-gate.yml", _GH_WORKFLOW))
    return files


def _validate(profile: str, ci: str) -> None:
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}; choose from {list(PROFILES)}")
    if ci not in CI_CHOICES:
        raise ValueError(f"unknown ci {ci!r}; choose from {list(CI_CHOICES)}")


def plan_scaffold(target: str, profile: str = "truth", ci: str = "none") -> dict:
    """Plan (do not write) the scaffold: for each template, whether it would be
    created or skipped because it already exists. Also self-checks the seed
    protocol so `forge init` can report that what it plants verifies on day one."""
    _validate(profile, ci)
    root = Path(target)
    planned: list[dict] = []
    for tmpl in _templates(profile, ci):
        dest = root / tmpl.path
        planned.append({
            "path": tmpl.path,
            "action": "skip-exists" if dest.exists() else "create",
            "executable": tmpl.executable,
        })
    seed_result = verify_protocol(seed_protocol(), check_liveness=True,
                                  source=".forge/protocol.json")
    return {
        "target": str(root),
        "profile": profile,
        "ci": ci,
        "planned": planned,
        "create_count": sum(1 for p in planned if p["action"] == "create"),
        "skip_count": sum(1 for p in planned if p["action"] == "skip-exists"),
        "seed_verdict": seed_result["verdict"],
        "seed_liveness": seed_result["liveness_checked"] and seed_result["verdict"] == CONFIRMED,
    }


def apply_scaffold(target: str, profile: str = "truth", ci: str = "none",
                   dry_run: bool = False) -> dict:
    """Apply the scaffold, strictly additively: never overwrite an existing file;
    report every path actually written. ``dry_run`` writes nothing."""
    result = plan_scaffold(target, profile, ci)
    root = Path(target)
    written: list[str] = []
    if not dry_run:
        for tmpl in _templates(profile, ci):
            dest = root / tmpl.path
            if dest.exists():
                continue  # additive: never overwrite what the adopter already has
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(tmpl.content, encoding="utf-8")
            if tmpl.executable:
                dest.chmod(0o755)
            written.append(tmpl.path)
    result["dry_run"] = dry_run
    result["written"] = written
    return result
