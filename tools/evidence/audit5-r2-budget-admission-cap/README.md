# Audit 5: R2 admission and ledger write caps

Node: `audit5-r2-budget-admission-cap`. Product mapping: P02/P03, Q7, L1, M1.
See the [audit record](../../../docs/blueprint/audits/2026-11-10_r2_budget_admission_cap.md),
BLUEPRINT and the evidence note in `09_제품목적_대응표.md`.

The last allowed admission now writes closure before reservation, including when
reservation succeeds. It may still execute and settle, while N+1 sends no admission
PUT. Global and job closures, both limits reached together, shared global usage
across jobs, next UTC month, zero limits, ledger read failure, closure write failure,
request accounting and local lock release are covered by loopback HTTP regressions.
Closure is remembered locally before the remote PUT so a failed write stops further
admissions on that machine. The existing append guard already limited both
reservations and settlements to 100 records after the last checkpoint; a new direct
write regression verifies the checkpoint-relative cap for ordinary and recovery
sessions. Neither caps nor the policy hash changed.

| Command | Result / evidence |
|---|---|
| Before implementation: `python3 -m unittest discover -s tools/tests -p test_r2_budget.py -k last_admission -v` | Normal last admissions fail all 3 scope subcases because no closure is written: [before-tests.log](before-tests.log) |
| Initial R2 sweep: `python3 -m unittest discover -s tools/tests -p 'test_r2*.py' -v` | 143 passed: [r2-tests.log](r2-tests.log). The additional mixed-job regression is included in final full discovery below |
| `python3 -m unittest discover -s tools/tests -p test_r2_budget.py -k admission -v` | 12 passed: [admission-tests.log](admission-tests.log) |
| `python3 tools/evidence/audit5-r2-budget-admission-cap/verify_mutations.py` | Both boundary mutants detected, exit 0: [mutation-tests.log](mutation-tests.log). Its assertion failures are intentional; production files are never edited |
| `env -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -v` | 1,425 run, 1,419 passed, 6 existing skips, no failures/errors, exit 0: [Final full Python results](python-tests.log) |
| `cargo test --all --locked --offline` | 513 passed, 1 existing ignored, exit 0: [rust-tests.log](rust-tests.log) |
| In `docs/blueprint/proposals/온톨로지/검증/runner`: `cargo test --locked --offline` | 4 passed, exit 0: [runner-tests.log](runner-tests.log) |
| `python3 -m unittest discover -s tools/tests -p test_o13_ruling.py -v` | 11 passed: [gate-tests.log](gate-tests.log) |
| Workflow, vocabulary, validation/self-test, product purpose, design spec, blueprint counts/status, whitespace | Passed: [static-checks.log](static-checks.log) |

The [initial full discovery](python-tests-initial.log) ran 1,425 tests with 1 failure
and 6 skips. The only failure was the existing O13 fixture's whole-file hash of
`infra/r2/BUDGET.md`. After reviewing the documentation diff, only that hash was
refreshed; all decision-gate and cost-policy hashes remain pinned. The gate tests
and full discovery were rerun. The six existing skips require private originals
(5) or an older botocore without conditional PUT support (1).

All commands ran in this worktree with Python 3, Rust 1.98.1 and boto3 1.43.100.
Only temporary local ledgers, synthetic data and loopback S3 were used. No real R2,
credentials, GitHub, commit or push was used. The single-environment, one-at-a-time,
manual-operation constraint remains: blind admissions followed by a closure marker
are not an atomic distributed counter. Admission LIST failure or remote closure
failure combined with a new environment remains a documented limitation.

These are archive-tool regressions, not actual disclosure acquisition, R2
observation reconciliation, consumer UX or first-release completion evidence.
P02/P03 remain open.

[Scope and source hashes](scope-and-source-hashes.json) record the parent HEAD,
changed-source SHA-256 values and unchanged policy hash. Allowed-path and protected-path
checks passed; no prohibited file was changed.
