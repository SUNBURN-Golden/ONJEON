# Fix round 1: deterministic settlement clocks

CI run `42720338918` failed the expired-run settlement regression with
`600 != 601`. The test captured a real floating-point monotonic start and
mocked only the end time. For example, `(1023.1 + 601) - 1023.1` evaluates to
`600.9999999999999`, so the meter's integer elapsed-time measurement is 600.
The same fixture pattern affected the settlement GET exhaustion test.

[Before-fix reproduction](before-clock-tests.log) runs both tests with an
outer `mock.patch.object(test_r2_budget.b.time, "monotonic", return_value=1023.1)`.
Both fail the elapsed-time assertion; both GET exhaustion subcases fail.

Both tests now mock the clock before creating the session, start at exactly
100, and advance it to 701 for settlement. The GET test resets the clock for
each injected-store subcase. Assertions still require 601 elapsed seconds,
the failed settlement, full reservation accounting, released local gate and
restored alarm where applicable. Production budget accounting is unchanged.

[Clock regression checks](clock-tests.log) repeat both test methods inside
outer monotonic mocks of `100.1`, `1023.1` and `1000000.123456789`. All six runs
pass without skips, including both GET exhaustion subcases per run.

The archive finding remains resolved: the existing implementation compares
the hash before calling `put_raw`, and archives the same verified bytes.
The archive suite and the in-memory upload-order/cache-reread mutation checks
were rerun for this round. See the [original archive evidence](../README.md)
for the behavior covered and the scope of the finding.

Commands rerun on 2026-11-10, from this worktree, using Rust 1.98.1 and
boto3 1.43.100. Each log records its command and exit code.

| Command | Result / evidence |
|---|---|
| `python3 tools/evidence/audit5-archive-samples-check-before-put/check_order_mutations.py` | Both mutants rejected; exit 0: [mutations](mutations.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_source_archive*.py' -v` | 69 passed; no skips: [archive tests](archive-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,411 run; 1,405 passed; 6 existing skips; exit 0: [Python tests](python-tests.log) |
| `cargo test --all --locked --offline` | 513 passed; 1 existing ignored test; embedded Python suites also passed: [workspace tests](rust-tests.log) |
| In `docs/blueprint/proposals/온톨로지/검증/runner`: `cargo test --locked --offline` | 4 passed: [runner tests](runner-tests.log) |
| `cargo fmt --all -- --check` | Exit 0: [format](rust-checks.log) |
| `cargo clippy --locked --offline --all-targets -- -D warnings` | Exit 0: [lint](rust-lint.log) |
| Workflow, vocabulary, validation, validation self-test, design specs, Blueprint counts | All exit 0; exact commands: [static checks](static-checks.log) |
| Allowed paths, Python syntax, local Markdown links, whitespace | Passed: [scope checks](scope-checks.log) |

The six Python skips are the existing private-archive-dependent tests (five)
and the old-botocore compatibility case (one). Both modified settlement
regressions and all archive order/snapshot checks ran without skips.

All writes stayed in the authorized worktree paths. No production service,
credentials, GitHub calls, commits or pushes were used. This evidence closes
the local archive finding and reported CI failure; product mapping remains
A1, Q7, L1, I6, M1, P02/P03, with the scope limits in the original record.
