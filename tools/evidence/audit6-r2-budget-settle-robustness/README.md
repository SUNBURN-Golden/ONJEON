# Audit 6: R2 settlement robustness

Node: `audit6-r2-budget-settle-robustness`. Product mapping: A1/A2/A4, Q7, L1,
I1, M1, P02/P03. [Audit record](../../../docs/blueprint/audits/2026-11-15_r2_budget_settle_robustness.md).

Settlement retries sequence conflicts using the existing `reserve_attempts` bound,
refreshing the tail hash and measured usage on every attempt. Append reconciles
412 with an exact comparison against the stored bytes, so a committed PUT followed
by an error and HTTP retry does not become a duplicate reservation or a failed
settlement. Settlement worst-case amounts include the confirming GET; records
larger than 4,096 bytes are rejected before writing. Remaining request, retry,
byte and append guards still stop settlement and retain the full reservation.
The ordinary profile minimum and all policy/profile caps remain unchanged.

The existing deadline/summary and session ledger GET fixes are preserved and
tested together with conflicts. The unpinned initialization CLI now also receives
the policy and body meter at client construction. Paginated admissions/ledger
reads check exact continuation parameters with Stubber; loopback HTTP with one
record per page verifies every LIST page and GET body against meter counters and
persisted amounts. Confirming GET retries are included too.

All commands ran in this worktree using Python 3.13, boto3 1.43.100 and the installed
Rust 1.98.1. Only synthetic data, temporary stores and loopback HTTP were used.
No real R2, real credentials, GitHub, commit or push was used.

| Command | Result / evidence |
|---|---|
| `python3 tools/evidence/audit6-r2-budget-settle-robustness/verify_original.py` | Original revision `b79cfa3eeac1e3cb0178e35637eaf1c241fded54`: all five selected regressions detect the old behavior (four failed assertions, one admission Class A refusal); harness exits 0 only for these expected detections. [before-regressions.log](before-regressions.log) |
| `python3 -m unittest discover -s tools/tests -p test_r2_budget_settlement.py -v` | 14 passed, no skips, exit 0. [regressions.log](regressions.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_r2*.py' -v` | 160 passed, no skips, exit 0. [r2-tests.log](r2-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,630 run, 1,624 passed, 6 existing skips, no failures/errors, exit 0. [python-tests.log](python-tests.log) |
| `cargo test --all --locked --offline` | 532 passed, 1 existing ignored, exit 0. [rust-tests.log](rust-tests.log) |
| `cargo test --locked --offline` in `docs/blueprint/proposals/온톨로지/검증/runner` | 4 passed, exit 0. [runner-tests.log](runner-tests.log) |
| `python3 -m unittest discover -s tools/tests -p test_o13_ruling.py -v` | 11 passed, exit 0. [gate-regressions.log](gate-regressions.log) |
| Workflow, tracked-secret, vocabulary, validation/self-test, product-purpose, spec, blueprint counts/status, Rust format/clippy, whitespace | All passed; exact commands and exit codes in [static-checks.log](static-checks.log). |
| Allowed paths, protected paths, Python AST, unchanged gates/caps | Passed. [scope-check.log](scope-check.log) |

The budget documentation changed only sections 2/3. Sections 4–6 remain identical
to the parent. The D-04 regression fixture refreshes only this document hash and
its explanatory note; other gate/policy hashes and all gate rows are retained.

This closes this local archive-tool finding. GET accounting counts bytes returned
by body streams, not LIST/error bodies or socket traffic. It does not establish
real disclosure coverage, R2 observation reconciliation, product/contract twins,
consumer UX, P02/P03 completion or first-release readiness. BLUEPRINT and the
09 product-purpose table link this bounded evidence without changing those states.
