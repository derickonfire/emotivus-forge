from __future__ import annotations

import json
import math
import os
from collections import Counter
from pathlib import Path
from typing import Any

from .brief import build_brief
from .graph import analyze_impact, build_graph, load_graph
from .project_memory import build_context_packet, project_status
from .package import build_package
from .confidentiality import scan_confidentiality
from .release_proof import build_release_proof
from .runner import run_profile
from .utils import read_json, tree_snapshot, utc_now, write_json

PASSPORT_SCHEMA = 1
PASSPORT_DIR = Path('.forge/passport')


def _command_name() -> str:
    value = os.environ.get("FORGE_INVOKED_AS", "forge").strip().lower()
    return "frg" if value == "frg" else "forge"


def _command(value: str) -> str:
    name = _command_name()
    return value if name == "forge" else value.replace("forge ", f"{name} ")


def _token_baseline(snapshot: dict[str, dict[str, Any]]) -> dict[str, Any]:
    total_bytes = sum(int(item.get("size", 0) or 0) for item in snapshot.values() if item.get("kind") == "file")
    source_files = sum(1 for item in snapshot.values() if item.get("kind") == "file")
    estimated = int(math.ceil(total_bytes / 4)) if total_bytes else 0
    return {
        "source_files": source_files,
        "source_bytes": total_bytes,
        "project_token_equivalent_estimate": estimated,
        "default_resume_budget_tokens": 1200,
        "method": "Heuristic only: project snapshot bytes divided by four. It is not a provider billing estimate.",
    }


