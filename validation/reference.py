"""Independent whole-input grammar oracle for the frozen FeRecords byte dialect.

This is test support, not code called by the Fe product. It parses fields using
lookahead rather than implementing the candidate's streaming state transitions.
"""
from dataclasses import dataclass
from itertools import product


@dataclass(frozen=True)
class Limits:
    field: int = 16384
    raw: int = 65536
    fields: int = 256


@dataclass(frozen=True)
class Error:
    kind: str
    offset: int
    record: int
    field: int


@dataclass
class Outcome:
    rows: list[list[bytes]]
    error: Error | None


class Rejected(Exception):
    def __init__(self, error):
        self.error = error


def parse(data: bytes, limits=Limits()) -> Outcome:
    rows = []
    index = 0
    field_index = 0
    raw = 0

    def reject(kind, offset, field=None):
        raise Rejected(Error(kind, offset, len(rows), field_index if field is None else field))

    def charge(offset):
        nonlocal raw
        if raw == limits.raw:
            reject('RawLimit', offset)
        raw += 1

    def append(field, byte, offset):
        if len(field) == limits.field:
            reject('FieldLimit', offset)
        field.append(byte)

    try:
        if not (1 <= limits.fields <= 256 and 1 <= limits.raw <= 1048576
                and 1 <= limits.field <= limits.raw):
            reject('InvalidConfig', 0, 0)
        while index < len(data):
            fields = []
            raw = 0
            field_index = 0
            while True:
                decoded = bytearray()
                if index < len(data) and data[index] == 34:
                    charge(index)
                    index += 1
                    while True:
                        if index == len(data):
                            reject('UnterminatedQuote', index)
                        byte = data[index]
                        if byte == 0:
                            reject('Nul', index)
                        charge(index)
                        index += 1
                        if byte != 34:
                            append(decoded, byte, index - 1)
                            continue
                        if index < len(data) and data[index] == 34:
                            charge(index)
                            append(decoded, 34, index)
                            index += 1
                            continue
                        break
                    if index < len(data) and data[index] not in (44, 13):
                        if data[index] == 0:
                            reject('Nul', index)
                        if data[index] == 10:
                            reject('BareLf', index)
                        reject('AfterQuote', index)
                else:
                    while index < len(data) and data[index] not in (44, 13):
                        byte = data[index]
                        if byte == 0:
                            reject('Nul', index)
                        if byte == 10:
                            reject('BareLf', index)
                        if byte == 34:
                            reject('QuoteInBare', index)
                        charge(index)
                        append(decoded, byte, index)
                        index += 1
                fields.append(bytes(decoded))
                if index == len(data):
                    rows.append(fields)
                    break
                if data[index] == 44:
                    charge(index)
                    if len(fields) == limits.fields:
                        reject('FieldCount', index, len(fields))
                    index += 1
                    field_index += 1
                    continue
                # CR outside quotes is never charged to the raw record budget.
                index += 1
                if index == len(data):
                    reject('BareCr', index)
                if data[index] == 0:
                    reject('Nul', index)
                if data[index] != 10:
                    reject('BareCr', index)
                index += 1
                rows.append(fields)
                break
        return Outcome(rows, None)
    except Rejected as rejected:
        return Outcome(rows, rejected.error)


def canonical(rows: list[list[bytes]]) -> bytes:
    result = bytearray()
    for row in rows:
        if not row:
            raise ValueError('zero-field record')
        if any(b'\x00' in field for field in row):
            raise ValueError('NUL field')
        result += b','.join(b'"' + field.replace(b'"', b'""') + b'"' for field in row)
        result += b'\r\n'
    return bytes(result)


def projection(rows, indices):
    if not indices or any(i < 0 for i in indices):
        raise ValueError('nonempty nonnegative projection required')
    output = []
    for row in rows:
        if any(i >= len(row) for i in indices):
            raise IndexError('missing selected field')
        output.append([row[i] for i in indices])
    return output


def structural_corpus(max_length=4):
    alphabet = (97, 44, 34, 13, 10, 0)
    for length in range(max_length + 1):
        for values in product(alphabet, repeat=length):
            yield bytes(values)


def all_partitions(data):
    if not data:
        yield [b'']
        return
    for mask in range(1 << (len(data) - 1)):
        starts = [0] + [i + 1 for i in range(len(data) - 1) if mask & (1 << i)]
        ends = starts[1:] + [len(data)]
        yield [data[start:end] for start, end in zip(starts, ends)]


def json_outcome(outcome):
    return {'rows_hex': [[f.hex() for f in row] for row in outcome.rows],
            'error': None if outcome.error is None else vars(outcome.error)}
