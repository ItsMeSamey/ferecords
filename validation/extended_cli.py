"""Independent extended CLI/capacity-boundary checks; no speed comparison."""
import hashlib
import json
from pathlib import Path
import random
import subprocess
import time
from transport import CODES, decode_transport
from reference import Limits, canonical, parse

ROOT = Path(__file__).resolve().parent


def encode(rows, force_quotes=False):
    def field(value):
        if force_quotes or any(byte in value for byte in (b',', b'"', b'\r', b'\n')):
            return b'"' + value.replace(b'"', b'""') + b'"'
        return value
    return b'\r\n'.join(b','.join(map(field, row)) for row in rows) + b'\r\n'


def run(project, output):
    global ROOT
    ROOT = Path(output)
    source = Path(project) / "build/bin/ferecords"
    binary = source.read_bytes()
    digest = hashlib.sha256(binary).hexdigest()
    snapshot = ROOT / ('candidate-' + digest[:16])
    if snapshot.exists():
        assert snapshot.read_bytes() == binary
    else:
        snapshot.write_bytes(binary)
        snapshot.chmod(0o700)
    report_path = ROOT / ('EXTENDED_CLI_' + digest[:16] + '.json')
    if report_path.exists():
        raise RuntimeError('Do not overwrite a previous test receipt')
    failures, results = [], []
    start = time.monotonic()

    def invoke(name, args, data, expected_status, expected_stdout=None, inspect_expected=None):
        response = subprocess.run([str(snapshot), *args], input=data, capture_output=True, timeout=10)
        passed = response.returncode == expected_status and response.stderr == b''
        if expected_stdout is not None:
            passed = passed and response.stdout == expected_stdout
        stats = None
        if inspect_expected is not None:
            expected = inspect_expected
            actual_rows, actual_error, stats = decode_transport(response.stdout)
            e = expected.error
            expected_error = None if e is None else [CODES[e.kind], e.offset, e.record, e.field]
            passed = passed and actual_rows == [[f.hex() for f in row] for row in expected.rows]
            passed = passed and actual_error == expected_error and stats[0] == len(expected.rows) and stats[3] == 2048
            chunk = int(args[1])
            input_capacity = max(32, 1 << (chunk - 1).bit_length())
            passed = passed and len(stats) == 5 and stats[4] == input_capacity
            if e is None:
                passed = passed and stats[1] == len(data)
        detail = {'name': name, 'args': args, 'input_bytes': len(data),
                  'input_sha256': hashlib.sha256(data).hexdigest(),
                  'exit': response.returncode, 'expected_exit': expected_status,
                  'stdout_bytes': len(response.stdout), 'stdout_sha256': hashlib.sha256(response.stdout).hexdigest(),
                  'stats': stats, 'pass': passed}
        results.append(detail)
        if not passed:
            failures.append({**detail, 'stdout_prefix_hex': response.stdout[:256].hex(),
                             'stderr_prefix_hex': response.stderr[:256].hex()})
        return response

    rng = random.Random(0xFE2026)
    parts = [b'', b'a', b'"', b'a,b', b'\r', b'\n', b'\r\n', b'\xff', b' ', b'\t', b'\x01']
    for number in range(96):
        width = rng.randrange(1, 9)
        rows = [[b''.join(rng.choice(parts) for _ in range(rng.randrange(0, 9)))
                 for _ in range(width)] for _ in range(rng.randrange(1, 6))]
        data = encode(rows, force_quotes=bool(number % 2))
        expected = parse(data)
        assert expected.rows == rows and expected.error is None
        for chunk in (1, 17, 4096):
            invoke(f'generated-{number}-inspect-{chunk}', ['inspect', str(chunk)], data, 0, inspect_expected=expected)
        columns = [width - 1, 0, width - 1]
        invoke(f'generated-{number}-projection', ['select', *map(str, columns)], data, 0,
               expected_stdout=canonical([[row[i] for i in columns] for row in rows]))
        invoke(f'generated-{number}-width', ['validate', str(width)], data, 0, expected_stdout=b'')
        mutated = data[:len(data) // 2] + b'\0' + data[len(data) // 2:]
        outcome = parse(mutated)
        assert outcome.error is not None
        invoke(f'generated-{number}-nul', ['inspect', '17'], mutated, CODES[outcome.error.kind], inspect_expected=outcome)

    boundary_inputs = [(f'field-{size}', b'a' * size) for size in (31, 32, 33, 63, 64, 65, 16384, 16385)]
    exact_raw = b','.join([b'a' * 16384] + [b'b' * 16383] * 3)
    assert len(exact_raw) == 65536
    boundary_inputs += [('raw-exact', exact_raw), ('raw-over', exact_raw + b','),
                        ('fields-256', b',' * 255), ('fields-257', b',' * 256)]
    for name, data in boundary_inputs:
        outcome = parse(data)
        code = 0 if outcome.error is None else CODES[outcome.error.kind]
        invoke(name, ['inspect', '4096'], data, code, inspect_expected=outcome)
    expanded = canonical(parse(exact_raw).rows)
    assert parse(expanded).error.kind == 'RawLimit'
    invoke('canonical-expansion-default-limit', ['inspect', '4096'], expanded, 12, inspect_expected=parse(expanded))
    invoke('canonical-expansion-larger-budget', ['inspect', '4096', '16384', '65544', '256'], expanded, 0,
           inspect_expected=parse(expanded, Limits(16384, 65544, 256)))

    invoke('projection-later-missing', ['select', '2', '0', '2'], b'a,b,c\r\nx,y\r\n', 18,
           expected_stdout=b'"c","a","c"\r\n')
    invoke('projection-later-syntax', ['select', '0'], b'a\r\n"x', 10, expected_stdout=b'"a"\r\n')
    invoke('width-mismatch', ['validate', '2'], b'a,b\r\nx\r\n', 17, expected_stdout=b'')
    invoke('leading-zero-number', ['validate', '0002'], b'a,b', 0, expected_stdout=b'')
    invoke('largest-index-missing', ['select', '18446744073709551615'], b'a', 18, expected_stdout=b'')
    invalid = [[], ['select'], ['select', '-1'], ['select', '+1'], ['select', '1x'],
               ['select', '18446744073709551616'], ['validate', '0'], ['validate', '257'],
               ['validate', '1', '2'], ['inspect', '0'], ['inspect', '4097'],
               ['inspect', '1', '1'], ['inspect', '1', '0', '1', '1'],
               ['unknown'], ['select', *['0'] * 257]]
    for number, args in enumerate(invalid):
        invoke(f'invalid-argv-{number}', args, b'', 64, expected_stdout=b'')
    help_response = invoke('help', ['--help'], b'', 0)
    help_text = help_response.stdout.decode('ascii')
    required_help = ['strict CRLF', 'zero-based', 'duplicates', '65536', '16384', '256', '64', 'inspect', 'EOF', 'flush']
    missing_help = [text for text in required_help if text not in help_text]
    if missing_help:
        failures.append({'name': 'help-content', 'missing': missing_help})
    (ROOT / ('help-' + digest[:16] + '.txt')).write_text(help_text)
    report = {'scope': 'independent generated records, canonical projection, boundaries and CLI usability',
              'binary_sha256': digest, 'executions': len(results), 'generated_valid_inputs': 96,
              'wall_seconds': time.monotonic() - start, 'result': 'FAIL' if failures else 'PASS',
              'failures': failures, 'checks': results}
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'checks'}, indent=2))
