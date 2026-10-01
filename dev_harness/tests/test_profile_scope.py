"""Unrelated profile edits must not invalidate other jobs; a job's own profile still binds its evidence."""
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'dev_harness'))
import gate  # noqa: E402
from ops_harness.workflow import WorkflowRuntime  # noqa: E402


def own_key(name):
    return 'dev_harness/profiles.json#' + name


def test_snapshot_binds_only_its_own_profile_entry():
    profile, workspace = gate.load_profile('sample-artifact-path', 'safe-relative-output', True)
    evidence = gate.snapshot(profile, workspace, 'safe-relative-output', 'sample-artifact-path')
    assert 'dev_harness/profiles.json' not in evidence
    canonical = json.dumps(profile, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    assert evidence[own_key('sample-artifact-path')] == hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    changed = copy.deepcopy(profile)
    changed['timeout_seconds'] = profile.get('timeout_seconds', 120) + 1
    assert gate.snapshot(changed, workspace, 'safe-relative-output', 'sample-artifact-path')[own_key('sample-artifact-path')] != evidence[own_key('sample-artifact-path')]


def test_check_reports_own_profile_key(monkeypatch):
    seen = []
    monkeypatch.setattr(gate, 'snapshot', lambda *a: seen.append(a) or {'k': 'v'})
    monkeypatch.setattr(gate, 'official', lambda *a: (1, {}))
    gate.check('safe-relative-output', 'sample-artifact-path', True)
    assert seen and all(call[3] == 'sample-artifact-path' for call in seen)


def _runtime_root(tmp_path):
    for relative in ('dev_harness/gate.py', 'dev_harness/unittest_runner.py', 'dev_harness/profiles.json',
                     'dev_harness/tools/package-lock.json', 'openspec/config.yaml', 'config/ops_harness.json'):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"v": 1}', encoding='utf-8')
    return tmp_path


def test_workflow_fingerprint_ignores_profile_registry_but_not_gate(tmp_path):
    root = _runtime_root(tmp_path)
    runtime = WorkflowRuntime(root, root / 'state')
    first = runtime.fingerprint()
    (root / 'dev_harness/profiles.json').write_text('{"profiles": {"someone-else": {}}}', encoding='utf-8')
    assert runtime.fingerprint() == first
    (root / 'dev_harness/gate.py').write_text('# changed gate', encoding='utf-8')
    assert runtime.fingerprint() != first
