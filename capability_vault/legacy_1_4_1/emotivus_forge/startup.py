from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import load_config
from .guidance import build_help_guide
from .init_project import initialize_project
from .passport import build_project_passport, build_resume_packet, check_project
from .utils import utc_now, write_json

PASSPORT_DIR = Path('.forge/passport')
IGNORED_HOST_NAMES = {
    '.forge',
    '.emotivus-forge.json',
    '.DS_Store',
    'Thumbs.db',
}


def _looks_like_forge_artifact(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith('emotivus-forge') or lowered.startswith('run-forge') or lowered in {
        'forge.zip', 'forge', 'forge.cmd', 'forge.py', 'frg', 'frg.cmd', 'frg.py'
    }


def resolve_project_root(requested: Path, forge_root: Path) -> tuple[Path, list[str]]:
    """Resolve the host project without ever treating Forge Core as the target project."""
    requested = requested.resolve()
    forge_root = forge_root.resolve()
    if requested == forge_root or forge_root in requested.parents:
        candidate = forge_root.parent
    else:
        candidate = requested

    host_entries: list[str] = []
    try:
        entries = sorted(candidate.iterdir(), key=lambda path: path.name.lower())
    except OSError:
        return candidate, host_entries
    for path in entries:
        if path.name in IGNORED_HOST_NAMES:
            continue
        if path.resolve() == forge_root:
            continue
        if _looks_like_forge_artifact(path.name):
            continue
        host_entries.append(path.name)
    return candidate, host_entries


def run_forge(
    project_root: Path,
    forge_root: Path,
    *,
    check_profile: str = 'quick',
    resume_budget: str = 'compact',
) -> dict[str, Any]:
    """Perform the safe natural-language startup flow behind “Run Forge.”

    The flow may Adopt, Resume, or run a Quick Check. It never Ships, deploys,
    deletes, migrates production data, or applies environment repairs.
    """
    project_root, host_entries = resolve_project_root(project_root, forge_root)
    if not host_entries:
        return {
            'schema': 1,
            'generated_utc': utc_now(),
            'status': 'NEEDS_PROJECT',
            'mode': 'run-forge',
            'action': 'NONE',
            'project_root': str(project_root),
            'reason': 'No host-project files were found beside Forge.',
            'next_action': 'Extract the target project beside Emotivus-Forge, then run Forge again from the project root.',
            'safety': {'ship_invoked': False, 'destructive_action_invoked': False},
        }

    guide = build_help_guide(project_root, forge_root)
    state = str(guide.get('project_state', {}).get('state', 'NOT_ADOPTED'))
    initialized = False
    adopted = False
    check: dict[str, Any] = {}

    if state in {'NOT_ADOPTED', 'ADOPTION_INCOMPLETE'}:
        if not (project_root / '.emotivus-forge.json').is_file():
            initialize_project(project_root, forge_root, setup_answers={'preset': 'balanced', 'existing_tools': 'audit'})
            initialized = True
        config = load_config(project_root)
        passport = build_project_passport(
            project_root,
            forge_root,
            config,
            refresh_graph=True,
            refresh_proof=True,
            checkpoint=True,
            checkpoint_kind='adopted',
        )
        adopted = True
        resume = build_resume_packet(project_root, forge_root, config, budget=resume_budget, refresh=False)
        action = 'ADOPT + RESUME'
        status = 'ATTENTION' if passport.get('uncertainties') else 'PASS'
    elif state == 'CHANGED':
        config = load_config(project_root)
        check = check_project(project_root, forge_root, config, profile=check_profile, fresh=True)
        resume = build_resume_packet(project_root, forge_root, config, budget=resume_budget, refresh=False)
        passport = build_project_passport(project_root, forge_root, config, refresh_graph=False, refresh_proof=False, checkpoint=False)
        action = 'CHECK + RESUME'
        if check.get('status') != 'PASS':
            status = 'BLOCKED'
        elif passport.get('uncertainties') or resume.get('evidence', {}).get('claim_status') != 'PASS':
            status = 'ATTENTION'
        else:
            status = 'PASS'
    else:
        config = load_config(project_root)
        resume = build_resume_packet(project_root, forge_root, config, budget=resume_budget, refresh=False)
        passport = build_project_passport(project_root, forge_root, config, refresh_graph=False, refresh_proof=False, checkpoint=False)
        action = 'RESUME'
        status = 'ATTENTION' if passport.get('uncertainties') else 'PASS'

    payload: dict[str, Any] = {
        'schema': 1,
        'generated_utc': utc_now(),
        'status': status,
        'mode': 'run-forge',
        'action': action,
        'project_root': str(project_root),
        'project': passport.get('identity', {}),
        'initialized': initialized,
        'adopted': adopted,
        'changes': check.get('changes', {}) if check else resume.get('changes', {}),
        'objective': resume.get('objective', {}),
        'uncertainties': resume.get('uncertainties', []),
        'evidence': resume.get('evidence', {}),
        'next_action': resume.get('next_action', {}),
        'passport': passport.get('output', str(project_root / PASSPORT_DIR / 'passport.json')),
        'passport_markdown': passport.get('markdown', str(project_root / PASSPORT_DIR / 'passport.md')),
        'resume': resume.get('output', str(project_root / PASSPORT_DIR / 'resume.json')),
        'resume_markdown': resume.get('markdown', str(project_root / PASSPORT_DIR / 'resume.md')),
        'check': check,
        'safety': {
            'ship_invoked': False,
            'destructive_action_invoked': False,
            'automatic_actions_allowed': ['adopt', 'resume', 'check:quick'],
            'explicit_only': ['ship', 'deployment', 'production migration', 'deletion', 'environment repair'],
        },
    }
    output_dir = project_root / PASSPORT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / 'run-latest.json', payload)
    payload['output'] = str(output_dir / 'run-latest.json')
    return payload


