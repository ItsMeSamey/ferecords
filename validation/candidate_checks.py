"""Independent black-box native parser checks against the frozen corpus."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "build/bin/ferecords"
CODES = {'InvalidConfig': 2, 'Range': 3, 'Finished': 4, 'Nul': 5,
         'BareCr': 6, 'BareLf': 7, 'QuoteInBare': 8, 'AfterQuote': 9,
         'UnterminatedQuote': 10, 'FieldLimit': 11, 'RawLimit': 12,
         'FieldCount': 13, 'Overflow': 14, 'Allocation': 15, 'Output': 16,
         'Width': 17, 'Missing': 18, 'EmptyRecord': 19}


def decode_transport(stdout):
    rows, error, stats = [], None, None
    for line in stdout.decode('ascii').splitlines():
        tokens = line.split()
        if tokens[0] == 'R':
            count = int(tokens[1])
            fields = ['' if token == '-' else token for token in tokens[2:]]
            if len(fields) != count:
                raise ValueError(('bad row count', line))
            for field in fields:
                bytes.fromhex(field)
            rows.append(fields)
        elif tokens[0] == 'E':
            if error is not None:
                raise ValueError('duplicate errors')
            error = list(map(int, tokens[1:]))
        elif tokens[0] == 'S':
            if stats is not None:
                raise ValueError('duplicate stats')
            stats = list(map(int, tokens[1:]))
        else:
            raise ValueError(('unknown transport line', line))
    return rows, error, stats


def run(project, output):
    global ROOT, SOURCE
    ROOT = Path(output)
    SOURCE = Path(project) / "build/bin/ferecords"
    started = time.monotonic()
    binary_bytes = SOURCE.read_bytes()
    binary_sha = hashlib.sha256(binary_bytes).hexdigest()
    snapshot = ROOT / ('candidate-' + binary_sha[:16])
    if snapshot.exists():
        assert snapshot.read_bytes() == binary_bytes
    else:
        snapshot.write_bytes(binary_bytes)
        snapshot.chmod(0o700)
    corpus_bytes = (Path(__file__).resolve().parent / 'frozen_corpus.json').read_bytes()
    corpus = json.loads(corpus_bytes)
    failures = []
    executions = 0
    for case in corpus:
        data = bytes.fromhex(case['input_hex'])
        error = case['error']
        expected_error = None if error is None else [CODES[error['kind']], error['offset'], error['record'], error['field']]
        for chunk in sorted({1, 2, 3, 7, 4096}):
            command = [str(snapshot), 'inspect', str(chunk), *map(str, case['limits'])]
            result = subprocess.run(command, input=data, capture_output=True, timeout=5)
            executions += 1
            try:
                rows, actual_error, stats = decode_transport(result.stdout)
                valid = (rows == case['rows_hex'] and actual_error == expected_error
                         and not result.stderr and stats is not None
                         and stats[0] == len(case['rows_hex']) and stats[3] == 2048)
                if error is None:
                    valid = valid and stats[1] == len(data) and result.returncode == 0
                else:
                    valid = valid and result.returncode == expected_error[0]
            except Exception as problem:
                valid = False
                rows, actual_error, stats = None, repr(problem), None
            if error is not None and error['kind'] == 'InvalidConfig':
                valid = result.returncode == 64 and result.stdout == b'' and result.stderr == b''
            if not valid:
                failures.append({'case': case['id'], 'input_hex': data.hex(), 'limits': case['limits'],
                                 'chunk': chunk, 'expected_rows': case['rows_hex'],
                                 'expected_error': expected_error, 'actual_rows': rows,
                                 'actual_error': actual_error, 'stats': stats,
                                 'exit': result.returncode, 'stdout_hex': result.stdout.hex(),
                                 'stderr_hex': result.stderr.hex()})
    report = {'scope': 'independent native parser/corpus fixed-chunk differential',
              'binary_source': str(SOURCE), 'binary_snapshot': str(snapshot),
              'binary_sha256': binary_sha, 'corpus_sha256': hashlib.sha256(corpus_bytes).hexdigest(),
              'cases': len(corpus), 'executions': executions,
              'configuration_cases_are_cli_usage_checks': True, 'chunks': [1, 2, 3, 7, 4096],
              'elapsed_seconds': time.monotonic() - started,
              'result': 'FAIL' if failures else 'PASS', 'failures': failures}
    path = ROOT / ('CANDIDATE_DIFFERENTIAL_' + binary_sha[:16] + '.json')
    if path.exists():
        raise RuntimeError('Preserve old report; choose a new attempt suffix')
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'failures'}, indent=2))
    print(json.dumps({'failure_count': len(failures), 'first_failures': failures[:8]}, indent=2))
