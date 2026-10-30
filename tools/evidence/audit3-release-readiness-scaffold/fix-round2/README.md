# Audit 3 release-readiness scaffold — fix round 2

Latest: [fix round 3](../fix-round3/README.md) adds the actual evidence scaffold.
The results and path restriction below describe round 2 only.

The reported failure expected an injected checkpoint-write error but instead
hit the real admission deadline: `run time 131s exceeds limit 120s`.
`test_failed_checkpoint_retries_do_not_grow_backlog_or_block_recovery` now
controls only `r2_budget`'s monotonic clock. The HTTP stub and botocore retain
their real clocks and timeouts. All five failed writes, request/byte accounting,
unchanged backlog, lock release, successful recovery and compacted/full ledger
equivalence assertions still run. No production code or budget limit changed.

A separate checkpoint admission regression checks the exact 120-second boundary
and rejection at 121 seconds, with zero HTTP requests, no reservation, archive
access still denied and the local lock released. It uses the same controlled
clock, so checking timeout enforcement does not require sleeping.

| Verification | Command / evidence |
|---|---|
| Checkpoint regressions: 63 passed | `python3 -m unittest discover -s tools/tests -p test_r2_checkpoint.py -v`; [log](checkpoint-tests.log) |
| Readiness regressions: 16 passed | `python3 -I -m unittest discover -s tools/tests -p test_release_readiness.py -v`; [log](readiness-tests.log) |
| Full Python suite: passed, 1,312 run, 6 skipped (175.444s) | `python3 -m unittest discover -s tools/tests -v`; [log](python-tests.log) |
| Rust workspace tests: passed | `cargo test --all`; [log](cargo-tests.log) |
| Rust format and clippy: passed | [format](cargo-format.log), [clippy](cargo-clippy.log) |
| Product-purpose registration and task/spec checks: passed | [purpose](product-purpose.log), [spec](spec-check.log) |
| Vocabulary, validation, tamper self-tests and blueprint counts: passed | [vocabulary](vocabulary.log), [validation](validation.log), [self-tests](validation-selftest.log), [counts](blueprint-counts.log) |
| Both prescribed readiness commands: expected exit 1 | [default purpose](live-readiness.log), [explicit purpose, JSON](live-readiness-purpose.log) |

Both live commands report **19 open purpose rows, 64 open features, zero closed
and zero excluded**. These logs verify the checker mechanics and do not close
product rows or complete T-OP-08. Positive readiness tests use synthetic files.
The six Python skips concern unavailable archived originals/reproduction inputs
and the old-botocore branch on an installed version supporting conditional PUT.

The original path restriction still applies: `docs/release-readiness/**` is
absent from this node's explicit allowed-path list. The evidence directory has
not been created; a path exception was requested. The previously prepared
[scaffold patch](../evidence-scaffold.patch) still passes
[`git apply --check`](scaffold-patch-check.log). Thus the reported test failure
is addressed, but creation of both originally requested paths remains incomplete.
The earlier optional `tools/ci/tests` dependency-policy failures are documented
in the [round 1 evidence](../README.md); that separate suite was not rerun here.

All source/document edits are within the allowed paths. No commit, push, GitHub
call, production access or secret access was performed.
