# Retained verification results, 2026-11-06

The current CLI binary SHA256 is `27146ff3e1ca3a3e6da4d6d7d5b4e19f7ea3132a9e608f8bfad711e0d41e4212`, built with the pinned Fe 26.5.0 compiler. The library source SHA256 is `8713bca3eedb4925f7689abdd177552049e83d753c34010bee03c9b8c5fc719a`.

Release testing found two I/O defects in the initial CLI: directory input and a deferred /dev/full output failure both returned success. The current CLI uses owned POSIX streams, reports those failures and preserves any earlier error. The initial binary `6ac565170dce1e6ec528a1244d4aac0d29eab63d0f996121608e18d1d875721a` and its receipts are identified as historical evidence. The parser and writer functions are unchanged; the library adds the Input error kind with code 20.

| Check | Result | Retained evidence |
| --- | --- | --- |
| Initial native library suite, before Input20 was added | 13 passed, 0 failed | `evidence/owner/test.log`, `evidence/owner/test-receipt.json` |
| Current native CLI | 44 explicit cases, 35 chunk comparisons and 15 actual I/O cases passed | `tests/cli.py`, `evidence/owner/cli-io-results.json` |
| Current independent frozen-corpus comparison | 8025 parser comparisons (1605 cases at 5 chunk sizes) and 30 CLI configuration checks passed | `validation/evidence/CANDIDATE_DIFFERENTIAL_27146ff3e1ca3a3e.json` |
| Current independent native partitions | 56 fixtures, 377 split/partition schedules passed, including all 6 invalid configurations | `validation/evidence/NATIVE_CONFORMANCE_02547bac55e9e933.json` |
| Current independent extended CLI | 611 executions passed, including near default limits, byte preservation and projection | `validation/evidence/EXTENDED_CLI_27146ff3e1ca3a3e.json` |
| Current independent bounded writer | 11 native tests passed, including exact 1 MiB encoded plain/quote-heavy round trips and next-over zero-output rejection | `validation/evidence/BOUNDED_WRITER_8af650fad0ddaf4a.json` |
| Current independent I/O | 10 checks passed, including a read failure after 1500 complete rows, deferred output failure and closed-pipe behavior | `validation/evidence/HOST_IO.json` |
| Current fixed-stream storage | Both exact streams passed with identical tracked storage | `tests/storage.py`, `evidence/owner/cli-io-storage-report.json` |

The initial 8055-execution frozen-corpus CLI run produced 8025 parser agreements and 30 mismatches: six invalid library configurations at five chunk sizes. The CLI rejected them as usage code 64 before invoking the parser, while the reference expected library Config code 2. The independent native harness directly tested those configurations and passed. The mismatch receipt and classification are included in the validation evidence.

The independent model and corpus were frozen before candidate comparison. The oracle used a whole-input grammar instead of reproducing the parser's streaming state machine. Its 56 hand parser fixtures and 6 exact writer cases were checked separately. Python csv agreed on 88 valid common-dialect structural inputs after explicit blank-row normalization; it was not used to decide strict malformed-input errors.

The native suite covers bytes and rows across chunk boundaries, all EOF states, syntax error offsets, raw/decoded/count limits, invalid ranges/configuration, terminal calls and counted once-only callback failure. Writer tests compare independent canonical bytes, fail the output sink at every byte position, verify ordered duplicates and check parse/write round trips. The bounded writer test checks exact encoded size and zero emitted bytes on incompatible raw, decoded, count or configuration limits. Injected counter-boundary tests exercise guards without constructing enormous streams. The independent bounded-writer suite additionally reparses exact 1 MiB encoded plain and quote-heavy records, checking every decoded byte, and tests duplicate projection at and beyond the cap. All 11 tests passed.

## Storage measurement

The fixed row is 14 input bytes and includes three fields, an embedded comma/CRLF/quote and a non-UTF-8 byte. The driver feeds bounded batches and consumes inspection lines without collecting prior records. Every emitted row was checked against exact hand-authored bytes.

| Records | Input bytes | Record ByteBuffer capacity | Logical field ends | Input ByteBuffer capacity |
| ---: | ---: | ---: | ---: | ---: |
| 1000 | 14000 | 32 bytes | 2048 bytes | 4096 bytes |
| 100000 | 1400000 | 32 bytes | 2048 bytes | 4096 bytes |

The record buffer's capacity is its high-water capacity because clearing retains allocation. Parser record retention remained the same as total input grew from 1000 to 100000 rows of this fixed corpus. Fixed scalar state, CLI index arrays, compiler ABI stack layout, stdio buffers and allocator overhead remain outside the table. ByteBuffer growth can temporarily retain old and new allocations; the general bound is documented in README. The receipts also retain descriptive process RSS samples separately from these measured buffer capacities.

