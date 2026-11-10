# Audit 5: samples.csv SHA-256 format

The reported missing guard was already fixed by Audit 4 in this worktree's
base. `validation_check.check` validates every sample's `sha256` next to the
derived manifest pin check, using the shared 64-character ASCII hex validator.
`source_archive.object_key` independently applies the same check before
`verify_sources.materialize` probes storage or writes a digest-named file.
The existing case-preserving behavior is retained.

Three additional regression tests cover every existing sample row even when
encoded document hashes are changed to match, the actual CSV loader and CLI
entry function (including a missing column), and direct object-key rejection.
The invalid input matrix now includes exactly 64-character traversal strings,
absolute and Windows-style paths, a newline after 64 hex digits, Unicode
lookalikes and non-string values. Existing fetch/verify/materialize tests use
the expanded matrix and assert no store probes/reads and no output files.
The CSV loader now closes its file explicitly and uses CSV newline handling.

Commands run on 2026-11-10 in this worktree with Rust 1.98.1 and boto3 1.43.100:
The [run summary](run-summary.json) records the base commit, command exit codes
and source/log SHA-256 hashes.

| Command | Result / evidence |
|---|---|
| `python3 -m unittest discover -s tools/tests -p test_samples_csv_validation.py -v` | 7 passed, no skips, exit 0: [metadata tests](metadata-tests.log) |
| `python3 tools/evidence/audit5-samples-sha256-format-check/check_hash_mutations.py` | Both mutations rejected by every selected test, exit 0: [mutation log](hash-mutations.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_source_archive*.py' -v` | 70 passed, no skips, exit 0: [archive tests](source-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,415 run, 1,409 passed, 6 existing skips, exit 0: [full Python tests](python-tests.log) |
| `cargo test --all --locked --offline` | 513 Rust tests passed, 1 existing ignored; embedded Python suites 39 and 129 passed, exit 0: [workspace tests](rust-tests.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4 passed, exit 0: [runner tests](runner-tests.log) |
| Vocabulary, validation/self-test, blueprint counts, product-purpose links, design bundle, whitespace | All passed; commands and exit codes: [static checks](static-checks.log) |
| Allowed/protected paths, Python parsing, local Markdown links, whitespace | All passed: [scope checks](scope-checks.log) |

Five existing full-suite skips require private local archived originals
(three also require `pdftotext`). The sixth is an old-botocore test that does
not apply to the installed version supporting conditional PUT. All added
regressions and their subcases ran successfully.

The mutation script modifies functions only in memory. Removing the sample
row guard is caught by all three selected metadata tests (49 subtest failures).
Replacing hex validation with a length-only check is caught by all five
selected metadata/storage tests (47 subtest failures and 8 errors caused by
invalid values reaching later I/O code). The expected `FAILED` outputs in the
mutation log are followed by `MUTATION REJECTED`; the script exits successfully
only when every selected test detects its assigned mutation.

Product mapping: Q7, L1, I6, M1, P02/P03. See the
[audit record](../../../docs/blueprint/audits/2026-11-10_samples_sha256_format_check.md)
and its entry in `09_제품목적_대응표.md`. This is local metadata/archive-tool
regression evidence, not actual disclosure acquisition, R2 observation
reconciliation, consumer UX or first-release completion evidence.
