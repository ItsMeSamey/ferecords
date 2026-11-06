#!/usr/bin/env python3
"""Check bounded retained capacities on fixed 1k/100k native CSV streams.

Input is generated in small batches and output is consumed one line at a time.
This measures exposed capacities, not throughput or complete process memory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time
from datetime import datetime, timezone

RECORD = b'a,"b,\r\n""",\xff\r\n'
EXPECTED_ROW = b'R 3 61 622c0d0a22 ff\n'
COUNTS = (1_000, 100_000)


def digest(path: Path) -> str:
    state = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(65536), b''):
            state.update(block)
    return state.hexdigest()


def sample_process(pid: int) -> tuple[int, int]:
    try:
        fields = {}
        for line in Path(f'/proc/{pid}/status').read_text().splitlines():
            name, _, value = line.partition(':')
            if name in ('VmRSS', 'VmHWM'):
                fields[name] = int(value.split()[0]) * 1024
        return fields.get('VmRSS', 0), fields.get('VmHWM', 0)
    except (FileNotFoundError, ProcessLookupError):
        return 0, 0


def check(executable: Path, count: int) -> dict:
    argv = [str(executable), 'inspect', '4096']
    started = time.monotonic()
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)
    assert process.stdin is not None and process.stdout is not None
    feed_errors = []
    input_hash = hashlib.sha256()
    output_hash = hashlib.sha256()
    timed_out = threading.Event()

    def feed() -> None:
        try:
            remaining = count
            while remaining:
                amount = min(remaining, 64)
                block = RECORD * amount
                process.stdin.write(block)
                input_hash.update(block)
                remaining -= amount
            process.stdin.close()
        except Exception as error:
            feed_errors.append(repr(error))

    def expire() -> None:
        timed_out.set()
        process.kill()

    writer = threading.Thread(target=feed, name='bounded-corpus-feeder', daemon=True)
    watchdog = threading.Timer(30, expire)
    watchdog.daemon = True
    writer.start()
    watchdog.start()
    rows = 0
    stats = None
    sampled_rss = sampled_hwm = 0
    try:
        while True:
            # A fixed bound prevents the test driver retaining an unexpected large line.
            line = process.stdout.readline(1025)
            if not line:
                break
            if len(line) > 1024 or not line.endswith(b'\n'):
                raise AssertionError('oversized or truncated inspect line')
            output_hash.update(line)
            if line.startswith(b'R '):
                if stats is not None or line != EXPECTED_ROW:
                    raise AssertionError(f'unexpected record line at row {rows}: {line!r}')
                rows += 1
                if rows > count:
                    raise AssertionError('unexpected extra record')
            elif line.startswith(b'S '):
                if stats is not None:
                    raise AssertionError('duplicate storage summary')
                values = tuple(map(int, line.split()[1:]))
                if len(values) != 5:
                    raise AssertionError(f'expected five storage values, got {values!r}')
                stats = values
            else:
                raise AssertionError(f'unexpected inspect line: {line!r}')
            if rows % 1024 == 0 or stats is not None:
                rss, hwm = sample_process(process.pid)
                sampled_rss = max(sampled_rss, rss)
                sampled_hwm = max(sampled_hwm, hwm)
        returncode = process.wait(timeout=5)
        writer.join(timeout=5)
        if timed_out.is_set() or writer.is_alive() or feed_errors:
            raise AssertionError(f'feeder/timeout failure: {feed_errors!r}')
        if returncode != 0:
            raise AssertionError(f'native exit status {returncode}')
        expected_stats = (count, len(RECORD) * count, 32, 2048, 4096)
        if rows != count or stats != expected_stats:
            raise AssertionError(f'rows/stats mismatch: {rows}, {stats}, expected {expected_stats}')
        return {
            'argv': argv,
            'record_count': rows,
            'input_bytes': len(RECORD) * count,
            'input_sha256': input_hash.hexdigest(),
            'inspect_output_sha256': output_hash.hexdigest(),
            'record_buffer_capacity_bytes': stats[2],
            'field_offsets_logical_bytes': stats[3],
            'input_buffer_capacity_bytes': stats[4],
            'sampled_process_rss_bytes': sampled_rss or None,
            'last_observed_process_high_water_bytes': sampled_hwm or None,
            'wall_seconds_descriptive_only': time.monotonic() - started,
            'returncode': returncode,
        }
    finally:
        watchdog.cancel()
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()
        if not process.stdin.closed:
            process.stdin.close()
        writer.join(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=Path(__file__).resolve().parents[1] / 'build/bin/ferecords')
    parser.add_argument('--report', type=Path, default=Path(__file__).resolve().parents[1] / 'build/storage-report.json')
    args = parser.parse_args()
    executable = args.binary.resolve(strict=True)
    result = {
        'utc': datetime.now(timezone.utc).isoformat(),
        'test_sha256': digest(Path(__file__)),
        'binary_sha256': digest(executable),
        'record_hex': RECORD.hex(),
        'expected_inspect_row': EXPECTED_ROW.decode('ascii').rstrip('\n'),
        'checks': [check(executable, count) for count in COUNTS],
        'scope': 'Both fixed corpora must expose the same record and input buffer capacities. Field offsets are 256 logical u64 entries. No past rows are retained by this test driver or the parser.',
        'limitations': 'Capacities and logical metadata exclude fixed scalar state, stack/ABI layout, CLI column arrays, libc buffers and allocator overhead. RSS samples are descriptive, may miss peaks, and are not the constant-storage proof. Wall times are not a speed comparison.',
    }
    result['passed'] = True
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(f'PASS: 1,000 and 100,000 exact records; record capacity 32, offset metadata 2048, input capacity 4096. Receipt: {args.report}')


if __name__ == '__main__':
    main()
