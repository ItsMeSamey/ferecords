"""Run the independent near-limit bounded writer contract checks once per source."""
from pathlib import Path
import hashlib
import json
import subprocess
import time

ROOT = Path(__file__).resolve().parent
PIN = '3732fbe8a6e9d2ea3925d02d0e3a1478bc1e01d742c2be75d3ea7300c46c45f0'
COMPILER = None
PACKAGE = ROOT


def run(project, compiler, output):
    global ROOT, COMPILER
    ROOT = Path(output)
    COMPILER = Path(compiler)
    core = (Path(project) / "src/lib.fe").read_bytes()
    checks = (PACKAGE / "bounded_writer.fe").read_bytes()
    assert hashlib.sha256(COMPILER.read_bytes()).hexdigest() == PIN
    combined = core + b'\n' + checks
    digest = hashlib.sha256(combined).hexdigest()
    source = ROOT / ('bounded-frozen-' + digest[:16] + '.fe')
    receipt_path = ROOT / ('BOUNDED_WRITER_' + digest[:16] + '.json')
    if receipt_path.exists():
        raise RuntimeError('Preserve prior receipt; no automatic rerun')
    if source.exists():
        assert source.read_bytes() == combined
    else:
        source.write_bytes(combined)
    command = [str(COMPILER), 'test', str(source), '--backend', 'native', '--jobs', '1',
               '--native-timeout-secs', '20', '--native-output-limit-kib', '64']
    start = time.monotonic()
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=120)
        code, stdout, stderr = result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as error:
        code, stdout, stderr = None, error.stdout or b'', error.stderr or b''
    log = ROOT / ('bounded-' + digest[:16] + '.log')
    log.write_bytes(stdout + stderr)
    receipt = {'scope': 'independent canonical output preflight and reparsing at exact/over 1MiB budget',
               'core_sha256': hashlib.sha256(core).hexdigest(),
               'checks_sha256': hashlib.sha256(checks).hexdigest(),
               'generated_sha256': digest, 'compiler_sha256': PIN,
               'command': command, 'exit_code': code, 'wall_seconds': time.monotonic() - start,
               'log': str(log), 'result': 'PASS' if code == 0 else 'FAIL'}
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    print((stdout + stderr).decode(errors='replace'))
    print(json.dumps(receipt, indent=2))
