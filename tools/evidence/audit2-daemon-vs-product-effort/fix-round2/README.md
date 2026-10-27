# Audit 2 daemon versus product effort — fix round 2

The decision remains: freeze daemon expansion, allow audit bug fixes and their
regressions, prioritize the V1 gate, then remaining M1 vocabulary generation and
I7/I12 schema verification. This round changes test setup only; it does not
implement a scheduler freeze or complete V1/M1.

## Timeout investigation and correction

The supplied 900-second failure excerpt ends after the validation self-test
successfully caught all 38 mutations. It does not identify the next command or
test. The exact cause of that historical timeout cannot be established from
that excerpt.

Two slow daemon tests were isolated and completed successfully
([slow-tests.log](slow-tests.log)):

- `Cli.test_all_scenarios_exit_zero_and_print_expected_and_actual`: 18.814s.
- `StructuredFieldsOnly.test_replacing_or_deleting_explanation_keys_changes_nothing`:
  27.174s, including initial scenario-cache population.

The complete daemon suite took 78.783s ([daemon-before.log](daemon-before.log));
the standalone schema compatibility suite took 76.111s
([compat-before.log](compat-before.log)). These timings include concurrent
diagnostic work and are observations, not performance guarantees.

The ontology runner's fallback Cargo build had no timeout and captured all
output. A competing target-directory lock could therefore wait indefinitely
without displaying Cargo's lock diagnostic. This environment supplied a shared
`CARGO_TARGET_DIR`. A deliberately held lock reproduced that wait in a temporary
target directory ([cargo-lock-reproduction.log](cargo-lock-reproduction.log)).
This proves a hang path, not that the original timeout used that path.

`tools/tests/test_ontology_runner_io_error.py` now limits the fallback build to
120 seconds and fails setup with Cargo's stderr and guidance to check the build
lock or provide an already-built runner. It retains the previous round's Cargo
artifact discovery and prebuilt override. A timeout is a test error, never a
skip or a pass. The new regressions cover byte/text/absent stderr and a real
POSIX Cargo lock; the latter uses a five-second test deadline. All 13 focused
tests passed ([runner-tests.log](runner-tests.log)).

Initial exploratory discovery runs ended at their outer limits of 240 seconds
([python-before.log](python-before.log)) and 840 seconds
([python-timed-before.log](python-timed-before.log)), with incomplete output at
different tests. Neither is counted as a pass or used to infer a single root
cause. Final monitored invocations below completed successfully.

## Final verification

Run from this worktree with cached Cargo dependencies, a worktree-local target
directory, `CARGO_NET_OFFLINE=true`, and `ONJEON_ONTOLOGY_RUNNER` unset. Temporary
files for the final run used `$PWD/target/audit2-tmp`. Thus Python discovery
exercised the fallback build, and builds did not write to the inherited shared
target directory.

Exact commands, exit codes, and timings:
[verification-summary.log](verification-summary.log). The separately monitored
commands total **141.991 seconds**, below the reported 900-second budget; this
is summed command runtime, not one uninterrupted shell invocation.

| Check | Result | Evidence |
|---|---|---|
| Full `tools/tests` discovery | 1,161 run; 1,155 passed, six skipped; 104.194s inside unittest | [python-tests.log](python-tests.log) |
| Cargo workspace | 458 passed, one ignored; embedded Python suites also pass | [rust-tests.log](rust-tests.log) |
| Ontology runner Rust tests | Three passed | [runner-rust-tests.log](runner-rust-tests.log) |
| Ontology checks | 11 questions, 15 constraint self-tests, 25 release/document-model tests | [ontology-check.log](ontology-check.log) |
| Validation and tampering self-test | Clean; all 38 mutations caught | [validation.log](validation.log), [validation-selftest.log](validation-selftest.log) |
| Vocabulary / generated clients / SQL vocabulary | 49 axes / 30 files current / 20 SQL axes aligned | [vocabulary.log](vocabulary.log), [codegen.log](codegen.log), [sql-vocabulary.log](sql-vocabulary.log) |
| Product-purpose registration and design bundle | Both pass; static consistency only | [product-purpose.log](product-purpose.log), [design-specs.log](design-specs.log) |

The six Python skips remain five unavailable-original cases and one old-botocore
branch. No ontology runner regression was skipped. The ignored Rust test is
the fixture regeneration helper. PostgreSQL runtime constraints were not rerun;
SQL vocabulary agreement does not prove I7/I12 storage and permission isolation.
V1 reproduction, cross-review and S1/S6 remain open. The separately documented
[round 1 optional CI-checker baseline failures](../fix-round1/README.md#additional-baseline-findings)
were not changed or rerun here; this evidence does not claim every optional
repository suite is green.
