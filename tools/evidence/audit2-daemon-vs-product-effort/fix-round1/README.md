# Audit 2 daemon versus product effort — fix round 1

Local verification on 2026-10-27, based on HEAD
`dc0fc100843bf539aa37df9c8108dce1b1794670`.

The [decision](../../../../docs/decisions/audit2-daemon-vs-product-effort.md)
keeps daemon work limited to audit bug fixes and regressions, prioritizing the
V1 gate, then remaining M1 vocabulary/schema checks, then M2 integration.
This round fixes the reported test setup failure; it does not implement a
scheduler freeze or claim any product gate has passed.

## Failure and correction

With `CARGO_TARGET_DIR` redirected, the old setup built the runner successfully
but invoked a hardcoded `runner/target/debug/ontology-case-runner` path.
[Before the fix](before.log), the focused suite reproduced all 18 reported
errors, including the secondary `IndexError` after failed payout subtests.

The setup now reads the matching binary's `compiler-artifact.executable` from
Cargo's JSON output. This handles environment/config target directories and
target triples without guessing Cargo's layout. It ignores dependency and
unrelated binary artifacts, accepts cached artifacts, and fails during setup
if no executable is reported. The prebuilt-runner override still bypasses Cargo,
and build failures still fail the tests. Two new setup tests cover these paths;
the seven behavioral runner tests execute the real binary.

## Commands and results

Run from the worktree root. Cargo outputs were kept in this worktree using:

```sh
export CARGO_TARGET_DIR="$PWD/target/audit2-effort"
```

`ONJEON_ONTOLOGY_RUNNER` was unset, so both focused and full Python discovery
exercised the corrected fallback build. No runner path was patched by the test
invocation.

| Command | Result | Log |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p test_ontology_runner_io_error.py -v` | 11 passed | [runner-tests.log](runner-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,159 run, 1,153 passed, 6 skipped, no failures/errors | [python-tests.log](python-tests.log) |
| `cargo test --offline --workspace` | 458 passed, 1 ignored; embedded Python suites of 39 and 129 also passed | [rust-tests.log](rust-tests.log) |
| `cargo test --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml` | 3 passed | [runner-rust-tests.log](runner-rust-tests.log) |
| `python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py target/audit2-effort/debug/ontology-case-runner` | 11/11 questions, 15/15 constraint self-tests, 25/25 release/document-model tests | [ontology-check.log](ontology-check.log) |
| `python3 -I tools/validation_check.py --selftest` | 38 mutations caught for their intended reasons | [validation-selftest.log](validation-selftest.log) |
| `python3 -I tools/vocab_check.py` | 49 axes, 269 values | [vocabulary.log](vocabulary.log) |
| `python3 -I packages/schemas/codegen/gen.py --check` | 30 generated files current | [codegen.log](codegen.log) |
| `python3 -I infra/db/public/tests/test_vocab_sync.py` | 20 SQL vocabulary axes, no problems | [sql-vocabulary.log](sql-vocabulary.log) |
| `python3 -I tools/ci/check_product_purpose.py` | P01–P19 task links and nine required IDs registered; static only | [product-purpose.log](product-purpose.log) |
| `python3 -m unittest discover -s tools/tests -p test_pr_policy.py -v` followed by `python3 -m unittest discover -s tools/tests -p test_blueprint_layer_status.py -v` | 19 + 5 passed, including six daemon prerequisite tests | [decision-tests.log](decision-tests.log) |

The six Python skips are five archive-dependent tests without local originals
and one old-botocore branch in an environment with conditional-write support.
The ignored Rust test is the fixture regeneration helper
`regenerate_declared_abox_fixture`. No ontology runner test was skipped.
Database runtime constraints were not rerun; SQL vocabulary alignment is not
evidence that I7/I12 storage and permission requirements are fully satisfied.
V1 reproduction, cross-review, and S1/S6 remain open as recorded in BLUEPRINT §9.

## Additional baseline findings

`python3 -I -m unittest discover -s tools/ci/tests -v` ran 20 tests with two
failures ([ci-tests.log](ci-tests.log)). Both report the same three existing
dependency-zone findings: the ontology crate's rules-engine dependency and
imports in `packages/ontology/tests/common/mod.rs` and
`packages/ontology/tests/fixture_origin/main.rs`.

The checker, rules, tests, ontology manifest, and affected source files are
byte-identical to HEAD ([hash comparison](baseline-check.log)). These same
findings were already recorded in
[earlier verification](../../../tests/evidence/workflow_pins_round5/RESULTS.md).
This runner setup fix does not change the ontology dependency or relax zone
rules. The additional CI-checker suite is **not green**; the originally reported
full `tools/tests` suite is green.
