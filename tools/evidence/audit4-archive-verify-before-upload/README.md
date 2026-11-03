# Audit 4: verify cached bytes before upload

The reported ordering bug was already fixed by Audit 2 in this worktree's base.
`cmd_archive_samples` reads the cache bytes once, hashes them and compares with
`samples.csv` before calling `put_raw`. This change preserves that implementation
and adds regressions at the real `S3Store` request boundary.

The new tests use synthetic credentials/documents and botocore `Stubber`, with a
mock budget session. Mismatched, same-length corrupted and empty cache bytes must
produce the existing failure result without any raw or derived request, even
when derived inputs exist. A mixed batch must upload only the matching row's
original and observation, with the exact conditional PUT body/checksum and key.
A matching-only rerun verifies existing checksums and issues no PUT.

The reproducible mutation script moves the comparison after `put_raw` in memory.
Both new tests reject that mutation. Its log deliberately ends with unittest
failures/errors, followed by `MUTATION REJECTED`; the script's exit code is 0.
No production source is modified by the mutation check.

Commands ran on 2026-11-03 in this worktree, using the README's directory-local
Rust 1.98.1 setup. No real R2 service, production change, GitHub operation,
commit or push was used.

| Command | Result / evidence |
|---|---|
| `python3 tools/evidence/audit4-archive-verify-before-upload/check_upload_order_mutation.py` | Both new tests detect the ordering bug; no skips; exit 0: [mutation log](upload-order-mutation.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_source_archive*.py' -v` | 67 passed, no skips, exit 0: [archive tests](archive-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,331 run, 1,325 passed, 6 existing skips, no failures/errors, exit 0: [Python tests](python-tests.log) |
| `cargo test --all --locked --offline` | 478 Rust tests passed, 1 existing ignored; embedded Python suites 39 and 129 passed; exit 0: [workspace tests](rust-tests.log) |
| From `docs/blueprint/proposals/온톨로지/검증/runner`: `cargo test --locked --offline` | 3 passed, exit 0: [runner tests](runner-tests.log) |
| Workflow, vocabulary, validation, validation self-test, product-purpose links, design specs, blueprint counts, whitespace | All passed; exact commands and exit codes: [static checks](static-checks.log) |
| Allowed/protected paths, Python parsing, Markdown links and whitespace | Passed: [scope checks](scope-check.log) |

Five existing Python skips require private local archived originals (three also
require `pdftotext`). The sixth is an old-botocore test that does not apply to
the installed conditional-PUT-capable version. Both new tests and all their
subcases ran successfully.

Product mapping: A1, Q7, L1, I6, M1, P02/P03. These are local archive-tool
regressions, not actual disclosure acquisition, R2 observation reconciliation,
consumer UX or first-release completion evidence. See the
[audit record](../../../docs/blueprint/audits/2026-11-03_archive_verify_before_upload.md)
and its linked entry in `09_제품목적_대응표.md`.
