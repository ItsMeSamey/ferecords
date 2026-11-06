"""Verify frozen expectations without rewriting the historical corpus."""
import csv
import hashlib
import io
import json
from pathlib import Path
from hand_fixtures import CASES, WRITER_CASES
from reference import Error, Limits, canonical, json_outcome, parse, projection, structural_corpus

PACKAGE = Path(__file__).resolve().parent


def run(output):
    corpus_bytes = (PACKAGE / 'frozen_corpus.json').read_bytes()
    assert hashlib.sha256(corpus_bytes).hexdigest() == '85da8df5c9a1fe48f61581991fa0753d7b5e00302a099864a41458fd6b7cb08a'
    frozen = json.loads(corpus_bytes)
    built = []
    for name, data, limits, rows, error in CASES:
        outcome = parse(data, Limits(*limits))
        assert outcome.rows == rows
        assert outcome.error == (None if error is None else Error(*error))
        built.append({'id': 'hand-' + name, 'input_hex': data.hex(), 'limits': list(limits), **json_outcome(outcome)})
    for rows, expected in WRITER_CASES:
        assert canonical(rows) == expected
        assert parse(expected).rows == rows
    for invalid in ([[]], [[b'\0']], [[b'a', b'\0']]):
        try:
            canonical(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError('invalid writer record accepted')
    assert projection([[b'a', b'b', b'c']], [2, 0, 2]) == [[b'c', b'a', b'c']]
    valid = 0
    for number, data in enumerate(structural_corpus(4)):
        outcome = parse(data)
        if outcome.error is None:
            rows = list(csv.reader(io.StringIO(data.decode('latin1'), newline=''), strict=True))
            expected = [[f.encode('latin1') for f in row] if row else [b''] for row in rows]
            assert outcome.rows == expected
            encoded = canonical(outcome.rows)
            actual = list(csv.reader(io.StringIO(encoded.decode('latin1'), newline=''), strict=True))
            assert [[f.encode('latin1') for f in row] for row in actual] == outcome.rows
            valid += 1
        built.append({'id': f'structural-{number}', 'input_hex': data.hex(), 'limits': [16384, 65536, 256], **json_outcome(outcome)})
    assert built == frozen
    report = {'result': 'PASS', 'hand_cases': len(CASES), 'writer_cases': len(WRITER_CASES),
              'corpus_cases': len(frozen), 'valid_python_csv_agreements': valid,
              'corpus_sha256': hashlib.sha256(corpus_bytes).hexdigest()}
    (Path(output) / 'REFERENCE.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS independent reference and frozen corpus', flush=True)
