#!/usr/bin/env python3
"""Run the packaged independent checks on the current project and pinned compiler."""
import argparse
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import time
import traceback

import bounded_cases
import candidate_checks
import extended_cli
import host_io_checks
import native_cases
import reference_check

PACKAGE = Path(__file__).resolve().parent
PROJECT = PACKAGE.parent
PIN = '3732fbe8a6e9d2ea3925d02d0e3a1478bc1e01d742c2be75d3ea7300c46c45f0'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', default=os.environ.get('FE'), help='External Fe 26.5.0 Linux x86_64 release; defaults to FE')
    args = parser.parse_args()
    if not args.compiler:
        parser.error('provide --compiler /path/to/fe or set FE')
    compiler = Path(args.compiler).expanduser().resolve(strict=True)
    if hashlib.sha256(compiler.read_bytes()).hexdigest() != PIN:
        parser.error('compiler checksum differs from the pinned release')
    output = PROJECT / 'build/validation-runs' / str(time.time_ns())
    output.mkdir(parents=True, exist_ok=False)
    report = {'result': 'RUNNING', 'compiler_sha256': PIN, 'stages': [],
              'core_sha256': hashlib.sha256((PROJECT / 'src/lib.fe').read_bytes()).hexdigest(),
              'cli_sha256': hashlib.sha256((PROJECT / 'cli/main.fe').read_bytes()).hexdigest()}
    started = time.monotonic()

    def stage(name, function):
        print('Running ' + name, flush=True)
        captured = io.StringIO()
        before = time.monotonic()
        try:
            with redirect_stdout(captured):
                function()
        finally:
            (output / (name + '.log')).write_text(captured.getvalue())
        report['stages'].append({'name': name, 'wall_seconds': time.monotonic() - before})

    def build():
        result = subprocess.run([os.sys.executable, str(PROJECT / 'build.py'), 'build', '--compiler', str(compiler)],
                                cwd=PROJECT, capture_output=True, timeout=150)
        print((result.stdout + result.stderr).decode(errors='replace'))
        if result.returncode:
            raise RuntimeError('current project build failed')
        report['binary_sha256'] = hashlib.sha256((PROJECT / 'build/bin/ferecords').read_bytes()).hexdigest()

    try:
        stage('build-current-source', build)
        stage('reference', lambda: reference_check.run(output))
        stage('parser-corpus', lambda: candidate_checks.run(PROJECT, output))
        stage('native-partitions', lambda: native_cases.run(PROJECT, compiler, output))
        stage('bounded-writer', lambda: bounded_cases.run(PROJECT, compiler, output))
        stage('extended-cli', lambda: extended_cli.run(PROJECT, output))
        stage('host-io', lambda: host_io_checks.run(PROJECT, output))
        receipts = sorted(output.glob('*.json'))
        for path in receipts:
            item = json.loads(path.read_text())
            if item.get('result') != 'PASS':
                raise AssertionError('failed receipt: ' + path.name)
        assert report['core_sha256'] == hashlib.sha256((PROJECT / 'src/lib.fe').read_bytes()).hexdigest()
        assert report['cli_sha256'] == hashlib.sha256((PROJECT / 'cli/main.fe').read_bytes()).hexdigest()
        assert report['binary_sha256'] == hashlib.sha256((PROJECT / 'build/bin/ferecords').read_bytes()).hexdigest()
        report['receipts'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in receipts}
        report['result'] = 'PASS'
    except Exception as error:
        report['result'] = 'FAIL'
        report['error'] = repr(error)
        (output / 'exception.log').write_text(traceback.format_exc())
    report['wall_seconds'] = time.monotonic() - started
    (output / 'VALIDATION.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['result'] + ': ' + str(output / 'VALIDATION.json'), flush=True)
    raise SystemExit(0 if report['result'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
