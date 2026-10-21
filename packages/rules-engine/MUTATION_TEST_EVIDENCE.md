# Audit 1 mutation test evidence — fix round 4

Executed locally on 2026-10-21, starting from `8e186be` with the round 4
changes to `tests/mutation.rs`. Toolchain: rustc/cargo 1.98.1, Python 3.13.5,
boto3 1.43.100 (the version pinned by CI).

The generic mutators already cover the synthetic fixture and every rule loaded
from `packages/fixtures/rules/real`. This round adds a failure when any rule
generates zero mutants and prints the per-rule counts so coverage is visible in
test output. The mutators include comparator flips, literal ±1 changes,
rounding replacements, and removal of each `all` child, alongside the additional
mutators described in the engine README.

## Mutation results

Reproduce the counts with `cargo test --test mutation -- --nocapture`.
The recorded run used `cargo test --all -- --nocapture`, which also runs this
integration test.

| Rule | Golden cases | Generated mutants |
|---|---:|---:|
| fixture-rule-001 | 15 | 26 |
| kb-driver-fine | 12 | 28 |
| kb-driver-lawyer-fee | 20 | 79 |
| kyobo-1995-cancer-waiting | 5 | 9 |
| kyobo-cancer-main-dx | 18 | 40 |
| kyobo-small-cancer-skin | 17 | 41 |
| kyobo-wholelife-accident-death | 10 | 27 |
| kyobo-wholelife-disease-death | 23 | 86 |
| **Total** | **120** | **336** |

All 336 generated mutants load successfully and are killed by the golden cases;
there are zero survivors and zero equivalence allowlist entries. All six mutation
tests pass, including the 11 hand-written mutants, harness negative controls,
rate literal representation checks, and the wrapped real-rule rate regression
(79 mutants, including six rate mutants).

## Local CI checks

| Command | Result |
|---|---|
| `cargo fmt --all -- --check` | Pass |
| `cargo clippy --all-targets -- -D warnings` | Pass |
| `cargo test --all -- --nocapture` | Pass: 71 Rust tests and 3 doc tests |
| `python3 tools/vocab_check.py` | Pass: 33 axes, 177 values |
| `python3 tools/validation_check.py` | Pass: extracts and metadata internally consistent; originals not re-verified |
| `python3 tools/validation_check.py --selftest` | Pass: all 38 tampering cases caught |
| `python3 -m unittest discover -s tools/tests -v` | 197 tests: 188 passed, 6 skipped, 3 setup errors (sandbox limitation below) |
| `cargo build --locked --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir /tmp/audit1-mutation-onto` | Pass |
| `python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py /tmp/audit1-mutation-onto/debug/ontology-case-runner` | Pass |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | Pass: 44/44 machine checks, 72/72 existence checks |

The three Python setup errors are all in `test_r2_budget.EndToEnd`:

- `test_admitted_run_spends_within_its_admission_before_reserving`
- `test_repeated_refused_runs_are_recorded_then_closed`
- `test_settlement_retry_is_counted_in_the_settlement`

Each fails while `S3Stub` creates `ThreadingHTTPServer(("127.0.0.1", 0), Handler)`:
`PermissionError: [Errno 1] Operation not permitted` at socket creation. The
worktree sandbox denies local sockets; these tests must run in CI or an
environment that permits them. The tests were left enabled. The six skips are
the existing archive-dependent tests and the conditional-put compatibility test
for an older botocore API; no skips were added for this task.

## Hosted CI status

The reported `CI FAIL:no-ci-runs` is still an external verification gap. This
task explicitly prohibits GitHub access, commits, and pushes, so no hosted run
was triggered or inspected. The supervisor must publish the changes and obtain
a hosted CI result. The local results above do not claim that hosted CI passed.
