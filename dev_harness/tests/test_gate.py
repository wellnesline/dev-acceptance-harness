from __future__ import annotations

import importlib.util
from pathlib import Path
import pytest
import json
import subprocess
import sys

MODULE = Path(__file__).resolve().parents[1] / 'gate.py'
SPEC = importlib.util.spec_from_file_location('development_gate', MODULE)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


def setup_check(monkeypatch, *, done=True, valid=True, test_exit=0, changed=False):
    profile = {'runner': 'pytest', 'test_paths': ['dev_harness/tests/test_gate.py'], 'cwd': '.'}
    monkeypatch.setattr(gate, 'load_profile', lambda *a: (profile, gate.ROOT))
    snapshots = iter([{'code': 'before'}, {'code': 'after' if changed else 'before'}])
    monkeypatch.setattr(gate, 'snapshot', lambda *a: next(snapshots))
    responses = iter([(0, {'items': [{'id': 'example', 'valid': valid}]}),
                      (0, {'isPlanningComplete': True}),
                      (0, {'taskTrackingConfigured': True, 'tasks': [{'done': done}]})])
    monkeypatch.setattr(gate, 'official', lambda *a: next(responses))
    calls = []
    def command(argv, *args):
        calls.append(argv)
        return test_exit, 'internal output must not appear in report'
    monkeypatch.setattr(gate, 'command', command)
    return calls


def test_pending_tasks_block_execution(monkeypatch):
    calls = setup_check(monkeypatch, done=False)
    report = gate.check('example', 'example')
    assert report['status'] == 'failed' and not calls
    assert report['tasks']['incomplete'] == 1


def test_invalid_spec_blocks_execution(monkeypatch):
    calls = setup_check(monkeypatch, valid=False)
    assert gate.check('example', 'example')['status'] == 'failed'
    assert not calls


def test_test_failure_cannot_be_success(monkeypatch):
    setup_check(monkeypatch, test_exit=1)
    assert gate.check('example', 'example')['status'] == 'failed'


def test_source_change_during_verification_rejected(monkeypatch):
    setup_check(monkeypatch, changed=True)
    report = gate.check('example', 'example')
    assert report['status'] == 'failed' and report['inputs_unchanged'] is False


def test_success_requires_all_conditions(monkeypatch):
    calls = setup_check(monkeypatch)
    report = gate.check('example', 'example')
    assert report['status'] == 'passed' and len(calls) == 1
    assert report['verification']['profile'] == 'example'
    assert 'internal output' not in str(report)


@pytest.mark.parametrize('name,change,sample', [
    ('sample-artifact-path', 'development-harness', False),
    ('sample-artifact-path', 'safe-relative-output', False),
    ('unknown', 'safe-relative-output', True),
    ('sample-artifact-path', '../safe-relative-output', True),
])
def test_profile_bound_to_change_and_workspace(name, change, sample):
    with pytest.raises(ValueError):
        gate.load_profile(name, change, sample)


@pytest.mark.parametrize('path', ['../outside', 'C:/Windows/win.ini'])
def test_paths_cannot_escape_repository(path):
    with pytest.raises(ValueError):
        gate.local_path(path)


def test_snapshot_includes_spec_code_tests_and_upstream_lock():
    profile, workspace = gate.load_profile('sample-artifact-path', 'safe-relative-output', True)
    evidence = gate.snapshot(profile, workspace, 'safe-relative-output')
    for path in ['dev_harness/project/artifact_path.py',
                 'dev_harness/project/tests/test_artifact_path.py',
                 'dev_harness/tools/package-lock.json',
                 'dev_harness/project/openspec/changes/safe-relative-output/tasks.md']:
        assert len(evidence[path]) == 64
    assert len(evidence['dev_harness/tools/node_modules/@fission-ai/openspec/dist']) == 64


def test_upstream_dist_tampering_changes_digest(tmp_path):
    entry = tmp_path / 'main.js'
    entry.write_text('original')
    before = gate.distribution_digest(tmp_path)
    entry.write_text('tampered')
    assert gate.distribution_digest(tmp_path) != before


def test_zero_unittests_fail_in_real_subprocess(tmp_path):
    empty = tmp_path / 'test_empty.py'
    empty.write_text('# No actual cases\n')
    proc = subprocess.run([sys.executable, str(gate.HOME / 'unittest_runner.py'), str(empty)],
                          capture_output=True, text=True, timeout=15)
    assert proc.returncode == 1
    assert json.loads(proc.stdout) == {'tests_run': 0, 'successful': False}
