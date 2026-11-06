# FeRecords

FeRecords is a bounded streaming CSV reader and canonical writer in Fe, with a native command-line tool for validation and ordered column selection. It accepts a strict CRLF byte dialect, preserves multiline quoted fields and non-UTF-8 bytes, and reports the same rows and error positions regardless of chunk boundaries. LF-only row endings and NUL bytes are rejected.

Callers can consume or project quoted CSV without writing their own quote state machine. The baseline and prior preparation are disclosed in [PROVENANCE.md](PROVENANCE.md).

## Build and use

Native execution is verified on x86_64 Linux using Fe 26.5.0 (`3dab95f`), Python 3.10 or later and the system C linker. No additional packages are needed. Obtain the `fe_linux_amd64` asset from the [official v26.5.0 release](https://github.com/argotorg/fe/releases/tag/v26.5.0), keep it outside the project and set `FE` to its executable path. `build.py` verifies its exact release SHA256 before invoking it. Run these commands from the project root:

```sh
export FE=/absolute/path/to/fe_linux_amd64
python3 build.py build
build/bin/ferecords --help
printf 'id,name\r\n1,"Ada,\nA"\r\n' | build/bin/ferecords select 1 0 1
```

The output keeps the LF inside the quoted name and uses CRLF between records:

```csv
"name","id","name"
"Ada,
A","1","Ada,
A"
```

The expected compiler SHA256 is `3732fbe8a6e9d2ea3925d02d0e3a1478bc1e01d742c2be75d3ea7300c46c45f0`. The `--compiler` option overrides `FE`; a pinned `fe` on PATH is also accepted. The script uses the supplied compiler without downloading or installing anything.

Commands read stdin:

- `validate [WIDTH]` checks syntax and optionally requires 1 to 256 fields in every row. It emits no output.
- `select COLUMN...` writes canonical CSV for 1 to 256 zero-based column indices. Selection order and duplicates are preserved. A missing column fails before writing that row.
- `inspect [CHUNK [FIELD_LIMIT RAW_LIMIT FIELDS_LIMIT]]` emits diagnostic records and errors. Chunk size is 1 to 4096. Custom limits require the complete triple.

Successful commands exit 0. Usage errors exit 64. Format, limit and output errors use the codes in [CONTRACT.md](CONTRACT.md). `validate` and `select` keep errors off stdout; use `inspect` to see exact error positions. Earlier rows can already have been written before a later row fails.

Inspection rows are `R COUNT HEX...`, with `-` for an empty field. An error is `E CODE BYTE ROW FIELD`. After a parsing attempt, the final line is `S ROWS POSITION RECORD_CAPACITY OFFSET_BYTES INPUT_CAPACITY`; capacities are measured ByteBuffer capacities, while OFFSET_BYTES is the fixed logical 2048-byte field-offset array. Opening or writing the diagnostic stream can fail before these lines are available. Hex preserves otherwise unprintable bytes.

The CLI owns duplicate stdin/stdout descriptors through a native Fe POSIX stream adapter. It distinguishes read errors from EOF, checks byte writes and flushes and closes output before returning success. Input failures return 20; output failures return 16. An earlier parser, input or output error keeps its code if a later close or flush also fails. The default SIGPIPE behavior can terminate the process on a broken pipe. Applications using the pure library supply their own source and sink adapters.

## Library and ownership

`src/lib.fe` contains the complete library. `fe.toml` identifies the ingot. `cli/main.fe` consumes records through the RecordSink and ByteSink interfaces. `build.py` joins the library and native entry source into one standalone Fe compilation unit for the pinned compiler.

A caller constructs `Parser::new(default_limits())`, binds a mutable RecordSink effect, feeds borrowed ByteBuffers with checked start/length ranges, then calls `finish`. The sink receives a borrowed complete Record, completion byte position and row number. It can read fields with `field_count`, `field_len` and `byte_at`. The callback is synchronous; parser storage is cleared and reused after success. A sink failure becomes the parser's first terminal error.

To write records independently, construct `Record::new`, call `push_field` for each byte range and bind a mutable ByteSink effect. `write_record` writes all fields. `write_selected` takes up to 256 indices and preserves their order and repetitions. The writer validates selection before output, quotes every field and doubles quotes. All owned Parser, Record and input ByteBuffer values require an explicit `release` on every exit path. Tests and the CLI show these paths.

For output intended to be read by a parser with known limits, use `write_record_bounded` or `write_selected_bounded`. These functions take the target Limits and reject incompatible field counts, decoded lengths or canonical encoded size before writing any byte. Every successful bounded write can be parsed with those limits. `canonical_raw_size` exposes the exact encoded row size without writing it. The unrestricted functions and CLI select remain useful when the receiving program has different capacity limits.

The state machine uses Fe enums and typed error-first `Result<Failure, ()>`. A custom fallible ByteSink makes output failure part of the API; the stock Write trait returns no failure. Parser and record storage are private, and the external Record builder validates ranges, NUL bytes and capacities before mutation.

## Bounds and limitations

Defaults are 16384 decoded bytes per field, 65536 raw bytes per row and 256 fields. Configurable hard caps are 1048576 raw bytes and 256 fields. Raw size includes commas and quotes, excludes the terminating CRLF and includes embedded quoted CR/LF. A complete row is buffered so a missing projection column never causes silent omission or an incomplete semantic row. The implementation does not retain previous records.

The parser retains one ByteBuffer and 256 u64 field ends (2048 logical bytes), plus fixed state. ByteBuffer allocates at least 32 bytes and rounds growth to powers of two. For a raw bound R, record capacity is at most the next power of two of max(32, R), up to the 1 MiB hard cap. During growth, old and new allocations coexist; their sum is at most 1.5 times that rounded cap. These are payload bounds, not total allocator or process RSS bounds. The CLI adds a 4096-byte input buffer, two fixed 256-index configuration/provider arrays, fixed scalar state and host stdio buffers. The canonical writer streams output byte by byte and retains no growing output buffer. Its all-fields convenience function also constructs a fixed 256-index array.

Canonical quotes can make output larger than input. Parse/write round trips require sufficient raw capacity for the encoded output. Rows near the hard cap can produce canonical output that this version cannot parse under any supported raw setting. See the full contract for error precedence, terminal calls and exact EOF choices.

## Verification

```sh
python3 build.py check
python3 build.py test
python3 tests/cli.py
python3 tests/storage.py
python3 validation/run.py
```

The native suite checks fixed expectations, every split of selected fixtures, all partitions of a short quoted fixture, byte preservation, all EOF states, exact limits, sticky failures, checked ranges, record-builder rejection, canonical bytes, duplicate projection and deterministic sink failure at each output position. Counter-overflow tests inject boundary state. CLI tests exercise actual read and buffered-output failures. Allocator exhaustion is outside the test suite.

The included `validation/` directory contains the independently written whole-input reference, frozen corpus, chunk-partition tests and retained receipts. Its runner uses the same external compiler selected by `FE` or `--compiler`. Python's csv module checks valid inputs in the shared dialect; the strict reference defines malformed-input expectations. Test evidence and storage results are collected in [RESULTS.md](RESULTS.md).

## License and disclosure

Apache-2.0. Original implementation began November 6, 2026. Pre-window design notes, generic smoke, official API references, starter license/template reuse and AI assistance are listed in [PROVENANCE.md](PROVENANCE.md). The contest requires AI-assistance disclosure, tested results, a responsible human contact and the ability to explain the code.
