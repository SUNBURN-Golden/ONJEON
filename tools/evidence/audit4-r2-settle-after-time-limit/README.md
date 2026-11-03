# Audit 4: settlement after the run time limit

`Session.settle()` now disables the meter's run deadline alongside restoring the
alarm. Elapsed time remains measured; the final summary can report time beyond
the run limit. Request, byte, retry, ledger and individual HTTP timeout guards
remain in force. The ledger still caps settlement amounts at the reservation and
adds the worst case of the settlement write. Failed settlements retain the full
reservation.

The deterministic regressions cover the admission/alarm gap (30 seconds spent
before the alarm starts, successful finish at 601 seconds of a 600-second run),
preservation of the original SIGALRM error through `finally`, elapsed-time
reporting after a failed settlement write, and the existing byte exhaustion
scenario after the deadline. The loopback tests use real botocore requests and
check the stored settlement and server-observed usage; they do not sleep to
simulate the deadline.

All commands were run from this worktree. No real R2 service, credentials,
GitHub operation, commit or push was used. As documented in the root README,
the already-installed Rust toolchain was selected for this worktree with
`rustup override set --path "$PWD" 1.98.1`. The directory override is local
environment setup and does not change the global default or other worktrees.

| Command | Result / evidence |
|---|---|
| Before the fix: `python3 -m unittest discover -s tools/tests -p test_r2_budget.py -v` | 65 tests, 1 failure and 4 errors reproduce the bug: [before-budget-tests.log](before-budget-tests.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_r2*.py' -v` | 128 passed, no skips, exit 0: [budget-tests.log](budget-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,326 run, 1,320 passed, 6 existing skips, no failures/errors, exit 0: [python-tests.log](python-tests.log) |
| `cargo test --all --locked --offline` | 478 passed, 1 existing ignored test, no failures, exit 0: [rust-tests.log](rust-tests.log) |
| From `docs/blueprint/proposals/온톨로지/검증/runner`: `cargo test --locked --offline` | 3 passed, exit 0: [runner-tests.log](runner-tests.log) |
| Workflow, vocabulary, validation, validation self-test, product-purpose, spec, blueprint counts, whitespace | All passed; commands and exit codes: [static-checks.log](static-checks.log) |
| Allowed paths, protected files, Python parsing and whitespace | Passed: [scope-check.log](scope-check.log) |

Product mapping: A1/A2/A4, Q7, L1, I1, M1, P02/P03. This is local archive-tool
regression evidence. It does not close actual disclosure acquisition, R2
observation reconciliation, consumer UX or first-release completion requirements.
See the [audit record](../../../docs/blueprint/audits/2026-11-03_r2_settle_after_time_limit.md)
and the linked entry in `09_제품목적_대응표.md`.
