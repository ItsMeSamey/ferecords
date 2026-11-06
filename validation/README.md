# Independent, runnable validation

Run from the project root on Linux x86_64 with Python 3.10+, the system C linker and the checksum-pinned Fe 26.5.0 release:

```sh
python3 validation/run.py --compiler /path/to/fe_linux_amd64
```

Alternatively set `FE` to that compiler path. No compiler, package or dependency is downloaded. The runner builds the current project, then tests the current binary and library source. Reports, generated native harnesses, logs and binary snapshots go into a new `build/validation-runs/<timestamp>/` directory on every invocation. `VALIDATION.json` records the exact current core, CLI, compiler and binary hashes. A failed run stays available. A compiler checksum mismatch stops before execution.

The command runs:

- The independent whole-input reference against 56 hand-authored parser cases, six writer vectors, and the unchanged 1,611-case corpus. Python csv cross-checks the 88 valid structural strings with an explicit bare-blank-row normalization; it does not judge malformed input.
- All corpus cases at five chunk sizes. Six invalid configurations are CLI usage checks; the native harness separately verifies their library Config2 errors.
- The frozen hand cases through native Fe: all partitions up to eight input bytes, every split of longer cases, inserted empty chunks and terminal-call behavior, totaling 377 schedules.
- Eleven native bounded-writer checks, including full decoded-byte verification at the exact 1 MiB encoded budget, quote expansion, duplicate projection and zero-output preflight rejection.
- 611 focused CLI checks covering generated multirecord data, projection, limits, precise diagnostics, invalid arguments and help.
- Ten native I/O checks on ordinary owned Linux streams: clean input, directory read errors, a private raw PTY that fails after a valid prefix, deferred writes to `/dev/full`, primary error preservation, and a closed downstream pipe. SIGPIPE termination is nonzero and is distinguished from returned Output16. These checks do not claim filesystem durability or force host memory exhaustion.

The project also has its owner-maintained native, CLI and 1,000/100,000-row storage suites documented in the main README. Their receipts complement these independently maintained checks.

## Provenance and historical evidence

The reference, hand cases and corpus were frozen before candidate source inspection. They are unchanged copies here. The portable runners were adapted from the original reviewer-owned scripts for package-relative paths and explicit compiler/output arguments. They do not implement data handling for the product. The core parser/writer and native adapter remain Fe.

`ORIGIN.json` records original and published hashes and identifies adapted files. `history/` contains historical receipts and review reports. Absolute development paths in those publication copies are replaced with `historical-workspace/`; no test outcome, count, source hash or binary hash is changed. Historical commands are provenance records, not commands to run from this checkout.

Historical evidence has distinct scope:

| Evidence | Actual subject |
| --- | --- |
| ORACLE_FREEZE | Pre-candidate reference/corpus validation |
| CANDIDATE_DIFFERENTIAL_86f49de7ba700491 | Initial CLI snapshot; 30 usage-versus-library configuration mismatches retained as FAIL |
| DIFFERENTIAL_CLASSIFICATION | Explains those mismatches; they were subsequently checked directly in the native library |
| NATIVE_CONFORMANCE_d95126063a9eca63 | Original parser core `ef10fb8d`, before bounded writer APIs |
| BOUNDED_WRITER_b93f28c00701e8e4 | Core `fef132f1`, with added bounded writer APIs |
| EXTENDED_CLI_6ac565170dce1e6e | Earlier CLI binary `6ac56517`, before native I/O correction |
| IO_ADAPTER_PROBE | Preserves old false-success behavior and the working standalone adapter probe; PASS means the experiment matched its stated observations |
| FINAL_REVIEW and REVIEW_SEAL | Historical parser/writer assessment; current source is independently retested in evidence/ |

The former HostIo adapter returned false success on read and deferred-output failures. The corrected native adapter in executable `27146ff3` passed the current-source checks in `evidence/`. Fresh runs record their own exact source and binary hashes.

All newly authored validation code, fixtures and corpus are distributed under the project's Apache-2.0 license. Python csv and the installed compiler are dependencies, not bundled copies. The supplied project license also applies to the Fe test harnesses.
