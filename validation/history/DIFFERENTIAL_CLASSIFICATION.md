# First candidate differential classification

Candidate binary SHA256 `86f49de7ba7004914b1e3106307bd560c78012c6e33c94476ea370b402b9c45b` was copied to an immutable-by-convention reviewer snapshot before testing. Frozen corpus SHA256 `85da8df5c9a1fe48f61581991fa0753d7b5e00302a099864a41458fd6b7cb08a` predates candidate source inspection.

`CANDIDATE_DIFFERENTIAL_86f49de7ba700491.json` preserves the first run as FAIL: 30 mismatches in 8,055 executions, all six invalid-configuration cases at five chunk sizes. The CLI rejects invalid configurations as usage status 64 before constructing a Parser; it emits no diagnostic transport. The original runner expected the library's Config2 error and transport. Source inspection confirms the CLI's explicit prevalidation and the core's independently typed configuration error.

Thus the 30 failures are a test-transport boundary mismatch, not evidence that malformed parser configuration succeeds. They are not deleted or silently counted as parser passes. Direct library configuration tests remain required. The other 1,605 cases (8,025 executions at chunks 1, 2, 3, 7 and 4096) agree with frozen decoded records, complete-row prefix, exact first error code/byte/record/field, successful positions and fixed metadata accounting. This checks five fixed chunk sizes; it does not by itself establish every single split or arbitrary partition coverage.

One separate contract issue was identified: canonical quoting can increase raw record size. Parsing canonical output needs a sufficient raw limit, and some records at the parser's hard raw cap cannot be reparsed after canonical expansion under any supported configuration. Documentation must condition roundtrip claims accordingly. This does not justify changing the frozen input grammar.
