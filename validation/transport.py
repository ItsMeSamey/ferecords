"""Independent diagnostic transport decoder."""
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

