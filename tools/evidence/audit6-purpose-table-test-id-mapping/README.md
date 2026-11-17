# Audit 6: purpose table test ID mapping evidence

Verified locally on 2026-11-17 in worktree `audit6-purpose-table-test-id-mapping`.
Base HEAD and edited source hashes are in [source-hashes.log](source-hashes.log).
No commit, push, GitHub call, external service operation or decision change was made.

The [audit record](../../../docs/blueprint/audits/2026-11-17_purpose_table_test_id_mapping.md)
explains the changes: P06 now references the existing service loader owner T-KN-04,
and T-AP-09 registers `no-composite-score` with a test description and completion
criterion. 03 and 09 §6 agree with the task contract. Audit 3 already supplied
T-MB-04/T-AP-07's first-view and non-hidden-condition registrations and T-AP-08's
non-hidden-condition registration; all remain covered by regression tests.

| Command / check | Result | Log |
|---|---|---|
| New live P06/P17 regression before the repair (`python3 -I -m unittest discover -s tools/tests -p test_product_purpose.py -k live_p06_and_p17 -v`) | Expected exit 1, two failures: P06 omits T-KN-04; T-AP-09 omits `no-composite-score` | [before.log](before.log) |
| Current guard against temporary copies of HEAD's original tasks.json and 09 (`--tasks` / `--purpose`) | Expected exit 1, exactly one `PURPOSE-OWNER` and one `PURPOSE-ROW-OWNER` finding; repository files unchanged by this check | [baseline-guard.log](baseline-guard.log) |
| `python3 -I -m unittest discover -s tools/tests -p test_product_purpose.py -v` | Exit 0, 20 tests | [regression.log](regression.log) |
| `python3 -m unittest discover -s tools/tests -v` | Exit 0; 1,677 tests, 1,671 passed and six environment-dependent skips | [python.log](python.log) |
| `python3 -I tools/ci/check_product_purpose.py` and `--selftest` | Exit 0; five deliberate violations caught by their intended rules, one clean case | [checks.log](checks.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | Exit 0; 46/46 machine checks, 72/72 presence checks | [spec.log](spec.log) |
| `python3 tools/vocab_check.py`, `python3 tools/validation_check.py` and validation `--selftest` | All exit 0; 40 validation mutations rejected | [checks.log](checks.log) |
| `cargo test --all --locked --offline` | Exit 0; 532 passed, one existing ignored test; embedded Python suites of 39 and 129 tests passed | [cargo.log](cargo.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | Exit 0; four tests passed | [ontology.log](ontology.log) |
| `git diff --check` | Exit 0 | [checks.log](checks.log) |

The product-purpose regression mutates every required task/ID pair independently,
retaining the ID on another task and in descriptive fields. It also removes P06/P17's
owner references while leaving their tasks registered. An independent live matrix
checks the affected task registrations and test descriptions, plus 03's required IDs
and completion criteria. Existing Python CI discovery runs these tests.

The six Python skips are existing environment-dependent cases: five require local
archived originals (and, for reproduction, `pdftotext`), and one requires an old
botocore without conditional-put support. The installed botocore supports it.

These are static task/specification checks and local fixture regressions. They do
not execute the planned UI acceptance tests, demonstrate real-data accuracy, close
any product-purpose row, or establish release readiness.
