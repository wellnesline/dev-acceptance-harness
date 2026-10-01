"""Actual OpenSpec CLI plus independent allowlisted code verification."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

# VERIFIER holds this gate and the shared verifier files: the repository itself, or a job's
# read-only pin under .harness/verifier-pins/<digest>/files. ROOT is the workspace under
# verification (profiles, specs, the job's own code and tests); --root sets it for a pinned run.
VERIFIER = Path(__file__).resolve().parents[1]
ROOT = VERIFIER
HOME = VERIFIER / 'dev_harness'
PACKAGE = HOME / 'tools/node_modules/@fission-ai/openspec'
VERSION = '1.14.0'
if str(VERIFIER) not in sys.path:
    sys.path.insert(0, str(VERIFIER))
from ops_harness import verifier_pins  # noqa: E402  (resolved from VERIFIER, i.e. the pin when pinned)
PIN = verifier_pins.owning_pin(Path(__file__))


def local_path(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(ROOT.resolve()):
        raise ValueError('Path must remain inside this repository')
    return path


def command(argv: list[str], cwd: Path, timeout: int = 90) -> tuple[int, str]:
    env = {**os.environ, 'OPENSPEC_TELEMETRY': '0', 'DO_NOT_TRACK': '1',
           'OPENSPEC_NO_UPDATE_CHECK': '1', 'CI': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
    completed = subprocess.run(argv, cwd=cwd, env=env, capture_output=True,
                               text=True, encoding='utf-8', errors='replace', timeout=timeout)
    return completed.returncode, completed.stdout


def official(args: list[str], workspace: Path) -> tuple[int, dict]:
    node = shutil.which('node')
    if not node or not (PACKAGE / 'bin/openspec.js').is_file():
        raise ValueError('Install local OpenSpec dependencies first')
    code, output = command([node, str(PACKAGE / 'bin/openspec.js'), *args], workspace)
    try:
        data = json.loads(output)
    except ValueError as exc:
        raise ValueError('Official OpenSpec returned invalid JSON') from exc
    if not isinstance(data, dict):
        raise ValueError('Official OpenSpec returned an unexpected response')
    return code, data


def load_profile(name: str, change: str, sample: bool) -> tuple[dict, Path]:
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,79}', change):
        raise ValueError('Invalid change ID')
    data = json.loads((ROOT / 'dev_harness/profiles.json').read_text(encoding='utf-8'))
    profile = data['profiles'].get(name)
    if not profile or profile['change'] != change or profile['sample'] is not sample:
        raise ValueError('Verification profile is not bound to this change/workspace')
    if not profile['source_paths'] or not profile['test_paths']:
        raise ValueError('A profile must cover implementation and tests')
    if profile['runner'] not in ('unittest', 'pytest'):
        raise ValueError('Unsupported fixed runner')
    for relative in profile['source_paths'] + profile['test_paths']:
        if not local_path(relative).is_file():
            raise ValueError('Profile references a missing source or test file')
    workspace = ROOT / 'dev_harness/project' if sample else ROOT
    check_workflow_delivery(profile,name,change,sample)
    return profile, workspace


def check_workflow_delivery(profile, name, change, sample=False):
    """Automatic new-profile enforcement; historical profiles are explicitly scoped."""
    config=json.loads((HOME/'workflow_delivery_policy.json').read_text(encoding='utf-8'))
    historical=config['historical_profiles'].get(name) == change
    manifests=profile.get('workflow_manifest_paths')
    if sample or (historical and manifests is None):
        return
    scope=profile.get('workflow_scope')
    if scope not in ('new-application','new-pipeline','legacy-maintenance') or not isinstance(manifests,list) or not manifests:
        raise ValueError('New profiles require workflow_scope and workflow_manifest_paths')
    if str(VERIFIER) not in sys.path:
        sys.path.insert(0,str(VERIFIER))
    from integrations.visual_workflow.policy import verify_public_view, verify_future_defaults
    covered=set(profile['source_paths'])
    for relative in manifests:
        path=local_path(relative)
        data=json.loads(path.read_text(encoding='utf-8'))
        if data.get('scope') != scope or relative not in covered or verify_public_view(data,path.parent):
            raise ValueError('Workflow delivery manifest is missing, stale or outside the fixed profile')
        future = config.get('pre_graph_defaults_profiles', {}).get(name) != change
        if future and verify_future_defaults(data,path.parent):
            raise ValueError('Graphical inspection or coding-delegation defaults are missing or stale')
        references=[data.get('n8n_export'),data.get('dify_export')]
        if scope != 'legacy-maintenance':
            references += [data['public_view']['snapshot'],data['public_view']['verification']]
            if future:
                references += [data['inspection_view']['graph'],data['inspection_view']['verification']]
        for reference in references:
            if reference is None:
                continue
            file=(path.parent/reference).resolve()
            if not file.is_relative_to(ROOT.resolve()) or file.relative_to(ROOT.resolve()).as_posix() not in covered:
                raise ValueError('Workflow delivery files must be hashed in the fixed profile')


def distribution_digest(dist: Path) -> str:
    dist = dist.resolve()
    members = sorted(p for p in dist.rglob('*') if p.is_file())
    if not members or len(members) > 1000:
        raise ValueError('Unexpected upstream distribution file count')
    total_bytes = 0
    tree = hashlib.sha256()
    for path in members:
        resolved = path.resolve()
        if not resolved.is_relative_to(dist) or path.is_symlink():
            raise ValueError('Upstream distribution path escaped')
        total_bytes += resolved.stat().st_size
        if total_bytes > 10_000_000:
            raise ValueError('Upstream distribution exceeds bounded input size')
        relative = path.relative_to(dist).as_posix().encode('utf-8')
        tree.update(len(relative).to_bytes(4, 'big'))
        tree.update(relative)
        tree.update(hashlib.sha256(path.read_bytes()).digest())
    return tree.hexdigest()


def snapshot(profile: dict, workspace: Path, change: str, name: str | None = None) -> dict[str, str]:
    change_root = workspace / 'openspec/changes' / change
    if not change_root.is_dir():
        raise ValueError('Change does not exist')
    # The job's own inputs, read from the workspace.
    own = [local_path(p) for p in profile['source_paths'] + profile['test_paths']]
    own += [workspace / 'openspec/config.yaml']
    own += [p for p in change_root.rglob('*') if p.is_file()]
    # The shared verifier, read from VERIFIER: in a pinned run this is the job's immutable copy,
    # so updating the repository's shared files cannot stale in-flight evidence.
    shared = [HOME / 'gate.py', HOME / 'workflow_delivery_policy.json', VERIFIER / 'integrations/visual_workflow/policy.py',
              VERIFIER / 'integrations/visual_workflow/viewer.py', HOME / 'unittest_runner.py', HOME / 'tools/package.json',
              HOME / 'tools/package-lock.json']
    shared += [p for p in (PACKAGE / 'schemas/spec-driven').rglob('*') if p.is_file()]
    shared += [PACKAGE / 'package.json', PACKAGE / 'bin/openspec.js']
    if len(own) + len(shared) > 250:
        raise ValueError('Change exceeds the bounded verification scope')
    result = {}
    for base, paths in ((ROOT.resolve(), own), (VERIFIER, shared)):
        for path in paths:
            resolved = path.resolve()
            if not resolved.is_relative_to(base) or not resolved.is_file():
                raise ValueError('Verification input escaped or disappeared')
            if resolved.stat().st_size > 5_000_000:
                raise ValueError('Verification input exceeds size limit')
            result[resolved.relative_to(base).as_posix()] = hashlib.sha256(resolved.read_bytes()).hexdigest()
    # profiles.json is shared by every session: bind only this job's own entry, so that adding or
    # editing an unrelated profile does not invalidate other in-flight evidence.
    entry = json.dumps(profile, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    result['dev_harness/profiles.json#' + (name or profile['change'])] = hashlib.sha256(entry.encode('utf-8')).hexdigest()
    # Actual upstream executable modules, not merely the small launcher. Bound
    # this single dependency directory; never enumerate unrelated node_modules.
    dist = (PACKAGE / 'dist').resolve()
    if not dist.is_relative_to(VERIFIER):
        raise ValueError('Upstream distribution escaped the verifier')
    result[dist.relative_to(VERIFIER).as_posix()] = distribution_digest(dist)
    result['verifier-pin'] = verifier_digest()
    return dict(sorted(result.items()))


def verifier_digest() -> str:
    """Pin id of the verifier in use; a modified pin raises instead of producing evidence."""
    if PIN is not None:
        verifier_pins.verify(PIN)
        return PIN.name
    return verifier_pins.manifest(VERIFIER)[0]


def check(change: str, name: str, sample: bool = False) -> dict:
    profile, workspace = load_profile(name, change, sample)
    installed = json.loads((PACKAGE / 'package.json').read_text(encoding='utf-8'))['version']
    if installed != VERSION:
        raise ValueError('Installed OpenSpec version differs from the pinned version')
    before = snapshot(profile, workspace, change, name)
    code, validated = official(['validate', change, '--strict', '--json'], workspace)
    status_code, status = official(['status', '--change', change, '--json'], workspace)
    task_code, apply = official(['instructions', 'apply', '--change', change, '--json'], workspace)
    items = validated.get('items', [])
    valid = code == 0 and len(items) == 1 and items[0].get('id') == change and items[0].get('valid') is True
    planned = status_code == 0 and status.get('isPlanningComplete') is True
    tasks = apply.get('tasks', [])
    task_ready = (task_code == 0 and apply.get('taskTrackingConfigured') is True and bool(tasks)
                  and all(task.get('done') is True for task in tasks))
    verification = {'profile': name, 'executed': False, 'exit_code': None}
    if valid and planned and task_ready:
        if profile['runner'] == 'unittest':
            cwd = local_path(profile['cwd'])
            test_names = [local_path(p).relative_to(cwd).as_posix() for p in profile['test_paths']]
            argv = [sys.executable, str(HOME / 'unittest_runner.py'), *test_names]
        else:
            argv = [sys.executable, '-m', 'pytest', '-q', *profile['test_paths']]
        exit_code, stdout = command(argv, local_path(profile['cwd']), profile.get('timeout_seconds', 120))
        verification = {'profile': name, 'executed': True, 'exit_code': exit_code}
        if profile['runner'] == 'unittest':
            counts = json.loads(stdout)
            count = counts.get('tests_run')
            verification['tests_run'] = count
            if type(count) is not int or count < 1 or counts.get('successful') is not True:
                verification['exit_code'] = exit_code or 1
    after = snapshot(profile, workspace, change, name)
    unchanged = before == after
    passed = valid and planned and task_ready and verification['exit_code'] == 0 and unchanged
    return {'schema_version': 1, 'change': change, 'workspace': 'sample' if sample else 'repository',
            'upstream_version': installed, 'spec_valid': valid, 'planning_complete': planned,
            'tasks': {'total': len(tasks), 'complete': sum(t.get('done') is True for t in tasks),
                      'incomplete': sum(t.get('done') is not True for t in tasks)},
            'verification': verification, 'inputs_unchanged': unchanged,
            'status': 'passed' if passed else 'failed', 'artifact_hashes': before,
            'verifier': {'pin': before.get('verifier-pin'), 'pinned_copy': PIN is not None},
            'limits': 'This gate verifies the registered scope with the verifier named in verifier.pin. '
                      'Semantic acceptance and authorization require independent review.'}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--change', required=True)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--sample', action='store_true')
    parser.add_argument('--root', help='Workspace under verification (required when run from a verifier pin)')
    args = parser.parse_args(argv)
    global ROOT
    try:
        if args.root:
            ROOT = Path(args.root).resolve()
            if not ROOT.is_dir():
                raise ValueError('Workspace root does not exist')
        elif PIN is not None:
            raise ValueError('A pinned gate needs --root for the workspace under verification')
        report = check(args.change, args.profile, args.sample)
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as exc:
        report = {'schema_version': 1, 'status': 'failed', 'error_type': type(exc).__name__,
                  'message': 'Development verification unavailable or invalid; no success evidence was produced.'}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'passed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
