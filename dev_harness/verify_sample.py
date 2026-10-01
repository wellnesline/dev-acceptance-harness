"""Exercise installed upstream and the isolated example; restore all mutations."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / 'dev_harness/project'
CHANGE = SAMPLE / 'openspec/changes/safe-relative-output'


def run_gate():
    completed = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'dev_harness/gate.py'),
        '--sample', '--change', 'safe-relative-output', '--profile', 'sample-artifact-path'],
        cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=120)
    return completed.returncode, json.loads(completed.stdout)


def main():
    results = []
    cases = [
        ('invalid_spec', CHANGE / 'specs/artifact-path/spec.md',
         lambda text: text.replace('#### Scenario:', '### Scenario:'),
         lambda r: r.get('spec_valid') is False),
        ('pending_task', CHANGE / 'tasks.md',
         lambda text: text.replace('[x]', '[ ]', 1),
         lambda r: r.get('tasks', {}).get('incomplete') == 1 and r['verification']['executed'] is False),
        ('broken_implementation', SAMPLE / 'artifact_path.py',
         lambda text: 'def validate_artifact_path(value):\n    return value\n',
         lambda r: r.get('verification', {}).get('exit_code') not in (None, 0)),
    ]
    for name, path, mutate, expected in cases:
        original = path.read_bytes()
        try:
            path.write_text(mutate(original.decode('utf-8')), encoding='utf-8')
            code, report = run_gate()
            ok = code == 2 and report['status'] == 'failed' and expected(report)
            results.append({'case': name, 'expected_failure_observed': ok})
        finally:
            path.write_bytes(original)
    code, report = run_gate()
    results.append({'case': 'restored_valid_implementation', 'passed': code == 0 and report['status'] == 'passed'})
    success = all(row.get('expected_failure_observed', row.get('passed')) for row in results)
    print(json.dumps({'status': 'passed' if success else 'failed', 'cases': results}, indent=2))
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
