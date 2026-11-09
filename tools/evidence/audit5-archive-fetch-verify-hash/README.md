# Audit 5: verify fetched bytes before restore

The reported unchecked fetch was already fixed by Audits 2/3 in this worktree's
base. The production implementation is preserved: hash `raw.get(key)` bytes
against the manifest digest before creating the destination directory or
writing its file. Server checksum metadata does not decide integrity.

Three additional R2 regressions cover external overwrite between successful
restore and rerun (including a forged original checksum), CLI failure-code
propagation and budget settlement as `exit_1`, and a valid empty object whose
manifest digest matches. Tests use synthetic bytes/credentials, real
`S3Store.get`, botocore Stubber and mocked budget start/finish.

Commands run on 2026-11-10 in this worktree with Rust 1.98.1 and boto3 1.43.100:

| Command | Result / evidence |
|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_source_archive*.py' -v` | 70 passed, no skips, exit 0: [archive tests](archive-tests.log) |
| `python3 tools/evidence/audit5-archive-fetch-verify-hash/check_fetch_mutations.py` | Each of four selected regressions detects both mutations, no skips, exit 0: [mutation log](fetch-mutations.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,412 run, 1,406 passed, 6 existing skips, exit 0: [full Python tests](python-tests.log) |
| `cargo test --all --locked --offline` | 513 Rust tests passed, 1 existing ignored; embedded Python suites 39 and 129 passed, exit 0: [workspace tests](rust-tests.log) |
| From `docs/blueprint/proposals/온톨로지/검증/runner`: `cargo test --locked --offline` | 4 passed, exit 0: [runner tests](runner-tests.log) |
| Vocabulary, validation/self-test, product-purpose links, design bundle, whitespace | All passed; exact commands and exit codes: [static checks](static-checks.log) |
| Allowed/protected paths, Python parsing, local Markdown links, whitespace | Passed: [scope checks](scope-checks.log) |

Five existing Python skips require private local archived originals (three also
require `pdftotext`). The sixth is an old-botocore test that does not apply to
the installed version supporting conditional PUT. All new tests and the R2
fetch subcases ran successfully.

The mutation script modifies only an in-memory function, keeping each test's
temporary manifest and stubbed store patches active. Expected unittest failures
are followed by `MUTATION REJECTED`: removing the check gives 14 failures and
1 error (the forbidden later GET); moving it after writes gives 15 failures.
Both variants must be rejected by every selected test. The script never writes
the production implementation.

Product mapping: A1, Q7, L1, I6, M1, P02/P03. See the
[audit record](../../../docs/blueprint/audits/2026-11-10_archive_fetch_verify_hash.md)
and its entry in `09_제품목적_대응표.md`. This is local archive-tool regression
evidence, not actual disclosure acquisition, R2 observation reconciliation,
consumer UX or first-release completion evidence.
