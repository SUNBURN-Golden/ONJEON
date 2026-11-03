# Audit 4: reservation attempts fit the admission budget

The admission Class A limit remains 8. `reserve_attempts` changes from 5 to 2
total attempts: an ordinary first reservation costs 5 Class A requests and each
additional attempt after a lost race costs 3. Two lost races now report
`could not reserve after 2 attempts (concurrent runs)` rather than an incidental
Class A exhaustion error while preparing an unreachable third attempt.

The previous policy's SHA-256 is retained in `previous_policy_sha256`, so existing
ledger records remain readable. The common test fixture uses the same attempt
count. The new loopback regressions copy the shipped request and admission limits,
insert valid competing records immediately before conditional PUTs, and verify
actual botocore 412 responses, final-attempt success, exhaustion, server-observed
Class A usage (exactly 8), retained admission and released local gate. A separate
local-ledger regression reads a record written with the previous policy hash.

Additional HTTP retries, paginated LISTs and checkpoint writes still consume the
same admission limits and may exhaust them sooner. No cap was increased.

All commands ran in this worktree. The root README's directory-local Rust setup
was applied with `rustup override set --path "$PWD" 1.98.1`, selecting the already
installed toolchain. No real R2 service, production change, GitHub operation,
commit or push was used.

| Command | Result / evidence |
|---|---|
| Before the fix: `python3 -m unittest discover -s tools/tests -p test_r2_budget.py -k shipped_policy -v` | 2 tests, 1 failure and 1 error reproduce `class_a would reach 9 > limit 8`: [before-tests.log](before-tests.log) |
| Same command after the fix | 3 passed, no skips, exit 0: [regression-tests.log](regression-tests.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_r2*.py' -v` | 131 passed, no skips, exit 0: [budget-tests.log](budget-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,329 run, 1,323 passed, 6 existing skips, no failures/errors, exit 0: [python-tests.log](python-tests.log) |
| `cargo test --all --locked --offline` | 478 passed, 1 existing ignored test, no failures, exit 0: [rust-tests.log](rust-tests.log) |
| From `docs/blueprint/proposals/온톨로지/검증/runner`: `cargo test --locked --offline` | 3 passed, exit 0: [runner-tests.log](runner-tests.log) |
| Workflow, vocabulary, validation, validation self-test, product-purpose, spec, blueprint counts, whitespace | All passed, commands and exit codes: [static-checks.log](static-checks.log) |
| Allowed paths, protected paths, Python parsing and whitespace | Passed: [scope-check.log](scope-check.log) |

Product mapping: A1/A2/A4, Q7, L1, I1, M1, P02/P03. This is local archive-tool
regression evidence. It does not close actual disclosure acquisition, R2
observation reconciliation, consumer UX or first-release completion requirements.
See the [audit record](../../../docs/blueprint/audits/2026-11-03_r2_reserve_attempts_policy.md)
and the linked entry in `09_제품목적_대응표.md`.
