# Audit 5: archive provider classification

`provider_of` now accepts only HTTP(S) `localhost`/`127.0.0.1` endpoints as
emulators. Explicit AWS and other remote endpoints are refused before client
creation, including when supplied through `ONJEON_S3_ENDPOINT`, with an active
budget or for a ledger store. HTTPS R2 retains hostname case/trailing-dot
normalization and its existing budget, credential and meter checks. Omitting
the endpoint still selects AWS and requires a budget job.

Commands were run in this worktree on 2026-11-10 with Rust 1.98.1. Provider tests
use synthetic credentials, mocked clients and botocore Stubber; budget tests
also use a loopback S3 stub. No real AWS/R2 requests, production changes,
GitHub calls, commits or pushes were made.

| Command | Result / evidence |
|---|---|
| `python3 -m unittest discover -s tools/tests -p test_store_provider.py -v` | 28 run, 27 passed, 1 existing skip, exit 0: [provider tests](provider-tests.log) |
| `python3 -m unittest discover -s tools/tests -p test_r2_budget.py -v` | 72 passed, no skips, exit 0: [budget tests](budget-tests.log) |
| `python3 tools/evidence/audit5-archive-provider-classification/check_provider_mutation.py` | Three regression tests all detect the permissive emulator fallback, exit 0: [mutation log](provider-mutation.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,409 run, 1,403 passed, 6 existing skips, exit 0: [full Python tests](python-tests.log) |
| `cargo test --all --locked --offline` | 512 passed, 1 existing ignored; embedded Python suites 39 and 129 passed, exit 0: [workspace tests](rust-tests.log) |
| From `docs/blueprint/proposals/온톨로지/검증/runner`: `cargo test --locked --offline` | 4 passed, exit 0: [runner tests](runner-tests.log) |
| Workflow, vocabulary, validation/self-test, product-purpose links, design bundle, blueprint counts/status, whitespace | All passed; exact commands and exit codes: [static checks](static-checks.log) |
| Allowed/protected paths, Python parsing, Markdown local links, whitespace | Passed: [scope checks](scope-checks.log) |

The provider skip is the old-botocore regression, which does not apply to the
installed version supporting conditional PUT. All new provider subcases ran.
The other five full-suite skips require private local archived originals
(three also require `pdftotext`).
The mutation log deliberately contains `FAILED (failures=37)` followed by
`MUTATION REJECTED`: the script changes only the final provider rejection to
`return "emulator"` in memory and requires all three selected regression tests
to detect it. Production source files remain unchanged by that script.

Product mapping: A1, Q7, L1, I6, M1, P02/P03. See the
[audit record](../../../docs/blueprint/audits/2026-11-10_archive_provider_classification.md)
and its entry in `09_제품목적_대응표.md`. These are local cost-control boundary
regressions, not actual disclosure acquisition, R2 observation reconciliation,
consumer UX or first-release completion evidence.
