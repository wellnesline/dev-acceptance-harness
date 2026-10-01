"""Project-local upstream OpenSpec entrypoint; never writes global integrations."""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {'new', 'status', 'instructions', 'validate', 'list', 'show', 'templates', 'schemas'}


def main():
    args = sys.argv[1:]
    sample = '--sample' in args
    if sample:
        args.remove('--sample')
    if not args or args[0] not in ALLOWED or (args[0] == 'new' and (len(args) < 2 or args[1] != 'change')):
        raise SystemExit('Use new change, status, instructions, validate, list, show, templates or schemas')
    if any(arg == '--store' or arg.startswith('--store=') for arg in args):
        raise SystemExit('Global stores are outside this local wrapper scope')
    node = shutil.which('node')
    cli = ROOT / 'dev_harness/tools/node_modules/@fission-ai/openspec/bin/openspec.js'
    if not node or not cli.is_file():
        raise SystemExit('Run npm.cmd ci --prefix dev_harness/tools --ignore-scripts --no-audit --no-fund first on Windows')
    env = {**os.environ, 'OPENSPEC_TELEMETRY': '0', 'DO_NOT_TRACK': '1', 'OPENSPEC_NO_UPDATE_CHECK': '1', 'CI': '1'}
    return subprocess.run([node, str(cli), *args], cwd=ROOT / 'dev_harness/project' if sample else ROOT, env=env).returncode


if __name__ == '__main__':
    raise SystemExit(main())
