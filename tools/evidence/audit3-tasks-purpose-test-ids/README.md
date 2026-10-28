# Audit 3: tasks-purpose-test-ids evidence

Verified locally on 2026-10-29 in worktree `audit3-tasks-purpose-test-ids`, based on `4111455`. No commit or push was made.

The [audit record](../../../docs/blueprint/audits/2026-10-29_tasks_purpose_test_ids.md) explains the five repaired task/ID pairs. `tasks.json`, 03 and 09 agree on the assignments. The existing CI Python discovery executes the updated guard tests; no workflow changes are needed.

| Command | Result | Log |
|---|---|---|
| `python3 -I tools/ci/check_product_purpose.py` before repairing tasks.json | Exit 1, exactly five `PURPOSE-OWNER` findings | [before.log](before.log) |
| `python3 -I -m unittest discover -s tools/tests -p test_product_purpose.py -v` | Exit 0, 17 tests | [regression.log](regression.log) |
| `python3 -I tools/ci/check_product_purpose.py` | Exit 0, all assigned owners registered | [checks.log](checks.log) |
| `python3 -I tools/ci/check_product_purpose.py --selftest` | Exit 0, four violations caught by the intended rule and one clean case | [checks.log](checks.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | Exit 0, 45/45 machine checks and 72/72 presence checks | [checks.log](checks.log) |
| `python3 tools/vocab_check.py` | Exit 0 | [checks.log](checks.log) |
| `python3 tools/validation_check.py` and `--selftest` | Exit 0, 38 mutations rejected for the intended reason | [checks.log](checks.log) |
| `CARGO_TARGET_DIR="$PWD/target" cargo test --all` | Exit 0, 474 Rust tests passed, one existing ignored test; nested Python suites: 39 and 129 passed | [cargo.log](cargo.log) |
| `CARGO_TARGET_DIR="$PWD/target/onto" cargo build --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml` | Exit 0, local runner built for Python regressions | [ontology-build.log](ontology-build.log) |
| `ONJEON_ONTOLOGY_RUNNER="$PWD/target/onto/debug/ontology-case-runner" CARGO_TARGET_DIR="$PWD/target" python3 -m unittest discover -s tools/tests -v` | Exit 0, 1,280 tests: 1,274 passed, six skipped | [python.log](python.log) |
| `git diff --check` | Exit 0 | [checks.log](checks.log) |

The six Python skips are existing environment-dependent cases: five require local archived originals (and, for reproduction, `pdftotext`), and one tests an old botocore without conditional-put support. The installed botocore supports conditional put. The one Rust ignored test is unchanged. Source SHA-256 values for the checker, regression tests and edited bundle files are recorded in `checks.log`.

The regression suite checks every one of the 18 required task/ID assignments by removing its ID while retaining it on another task. Descriptions in `tests` and `done_criteria` cannot replace registration. It also rejects a missing owner task, removal of each of nine IDs globally, and dangling tasks in every P01–P19 row. An independent UX matrix checks the live assignments and test descriptions, and compares 03's IDs and completion criteria against JSON.

These are static registration and specification regression checks. They do not execute the planned product UI acceptance tests or establish P15/P16 or release completion. No production, spending, legal or secret decision was needed.
