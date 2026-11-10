# Audit 5: ledger metering and policy HTTP attempts

Node: `audit5-r2-budget-ledger-metering`. Mapping: A1/A2, Q7, L1, M1, P02/P03.
See the [audit record](../../../docs/blueprint/audits/2026-11-10_r2_budget_ledger_metering.md),
BLUEPRINT and the evidence note in `09_제품목적_대응표.md`.

The existing explicit ledger body-meter binding already fixed unmetered GETs.
It remains in place for default and injected stores and settlement after `ACTIVE`
is cleared. The missing piece was client construction: it now receives the session
directly, so its retry settings and meter are available before `ACTIVE` is set.
`total_max_attempts` also fixes botocore's distinction between total attempts and
retries: `max_attempts=3` in a Config allowed four HTTP attempts. Policy values and
hashes have not changed.

New real-botocore loopback tests cover policy totals of 1, 2 and 4: ledger GET
success on the last attempt and exhausted failures before reservation; archive GET
and settlement PUT success on the last attempt; exact request counts, retry counts,
GET bytes and settlement accounting. Existing ledger/checkpoint accounting and
byte exhaustion tests cover both default and injected stores.

| Command | Result / evidence |
|---|---|
| Before implementation: `python3 -m unittest discover -s tools/tests -p test_r2_budget.py -k policy_total_attempts -v` | New regression fails four subcases, no errors: [before-tests.log](before-tests.log) |
| Same command after implementation | Passed all six subcases: [retry-tests.log](retry-tests.log) |
| `python3 -m unittest discover -s tools/tests -p test_r2_budget.py -k policy_attempts -v` | Passed all three policy subcases: [settlement-retry-tests.log](settlement-retry-tests.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_r2*.py' -v` | 146 passed, no skips: [r2-tests.log](r2-tests.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_source_archive*.py' -v` | 72 passed, no skips: [archive-tests.log](archive-tests.log) |
| `env -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -v` | 1,427 run, 1,421 passed, 6 existing skips, exit 0: [python-tests.log](python-tests.log) |
| `cargo test --all --locked --offline` | 513 passed, 1 existing ignored, exit 0: [rust-tests.log](rust-tests.log) |
| In `docs/blueprint/proposals/온톨로지/검증/runner`: `cargo test --locked --offline` | 4 passed, exit 0: [runner-tests.log](runner-tests.log) |
| `python3 tools/evidence/audit5-r2-budget-ledger-metering/verify_mutations.py` | All three mutants detected, exit 0: [mutation-tests.log](mutation-tests.log) |
| Workflow, vocabulary, validation/self-test, product purpose, design spec, blueprint counts, formatting, whitespace | All nine checks passed: [static-checks.log](static-checks.log) |

Mutation verification changes methods in memory only. Disabling body metering is
rejected by the existing admission/settlement regressions; dropping the explicit
session argument is rejected by the new policy regression; changing total attempts
back to retry count is rejected by both new regressions. Assertion failures and
one exhausted-GET `BudgetError` in the mutant log are expected detections.

All commands ran in this worktree using Python 3, Rust 1.98.1 and boto3 1.43.100
(botocore 1.43.114). Only temporary local ledgers, synthetic credentials and loopback
S3 were used. The six existing Python skips require private originals (5) or an
older botocore without conditional PUT support (1). No real R2 service, real secrets,
GitHub operations, commits or pushes were used.

[Scope and source hashes](scope-and-source-hashes.json) record the parent HEAD,
changed-file inventory, implementation/test hashes and unchanged policy hash.
All changed paths are allowed; protected files are unchanged.

This evidence resolves the archive-tool finding. It does not establish actual
disclosure acquisition, R2 observation reconciliation, twins, consumer UX or first
release completion. P02/P03 remain open; existing manual-operation and budget
metering limitations continue to apply.