def _resume_efficiency(baseline: dict[str, Any], *, packet_tokens: int, token_limit: int) -> dict[str, Any]:
    project_tokens = int(baseline.get("project_token_equivalent_estimate", 0) or 0)
    avoided = max(0, project_tokens - packet_tokens)
    reduction = round((avoided / project_tokens) * 100, 1) if project_tokens else 0.0
    return {
        **baseline,
        "packet_estimated_tokens": packet_tokens,
        "packet_token_limit": token_limit,
        "estimated_tokens_avoided": avoided,
        "estimated_context_reduction_percent": reduction,
        "within_budget": packet_tokens <= token_limit,
        "claim": "Forge reduces repeated context loading by retrieving minimum sufficient verified project truth; actual token use varies by model and task.",
    }


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = read_json(path)
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _snapshot_diff(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    previous_paths = set(previous)
    current_paths = set(current)
    added = sorted(current_paths - previous_paths)
    removed = sorted(previous_paths - current_paths)
    modified = sorted(
        path for path in previous_paths & current_paths
        if previous.get(path, {}).get('sha256') != current.get(path, {}).get('sha256')
        or previous.get(path, {}).get('kind') != current.get(path, {}).get('kind')
    )
    changed = added + modified + removed
    return {
        'status': 'changed' if changed else 'unchanged',
        'count': len(changed),
        'added': added,
        'modified': modified,
        'removed': removed,
        'paths': changed,
    }


def _surface_summary(proof: dict[str, Any]) -> dict[str, Any]:
    surfaces = proof.get('surfaces', {}) if isinstance(proof, dict) else {}
    items = surfaces.get('items', []) if isinstance(surfaces, dict) else []
    kinds = Counter(
        str((item.get('surface', {}) if isinstance(item.get('surface'), dict) else item).get('kind', 'unknown'))
        for item in items if isinstance(item, dict)
    )
    return {
        'count': int(surfaces.get('count', len(items)) or 0),
        'covered': int(surfaces.get('covered', 0) or 0),
        'uncovered': int(surfaces.get('uncovered', 0) or 0),
        'by_kind': dict(sorted(kinds.items())),
    }


def _release_summary(proof: dict[str, Any]) -> dict[str, Any]:
    if not proof:
        return {
            'claim_level': 'none',
            'claim_status': 'NOT_RUN',
            'problems': ['No release proof has been generated for the current project state.'],
            'limitations': [],
            'surfaces': {'count': 0, 'covered': 0, 'uncovered': 0, 'by_kind': {}},
        }
    problems = list(proof.get('problems', [])) + list(proof.get('dimension_problems', []))
    return {
        'claim_level': proof.get('claim_level', 'source-verified'),
        'claim_status': proof.get('claim_status', 'UNKNOWN'),
        'problems': sorted(set(str(item) for item in problems if str(item).strip())),
        'limitations': [str(item) for item in proof.get('limitations', []) if str(item).strip()],
        'surfaces': _surface_summary(proof),
        'target_environment': proof.get('target_environment', {}).get('status', 'UNKNOWN'),
        'deployment_states': proof.get('deployment_states', {}).get('status', 'UNKNOWN'),
        'delivery_provenance': proof.get('delivery_provenance', {}).get('status', 'UNKNOWN'),
    }


def _next_action(passport: dict[str, Any]) -> dict[str, str]:
    safety = passport.get('safety', {})
    continuity = passport.get('continuity', {})
    evidence = passport.get('evidence', {})
    changes = passport.get('changes', {})
    if safety.get('doctor_status') != 'PASS':
        return {
            'command': _command('forge check . --profile quick'),
            'reason': 'Resolve environment or project-layout blockers before relying on deeper proof.',
        }
    if changes.get('count', 0):
        return {
            'command': _command('forge check . --profile quick'),
            'reason': f"{changes.get('count', 0)} source path(s) changed since the last Forge observation.",
        }
    if continuity.get('objective', {}).get('text') == 'No declared next action was found.':
        return {
            'command': _command('forge resume .'),
            'reason': 'Review the current passport and declare the next bounded objective.',
        }
    if evidence.get('claim_status') != 'PASS':
        return {
            'command': 'forge check . --profile section',
            'reason': 'The current release claim is incomplete, blocked, or stale.',
        }
    return {
        'command': _command('forge resume .'),
        'reason': 'The project is understood; continue from the current objective with a bounded context packet.',
    }


def _uncertainties(passport: dict[str, Any]) -> list[dict[str, str]]:
    uncertainties: list[dict[str, str]] = []
    structure = passport.get('structure', {})
    safety = passport.get('safety', {})
    evidence = passport.get('evidence', {})
    workspace = passport.get('identity', {}).get('workspace', {})
    confidence = str(workspace.get('confidence', 'low'))
    if confidence != 'high':
        uncertainties.append({
            'area': 'workspace',
            'message': f"Workspace classification confidence is {confidence}.",
        })
    source_status = str(safety.get('source_completeness', 'unknown'))
    if source_status not in {'complete', 'PASS', 'pass'}:
        uncertainties.append({
            'area': 'source-completeness',
            'message': f"Development source completeness is {source_status}.",
        })
    surfaces = structure.get('surfaces', {})
    if int(surfaces.get('uncovered', 0) or 0):
        uncertainties.append({
            'area': 'surface-coverage',
            'message': f"{surfaces.get('uncovered', 0)} discovered surface(s) lack recurring execution evidence.",
        })
    if evidence.get('target_environment') not in {'PASS', 'NOT_APPLICABLE', 'not-required'}:
        uncertainties.append({
            'area': 'target-environment',
            'message': 'Target-environment parity is not proven.',
        })
    if evidence.get('deployment_states') not in {'PASS', 'NOT_APPLICABLE', 'not-required'}:
        uncertainties.append({
            'area': 'persisted-state',
            'message': 'Required deployment or persisted-state transitions are not fully proven.',
        })
    for problem in safety.get('doctor_problems', []):
        uncertainties.append({'area': 'environment', 'message': str(problem)})
    return uncertainties


def _markdown(passport: dict[str, Any]) -> str:
    identity = passport['identity']
    structure = passport['structure']
    continuity = passport['continuity']
    safety = passport['safety']
    evidence = passport['evidence']
    changes = passport['changes']
    lines = [
        '# Forge Project Passport', '',
        f"- Project: **{identity.get('name', '')}**",
        f"- Project version: **{identity.get('version') or 'unversioned'}**",
        f"- Forge version: **{identity.get('forge_version', '')}**",
        f"- Workspace: **{identity.get('workspace', {}).get('classification', 'unknown')}** ({identity.get('workspace', {}).get('confidence', 'low')} confidence)",
        f"- Objective: {continuity.get('objective', {}).get('text', '')}",
        f"- Source changes since last observation: **{changes.get('count', 0)}**",
        f"- Doctor: **{safety.get('doctor_status', 'UNKNOWN')}**",
        f"- Strongest current claim: **{evidence.get('claim_level', 'none')}** ({evidence.get('claim_status', 'NOT_RUN')})",
        '', '## Structure', '',
        f"- Graph nodes / edges: {structure.get('graph', {}).get('nodes', 0)} / {structure.get('graph', {}).get('edges', 0)}",
        f"- Discovered surfaces: {structure.get('surfaces', {}).get('count', 0)}",
        f"- Covered / uncovered surfaces: {structure.get('surfaces', {}).get('covered', 0)} / {structure.get('surfaces', {}).get('uncovered', 0)}",
        f"- Adapters: {', '.join(structure.get('adapters', [])) or 'none'}",
        '', '## Continuity', '',
        f"- Active plan: {continuity.get('active_plan', {}).get('title') or 'none'}",
        f"- Active pivot: {continuity.get('active_pivot', {}).get('title') or 'none'}",
        f"- Durable records: {continuity.get('counts', {}).get('active_records', 0)}",
        f"- Learned contracts: {continuity.get('learned_contracts', 0)}",
        f"- Project token-equivalent estimate: {continuity.get('token_efficiency', {}).get('project_token_equivalent_estimate', 0):,}",
        f"- Default compact Resume budget: {continuity.get('token_efficiency', {}).get('default_resume_budget_tokens', 1200):,} tokens",
        '', '## Evidence boundary', '',
        f"- Target environment: {evidence.get('target_environment', 'UNKNOWN')}",
        f"- Deployment states: {evidence.get('deployment_states', 'UNKNOWN')}",
        f"- Delivery provenance: {evidence.get('delivery_provenance', 'UNKNOWN')}",
        '', '## Next action', '',
        f"`{passport.get('next_action', {}).get('command', _command('forge resume .'))}`",
        '', passport.get('next_action', {}).get('reason', ''), '',
    ]
    if passport.get('uncertainties'):
        lines += ['## Uncertainties', ''] + [f"- **{item['area']}** — {item['message']}" for item in passport['uncertainties']] + ['']
    if changes.get('paths'):
        lines += ['## Changed paths', ''] + [f"- `{path}`" for path in changes['paths'][:100]] + ['']
    return '\n'.join(lines).rstrip() + '\n'


def build_project_passport(
    project_root: Path,
    forge_root: Path,
    config: dict[str, Any],
    *,
    refresh_graph: bool = False,
    refresh_proof: bool = False,
    checkpoint: bool = False,
    checkpoint_kind: str = 'observed',
) -> dict[str, Any]:
    project_root = project_root.resolve()
    output_dir = project_root / PASSPORT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    graph = build_graph(project_root, forge_root, config, write=True) if refresh_graph else (load_graph(project_root, config) or build_graph(project_root, forge_root, config, write=True))
    brief = build_brief(project_root, forge_root, config, write=True)
    status = project_status(project_root, forge_root, config, budget='compact')

    proof_path = project_root / str(config.get('release_proof', {}).get('output_dir', '.forge/release-proof')) / 'latest.json'
    proof = build_release_proof(project_root, forge_root, config, write=True) if refresh_proof else _read_json_object(proof_path)
    release = _release_summary(proof)

    excludes = config.get('paths', {}).get('exclude', [])
    current_snapshot = tree_snapshot(project_root, excludes, forge_root)
    observed_path = output_dir / 'observed-snapshot.json'
    adopted_path = output_dir / 'adopted-snapshot.json'
    previous_snapshot = _read_json_object(observed_path) or _read_json_object(adopted_path)
    changes = _snapshot_diff(previous_snapshot, current_snapshot) if previous_snapshot else {
        'status': 'baseline', 'count': 0, 'added': [], 'modified': [], 'removed': [], 'paths': [],
    }

    passport: dict[str, Any] = {
        'schema': PASSPORT_SCHEMA,
        'generated_utc': utc_now(),
        'identity': {
            'name': config.get('project', {}).get('name', project_root.name),
            'identity': config.get('project', {}).get('identity', ''),
            'version': config.get('versioning', {}).get('target_version', ''),
            'forge_version': config.get('forge_version', ''),
            'workspace': config.get('workspace', {}),
            'deployment_target': config.get('project', {}).get('deployment_target', ''),
        },
        'structure': {
            'adapters': list(config.get('adapters', [])),
            'runtime_requirements': config.get('runtime_requirements', {}),
            'graph': graph.get('summary', {}),
            'surfaces': release['surfaces'],
        },
        'continuity': {
            'objective': brief.get('objective', {}),
            'active_plan': brief.get('active_plan', {}),
            'active_pivot': brief.get('active_pivot', {}),
            'development_mode': brief.get('development_mode', 'development'),
            'counts': status.get('counts', {}),
            'learned_contracts': brief.get('active_learned_contracts', 0),
            'last_green': brief.get('last_green', {}),
            'source_changed_since_last_green': brief.get('source_changed_since_last_green'),
            'token_efficiency': _token_baseline(current_snapshot),
        },
        'safety': {
            'doctor_status': brief.get('doctor_status', 'UNKNOWN'),
            'doctor_problems': brief.get('doctor_problems', []),
            'source_completeness': config.get('source_completeness', {}).get('status', 'unknown'),
            'work_scope': config.get('work', {}),
            'packaging_contradictions': config.get('packaging_policy', {}).get('contradictions', []),
        },
        'evidence': release,
        'changes': changes,
        'commands': {
            'help': _command('forge help'),
            'adopt': _command('forge adopt .'),
            'resume': _command('forge resume .'),
            'check': _command('forge check . --profile quick'),
            'ship': _command('forge ship .'),
            'aliases': ['forge', 'frg'],
        },
    }
    passport['uncertainties'] = _uncertainties(passport)
    passport['next_action'] = _next_action(passport)

    write_json(output_dir / 'passport.json', passport)
    (output_dir / 'passport.md').write_text(_markdown(passport), encoding='utf-8')
    if checkpoint:
        write_json(observed_path, current_snapshot)
        if checkpoint_kind == 'adopted' or not adopted_path.is_file():
            write_json(adopted_path, current_snapshot)
        write_json(output_dir / f'{checkpoint_kind}-snapshot.json', current_snapshot)
    passport['output'] = str(output_dir / 'passport.json')
    passport['markdown'] = str(output_dir / 'passport.md')
    return passport


def build_resume_packet(
    project_root: Path,
    forge_root: Path,
    config: dict[str, Any],
    *,
    budget: str = 'compact',
    refresh: bool = False,
) -> dict[str, Any]:
    passport = build_project_passport(project_root, forge_root, config, refresh_graph=refresh, refresh_proof=False, checkpoint=False)
    context = build_context_packet(project_root, forge_root, config, mode='task', budget=budget, write=True)
    payload = {
        'schema': 1,
        'generated_utc': utc_now(),
        'project': passport['identity'],
        'objective': passport['continuity']['objective'],
        'active_plan': context.get('active_plan', {}),
        'active_pivot': context.get('active_pivot', {}),
        'records': context.get('records', []),
        'relevant_architecture': context.get('architecture', {}),
        'learned_contracts': context.get('learned_contracts', []),
        'changes': passport['changes'],
        'uncertainties': passport['uncertainties'],
        'evidence': passport['evidence'],
        'next_action': passport['next_action'],
        'retrieval': context.get('retrieval', {}),
        'estimated_tokens': context.get('estimated_tokens', 0),
        'token_limit': context.get('token_limit', 0),
        'within_budget': context.get('within_budget', True),
    }
    payload['token_efficiency'] = _resume_efficiency(
        passport.get('continuity', {}).get('token_efficiency', {}),
        packet_tokens=int(payload['estimated_tokens'] or 0),
        token_limit=int(payload['token_limit'] or 0),
    )
    output_dir = project_root.resolve() / PASSPORT_DIR
    write_json(output_dir / 'resume.json', payload)
    lines = [
        '# Forge Resume Packet', '',
        f"- Project: **{payload['project'].get('name', '')}**",
        f"- Objective: {payload['objective'].get('text', '')}",
        f"- Changed paths since last Forge observation: **{payload['changes'].get('count', 0)}**",
        f"- Current proof: **{payload['evidence'].get('claim_level', 'none')}** ({payload['evidence'].get('claim_status', 'NOT_RUN')})",
        f"- Estimated Resume context tokens: {payload['estimated_tokens']:,} / {payload['token_limit']:,}",
        f"- Project token-equivalent estimate: {payload['token_efficiency'].get('project_token_equivalent_estimate', 0):,}",
        f"- Estimated repeated context avoided: {payload['token_efficiency'].get('estimated_tokens_avoided', 0):,} ({payload['token_efficiency'].get('estimated_context_reduction_percent', 0)}%)",
        f"- Token estimate note: {payload['token_efficiency'].get('method', '')}",
        '', '## Next action', '',
        f"`{payload['next_action'].get('command', _command('forge resume .'))}`", '',
        payload['next_action'].get('reason', ''), '',
    ]
    if payload['active_plan']:
        lines += ['## Active plan', '', f"- {payload['active_plan'].get('title', '')}: {payload['active_plan'].get('objective', '')}", '']
    if payload['records']:
        lines += ['## Durable project records', ''] + [f"- **{item.get('type', 'record')}** — {item.get('title', '')}: {item.get('summary', '')}" for item in payload['records']] + ['']
    if payload['relevant_architecture'].get('nodes'):
        lines += ['## Relevant files and surfaces', ''] + [f"- `{item.get('path', '')}` ({item.get('type', 'unknown')})" for item in payload['relevant_architecture']['nodes']] + ['']
    (output_dir / 'resume.md').write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')
    payload['output'] = str(output_dir / 'resume.json')
    payload['markdown'] = str(output_dir / 'resume.md')
    return payload


def check_project(
    project_root: Path,
    forge_root: Path,
    config: dict[str, Any],
    *,
    profile: str = 'quick',
    changed_paths: list[str] | None = None,
    fresh: bool = True,
    resume: bool = False,
    only: list[str] | None = None,
    allow_anomaly: list[str] | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    pre = build_project_passport(project_root, forge_root, config, refresh_graph=True, refresh_proof=False, checkpoint=False)
    actual_changes = list(pre.get('changes', {}).get('paths', []))
    requested = [str(path).strip().replace('\\', '/') for path in (changed_paths or []) if str(path).strip()]
    changed = sorted(set(actual_changes + requested))
    impact: dict[str, Any] = {}
    if changed:
        impact = analyze_impact(project_root, forge_root, config, changed, write=True)
    gate = run_profile(
        project_root, forge_root, config, profile,
        resume=resume, fresh=fresh, only=only or [], allow_anomaly=allow_anomaly or [],
    )
    proof = build_release_proof(project_root, forge_root, config, write=True)
    passport = build_project_passport(project_root, forge_root, config, refresh_graph=False, refresh_proof=False, checkpoint=True, checkpoint_kind='check')
    payload = {
        'schema': 1,
        'generated_utc': utc_now(),
        'status': gate.get('status', 'UNKNOWN'),
        'profile': profile,
        'changes': pre.get('changes', {}),
        'impact': {
            'risk': impact.get('risk', {}),
            'impacted_nodes': len(impact.get('impacted_nodes', [])) if impact else 0,
            'targeted_tests': impact.get('targeted_tests', []) if impact else [],
            'recommended_live_checks': impact.get('recommended_live_checks', []) if impact else [],
        },
        'gate': {
            'status': gate.get('status', 'UNKNOWN'),
            'completed_count': gate.get('completed_count', 0),
            'remaining_count': gate.get('remaining_count', 0),
            'status_counts': gate.get('status_counts', {}),
            'report': str(project_root / config.get('paths', {}).get('reports', '.forge/reports') / f'{profile}.json'),
        },
        'release_claim': _release_summary(proof),
        'passport': passport.get('output', ''),
    }
    output_dir = project_root / PASSPORT_DIR
    write_json(output_dir / 'check.json', payload)
    payload['output'] = str(output_dir / 'check.json')
    return payload


def ship_project(
    project_root: Path,
    forge_root: Path,
    config: dict[str, Any],
    *,
    output: Path | None = None,
    dry_run: bool = False,
    development: bool = False,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    gate = run_profile(project_root, forge_root, config, 'release', fresh=True)
    proof = build_release_proof(project_root, forge_root, config, write=True)
    confidentiality = scan_confidentiality(
        project_root, write=True,
        output_dir=str(config.get('confidentiality', {}).get('report_dir', '.forge/confidentiality')),
        scan_archives=bool(config.get('confidentiality', {}).get('scan_archives', True)),
    )
    blockers: list[str] = []
    if gate.get('status') != 'PASS':
        blockers.append(f"release check is {gate.get('status', 'UNKNOWN')}")
    if proof.get('claim_status') != 'PASS':
        blockers.extend(str(item) for item in proof.get('problems', []) if str(item).strip())
        blockers.extend(str(item) for item in proof.get('dimension_problems', []) if str(item).strip())
    if confidentiality.get('status') != 'PASS':
        blockers.append('confidentiality or secret-contamination scan failed')
    if not development and str(config.get('versioning', {}).get('state', '')).lower() in {'development', 'dev', 'draft'}:
        blockers.append('project version is still marked as development; use --development only for an explicit non-production build')

    package: dict[str, Any] = {
        'status': 'BLOCKED', 'dry_run': dry_run, 'output': str(output or ''),
        'sha256': '', 'included_count': 0, 'excluded_count': 0, 'problems': blockers,
    }
    if not blockers:
        package = build_package(project_root, forge_root, config, dry_run=dry_run, output=output)
        blockers.extend(str(item) for item in package.get('problems', []) if str(item).strip())

    status = 'PASS' if not blockers and package.get('status') == 'PASS' else 'BLOCKED'
    proof_card = {
        'schema': 1,
        'generated_utc': utc_now(),
        'project': config.get('project', {}).get('name', project_root.name),
        'project_version': config.get('versioning', {}).get('target_version', ''),
        'status': status,
        'release_check': gate.get('status', 'UNKNOWN'),
        'strongest_supported_claim': proof.get('claim_level', 'source-verified'),
        'claim_status': proof.get('claim_status', 'UNKNOWN'),
        'surfaces': _surface_summary(proof),
        'target_environment': proof.get('target_environment', {}).get('status', 'UNKNOWN'),
        'deployment_states': proof.get('deployment_states', {}).get('status', 'UNKNOWN'),
        'delivery_provenance': proof.get('delivery_provenance', {}).get('status', 'UNKNOWN'),
        'confidentiality': confidentiality.get('status', 'UNKNOWN'),
        'artifact': {
            'path': package.get('output', ''),
            'sha256': package.get('sha256', ''),
            'dry_run': package.get('dry_run', dry_run),
            'included_count': package.get('included_count', 0),
            'excluded_count': package.get('excluded_count', 0),
        },
        'blockers': sorted(set(blockers)),
        'limitations': [str(item) for item in proof.get('limitations', []) if str(item).strip()],
    }
    output_dir = project_root / PASSPORT_DIR
    write_json(output_dir / 'proof-card.json', proof_card)
    lines = [
        '# Forge Proof Card', '',
        f"- Project: **{proof_card['project']}**",
        f"- Version: **{proof_card['project_version'] or 'unversioned'}**",
        f"- Ship status: **{proof_card['status']}**",
        f"- Release check: **{proof_card['release_check']}**",
        f"- Strongest supported claim: **{proof_card['strongest_supported_claim']}** ({proof_card['claim_status']})",
        f"- Surfaces covered: {proof_card['surfaces'].get('covered', 0)} / {proof_card['surfaces'].get('count', 0)}",
        f"- Target environment: {proof_card['target_environment']}",
        f"- Deployment states: {proof_card['deployment_states']}",
        f"- Confidentiality scan: {proof_card['confidentiality']}",
        f"- Artifact: {proof_card['artifact'].get('path') or 'not created'}", '',
    ]
    if proof_card['blockers']:
        lines += ['## Blockers', ''] + [f"- {item}" for item in proof_card['blockers']] + ['']
    if proof_card['limitations']:
        lines += ['## Limitations', ''] + [f"- {item}" for item in proof_card['limitations']] + ['']
    (output_dir / 'proof-card.md').write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')
    build_project_passport(project_root, forge_root, config, refresh_graph=False, refresh_proof=False, checkpoint=False)
    return {
        'status': status,
        'artifact': proof_card['artifact'],
        'claim': {
            'level': proof_card['strongest_supported_claim'],
            'status': proof_card['claim_status'],
        },
        'blockers': proof_card['blockers'],
        'limitations': proof_card['limitations'],
        'proof_card': str(output_dir / 'proof-card.json'),
        'proof_card_markdown': str(output_dir / 'proof-card.md'),
    }
