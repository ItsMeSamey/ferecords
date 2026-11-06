"""Ordinary Linux stream failures: read error, deferred output error, and pipe close."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import tty


def run(project, output):
    output = Path(output)
    source = Path(project) / 'build/bin/ferecords'
    binary = source.read_bytes()
    digest = hashlib.sha256(binary).hexdigest()
    executable = output / ('io-candidate-' + digest[:16])
    executable.write_bytes(binary)
    executable.chmod(0o700)
    checks = []

    def record(name, response, statuses, expected_stdout=None):
        passed = response.returncode in statuses and response.stderr == b''
        if expected_stdout is not None:
            passed = passed and response.stdout == expected_stdout
        checks.append({'name': name, 'exit': response.returncode, 'accepted_exit_codes': list(statuses),
                       'stdout_bytes': len(response.stdout or b''),
                       'stdout_sha256': hashlib.sha256(response.stdout or b'').hexdigest(),
                       'pass': passed})

    for name, args, data, expected in [
        ('clean-empty-input', ['validate'], b'', b''),
        ('clean-pipe-projection', ['select', '1', '0', '1'], b'a,"b,c"\r\n', b'"b,c","a","b,c"\r\n'),
    ]:
        response = subprocess.run([str(executable), *args], input=data, capture_output=True, timeout=5)
        record(name, response, {0}, expected)
    directory = os.open(output, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for command in ('validate', 'select'):
            args = [command] + (['0'] if command == 'select' else [])
            response = subprocess.run([str(executable), *args], stdin=directory, capture_output=True, timeout=5)
            record('directory-read-error-' + command, response, {20}, b'')
    finally:
        os.close(directory)

    # A private raw PTY drains written bytes and then reports EIO when its slave
    # closes. This tests a real read failure after complete rows plus an unfinished
    # final field, without touching any existing terminal or external service.
    master, slave = os.openpty()
    tty.setraw(slave)
    prefix = b'a\r\n' * 1500 + b'z'
    process = subprocess.Popen([str(executable), 'select', '0'], stdin=master,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    write_errors = []

    def feed():
        try:
            at = 0
            while at < len(prefix):
                at += os.write(slave, prefix[at:at + 1024])
        except Exception as error:
            write_errors.append(repr(error))
        finally:
            os.close(slave)

    writer = threading.Thread(target=feed, daemon=True)
    writer.start()
    try:
        stdout, stderr = process.communicate(timeout=5)
        writer.join(timeout=5)
        response = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
        record('read-error-after-complete-prefix-no-finish', response, {20}, b'"a"\r\n' * 1500)
        assert not writer.is_alive() and not write_errors, write_errors
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
        writer.join(timeout=5)

    for name, args, data, status in [
        ('deferred-output-failure', ['select', '0'], b'a', 16),
        ('help-flush-failure', ['--help'], b'', 16),
        ('syntax-error-precedes-final-flush-failure', ['select', '0'], b'a\r\n"bad', 10),
        ('missing-column-precedes-final-flush-failure', ['select', '1'], b'a,b\r\nx\r\n', 18),
    ]:
        with open('/dev/full', 'wb', buffering=0) as full:
            response = subprocess.run([str(executable), *args], input=data, stdout=full,
                                      stderr=subprocess.PIPE, timeout=5)
        record(name, response, {status})
    read_fd, write_fd = os.pipe()
    os.close(read_fd)
    try:
        response = subprocess.run([str(executable), 'select', '0'], input=b'a',
                                  stdout=write_fd, stderr=subprocess.PIPE, timeout=5)
        record('downstream-pipe-closed', response, {16, -signal.SIGPIPE})
    finally:
        os.close(write_fd)
    report = {'scope': 'Linux x86_64 ordinary owned-stream error behavior, no durability or host-OOM proof',
              'binary_sha256': digest, 'result': 'PASS' if all(c['pass'] for c in checks) else 'FAIL',
              'checks': checks}
    (output / 'HOST_IO.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)
    return report
