"""Run exactly the requested unittest files; zero tests is a failure."""
from __future__ import annotations
import contextlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest


def main(argv=None):
    paths = sys.argv[1:] if argv is None else argv
    if not paths:
        return 2
    sys.path.insert(0, str(Path.cwd()))
    suite = unittest.TestSuite()
    with contextlib.redirect_stdout(sys.stderr):
        for index, value in enumerate(paths):
            path = Path(value).resolve()
            if not path.is_file() or path.suffix != '.py':
                return 2
            spec = importlib.util.spec_from_file_location(f'fixed_test_{index}', path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        result = unittest.TextTestRunner(stream=sys.stderr).run(suite)
    successful = result.testsRun > 0 and result.wasSuccessful()
    print(json.dumps({'tests_run': result.testsRun, 'successful': successful}))
    return 0 if successful else 1


if __name__ == '__main__':
    raise SystemExit(main())
