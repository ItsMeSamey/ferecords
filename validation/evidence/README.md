# Current-source integration receipts

These seven receipts came from one complete invocation of the packaged `validation/run.py` on November 6, 2026. All stages passed on core `8713bca3`, CLI source `0eaeb4f2` and executable `27146ff3`. These are direct current-source runs, rather than historical tests attributed to a later hash. The exact hashes are in `VALIDATION.json`.

Publication copies replace absolute development paths with `package/` and the external compiler path with `external/fe-v26.5.0-linux-amd64`. `validation/ORIGIN.json` maps original receipt hashes to published-copy hashes. The receipt hashes inside `VALIDATION.json` identify the original emitted bytes; use ORIGIN for the normalized files here. Outcomes, tested source hashes, counts and command flags are unchanged. A fresh local invocation writes its own unnormalized current receipts under build/validation-runs.

This integration run precedes the owner's separate exact-package clean-room extraction. Its result is not represented as that later clean-room run. Historical negative behavior and the first configuration-transport mismatch remain in validation/history.
