# Audit 1: product-purpose test IDs and task links

Verified locally on 2026-10-22 in worktree `audit1-spec-check-product-test-ids`.

The finding was a missing CI guard between 09 §6 and tasks.json. The protected design bundle, including the original `spec_check.py` G12 list, remains unchanged. The companion [checker](../check_product_purpose.py) enforces all nine missing IDs and each P01..P19 implementation-task list being a subset of tasks.json. Missing, duplicate, unexpected or malformed purpose rows also fail.

The existing CI command `python3 -m unittest discover -s tools/tests -v` discovers [test_product_purpose.py](../../tests/test_product_purpose.py). Its live-repository test checks the actual bundle; another test checks that the constant ID set matches all nine IDs in 09 §6. No workflow change is needed. All planted mutations use temporary files.

| Command | Local result |
|---|---|
| `python3 -I tools/ci/check_product_purpose.py` | PASS: all nine IDs registered, P01..P19 task links valid |
| `python3 -I tools/ci/check_product_purpose.py --selftest` | PASS: 3 violations caught by intended rule, 1 clean case |
| `python3 -I -m unittest discover -s tools/tests -p test_product_purpose.py -v` | PASS: 14 tests, including removal of each of 9 IDs and an unknown task in each of 19 rows |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | PASS: 44/44 machine checks and 72/72 presence checks |
| `python3 tools/vocab_check.py` | PASS: 45 axes, 228 values |
| `python3 tools/validation_check.py` | PASS: internal consistency; archived originals not reverified |
| `python3 tools/validation_check.py --selftest` | PASS: 38 mutations caught by intended reason |
| `python3 -m unittest discover -s tools/tests -v` | Exit 1: 447 tests; 435 passed, 6 errors, 6 skipped; new guard tests all pass |
| `python3 -I -m unittest discover -s tools/ci/tests -v` | Exit 1: 20 tests; 16 passed, 2 failures, 2 errors |
| `cargo test --all --offline` | Exit 101: stops at existing local S3 socket test |
| `cargo test --all --offline --no-fail-fast` | Exit 101: Rust result totals 385 passed, 2 failed, 1 ignored; two targets fail for environment restrictions below |
| `CARGO_NET_OFFLINE=true cargo test -p onjeon-contracts --lib --offline` | PASS: 54 Rust tests, including 129 nested Python codegen tests |
| `git diff --check` | PASS |

Broader-suite limits, outside this change:

- Python's 6 errors are R2 budget/checkpoint end-to-end tests attempting to create a local HTTP server: `PermissionError: [Errno 1] Operation not permitted`. The 6 skips require private archived originals/tools (5) or an old botocore (1).
- `tools/ci/tests` reports 2 existing dependency-check failures: the ontology knowledge zone depends on/imports `onjeon-rules-engine` in the twin zone (3 findings). This existing discrepancy is also recorded in the bootstrap sample README. Its 2 errors are skeleton tests blocked from creating local sockets.
- Rust `onjeon-collect --test http_conformance` cannot create its local S3 server (`PermissionDenied`). The contracts target initially failed because a nested codegen compatibility probe tried to resolve `index.crates.io`; the outer `--offline` flag does not propagate to that subprocess. Setting `CARGO_NET_OFFLINE=true` made that target pass without network access.

Checked source SHA-256:

```text
cd051a3c4e936d04aee278e0e1cbfb5554abd0da2e2464d0eb1ec08e4c080439  tools/ci/check_product_purpose.py
e307ea66211d71768d339f253e1686ea5a8f850ce2f9ad0babfbba053b0b9de4  tools/tests/test_product_purpose.py
```

This proves static registration and referential integrity only. It does not execute the nine product-purpose acceptance tests or close any P row with release completion evidence. No production, spending, legal or secret decision was needed.
