# FeRecords 0.1 contract

This contract was fixed on 2026-11-06 with the independent reviewer before differential testing. It describes a strict byte dialect inspired by CSV. It does not promise general RFC 4180 or Unix CSV compatibility.

Comma separates fields. A quote can only open a field at its start. Inside a quoted field, two quotes represent one quote. Following a closing quote, only a comma, CRLF or EOF is accepted. CRLF outside quotes terminates a row. Bare CR and LF outside quotes are errors. Embedded CR and LF inside quotes are preserved. NUL is rejected everywhere; all other nonstructural byte values, including non-UTF-8 bytes, are preserved.

Empty input has no rows. CRLF has one row with one empty field. A trailing CRLF adds no row. Consecutive and trailing commas preserve empty fields. An optional final row terminator is accepted. EOF after a comma creates the final empty field. EOF within an open quoted field or after a pending CR fails.

Limits are decoded bytes per field, raw bytes per row and fields per row. The raw count includes commas, quotes and quoted CR/LF, and excludes the terminating CRLF. Configuration requires 1 <= fields <= 256 and 1 <= field_bytes <= raw_bytes <= 1048576. Defaults are 16384, 65536 and 256. Zero limits are invalid rather than an alternate empty-only mode.

All positions are zero-based. Errors refer to the first offending byte, with these explicit choices: CR followed by a non-LF reports that following byte; incomplete quote or CR at EOF reports the input length. A comma introducing a field beyond the count limit reports the comma and the new field index. Row-consumer failures are anchored at the completing LF, or EOF for an unterminated final row. Width errors use the actual count as field index; missing projection errors use the requested missing index. No callback occurs before the completing LF is consumed.

Error precedence for each byte is counter availability, NUL, pending CR mismatch, bare LF, invalid quote placement/invalid byte after close, raw row limit, then decoded field limit or field-count limit. CR outside quotes is provisionally excluded from raw accounting even if a later byte proves it invalid. A valid doubled quote consumes raw budget before decoded budget. The parser retains its first error exactly; all subsequent calls return it. After successful finish, repeated finish succeeds. Any feed after finish, even an empty one, creates a terminal Finished error. A bad input range is terminal and does not consume bytes.

`Parser::feed(input, start, length)` borrows a ByteBuffer and checks start <= len and length <= len - start before reading it. A synchronous RecordSink accepts each complete Record. Callbacks must finish reading that borrowed record before returning; parser storage is then reused. The sink can return a typed failure, which becomes the parser's terminal failure. `records_seen` counts successfully accepted records. `position` counts successful input bytes; an error's byte is not included. Call `release` exactly once when an owner is no longer needed.

The writer always quotes fields, doubles their embedded quotes and emits CRLF. It rejects zero-field records. Record storage is private. `Record::new` and `push_field` provide a checked constructor for independent writing: at most 256 fields and 1048576 decoded bytes total; checked ranges, NUL rejection and allocation failures leave the record unchanged. This constructor cap describes decoded storage, not encoded CSV length. Projection preserves order and duplicates. Missing selected fields and invalid selected data are checked before any bytes for that row are written. Sink failures can leave a partial row and are returned immediately. Writer errors use the caller's offset and row context plus the offending field.

Parse/write round trips preserve records only when the parser's limits admit the canonical encoded rows. Quoting increases raw length. Even an accepted input can have canonical output larger than its original raw budget, and a record near the hard cap can have canonical output too large for this version's parser. Canonicalization is not a byte identity operation.

`canonical_raw_size` computes the selected canonical raw size, excluding CRLF, as sum(2 + decoded field length + embedded quote count) plus one comma per gap. `write_selected_bounded` and `write_record_bounded` take the target Parser Limits and preflight the entire selected record. They validate configuration, selection, field count, decoded field sizes and encoded raw size before any output. A successful bounded write can be reparsed with those limits to recover the selected fields exactly, provided the receiving source and sink succeed. Insufficient encoded raw capacity returns RawLimit with field 0 (a whole-row budget); a decoded FieldLimit reports the original selected field index. FieldCount uses the selected count. Invalid configuration takes precedence, followed by malformed selection, field count, decoded field limits and encoded raw limit. These bounded APIs make capacity incompatibility an explicit failure; unrestricted write_record/write_selected and CLI select remain streaming serializers with no target-parser-budget promise.

| Code | Kind |
| --- | --- |
| 0 | Success |
| 2 | Config |
| 3 | Range |
| 4 | Finished |
| 5 | Nul |
| 6 | BareCr |
| 7 | BareLf |
| 8 | Quote |
| 9 | AfterQuote |
| 10 | Unclosed |
| 11 | FieldLimit |
| 12 | RawLimit |
| 13 | FieldCount |
| 14 | Overflow |
| 15 | Allocation |
| 16 | Output |
| 17 | Width |
| 18 | Missing |
| 19 | EmptyRecord |
| 20 | Input |
| 64 | CLI usage |

The native CLI owns duplicated stdin/stdout descriptors through Fe declarations of POSIX stdio functions. It uses ferror to distinguish a read failure from EOF. Pending input bytes are fed before a read failure is reported; finish is called only after EOF. Input failures use code 20, the accepted input-byte position, the count of accepted rows and field 0 as source-level context. Each byte write is checked, and output is flushed and closed before success. An earlier parser, input or output error takes precedence over a later close or flush failure. Validation does not open stdout. The default SIGPIPE behavior can terminate the process on a broken pipe. The library's feed/finish interface remains independent of this adapter.