def render_run_summary(payload: dict[str, Any]) -> str:
    status = str(payload.get('status', 'UNKNOWN'))
    if status == 'NEEDS_PROJECT':
        return '\n'.join([
            'FORGE NOT STARTED',
            str(payload.get('reason', 'No host project was found.')),
            f"Do next: {payload.get('next_action', '')}",
        ]).rstrip() + '\n'

    project = payload.get('project', {}) if isinstance(payload.get('project'), dict) else {}
    objective = payload.get('objective', {}) if isinstance(payload.get('objective'), dict) else {}
    evidence = payload.get('evidence', {}) if isinstance(payload.get('evidence'), dict) else {}
    changes = payload.get('changes', {}) if isinstance(payload.get('changes'), dict) else {}
    check = payload.get('check', {}) if isinstance(payload.get('check'), dict) else {}
    lines = [
        f"FORGE STARTED — {status}",
        f"Project: {project.get('name', Path(str(payload.get('project_root', '.'))).name)}",
        f"Action:  {payload.get('action', 'UNKNOWN')}",
        f"Goal:    {objective.get('text', '') or 'No explicit objective recorded yet.'}",
        f"Changes: {changes.get('count', 0)} path(s) in the current Resume packet",
        f"Proof:   {evidence.get('claim_level', 'none')} ({evidence.get('claim_status', 'NOT_RUN')})",
    ]
    if check:
        lines.append(f"Check:   {check.get('profile', 'quick')} ({check.get('status', 'UNKNOWN')})")
    lines.extend([
        f"Passport: {payload.get('passport_markdown', '')}",
        f"Resume:   {payload.get('resume_markdown', '')}",
        '',
        'Forge did not Ship, deploy, delete, migrate production data, or apply environment repairs.',
    ])
    if status == 'BLOCKED':
        lines.append('Development should pause on the reported Check blockers unless the owner explicitly accepts a bounded exception.')
    else:
        lines.append('Read the Resume packet before changing the project.')
    return '\n'.join(lines).rstrip() + '\n'
