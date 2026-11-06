"""Generate independent Fe conformance tests from pre-candidate hand fixtures."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
from hand_fixtures import CASES
from transport import CODES

ROOT = Path(__file__).resolve().parent
PIN = '3732fbe8a6e9d2ea3925d02d0e3a1478bc1e01d742c2be75d3ea7300c46c45f0'
COMPILER = None
PACKAGE = ROOT


def array(values):
    return '[' + ', '.join(map(str, values)) + ']'


def run(project, compiler, output):
    global ROOT, COMPILER
    ROOT = Path(output)
    COMPILER = Path(compiler)
    source = Path(project) / "src/lib.fe"
    core = source.read_bytes()
    assert hashlib.sha256(COMPILER.read_bytes()).hexdigest() == PIN
    generated = (PACKAGE / 'native_harness.template.fe').read_text()
    partitions = 0
    for name, data, limits, rows, error in CASES:
        flat = b''
        ends = []
        row_ends = []
        for row in rows:
            for field in row:
                flat += field
                ends.append(len(flat))
            row_ends.append(len(ends))
        assert len(flat) <= 128 and len(ends) <= 32 and len(row_ends) <= 16
        error_values = [0, 0, 0, 0] if error is None else [CODES[error[0]], *error[1:]]
        generated += '\n#[test]\nfn independent_' + name.replace('-', '_') + '() {\n'
        generated += '    independent_fixture(' + ', '.join([array(data), array(flat), array(ends), array(row_ends)]) + ',\n'
        generated += f'        Limits {{ field_bytes: {limits[0]}, raw_bytes: {limits[1]}, fields: {limits[2]} }}, '
        generated += ', '.join(map(str, error_values)) + ')\n}\n'
        partitions += 1 if not data else (1 << (len(data) - 1)) if len(data) <= 8 else len(data) + 1
    test_bytes = core + b'\n' + generated.encode()
    source_sha = hashlib.sha256(test_bytes).hexdigest()
    path = ROOT / ('native-frozen-' + source_sha[:16] + '.fe')
    if path.exists():
        assert path.read_bytes() == test_bytes
    else:
        path.write_bytes(test_bytes)
    receipt_path = ROOT / ('NATIVE_CONFORMANCE_' + source_sha[:16] + '.json')
    if receipt_path.exists():
        raise RuntimeError('Existing receipt must be preserved; no automatic repeat')
    command = [str(COMPILER), 'test', str(path), '--backend', 'native', '--jobs', '1',
               '--native-timeout-secs', '20', '--native-output-limit-kib', '64']
    start = time.monotonic()
    try:
        result = subprocess.run(command, cwd=ROOT, timeout=120, capture_output=True)
        stdout, stderr, exitcode = result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as error:
        stdout, stderr, exitcode = error.stdout or b'', error.stderr or b'', None
    log = ROOT / ('native-' + source_sha[:16] + '.log')
    log.write_bytes(stdout + stderr)
    receipt = {'scope': 'independent frozen hand cases, all short partitions, long single splits, empty chunks, terminal behavior',
               'core_source': str(source), 'core_sha256': hashlib.sha256(core).hexdigest(),
               'compiler_sha256': PIN, 'generated_source_sha256': source_sha,
               'hand_fixture_sha256': hashlib.sha256((PACKAGE / 'hand_fixtures.py').read_bytes()).hexdigest(),
               'hand_cases': len(CASES), 'partition_schedules': partitions,
               'command': command, 'exit_code': exitcode, 'wall_seconds': time.monotonic() - start,
               'result': 'PASS' if exitcode == 0 else 'FAIL', 'log': str(log)}
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    print((stdout + stderr).decode(errors='replace'))
    print(json.dumps(receipt, indent=2))
