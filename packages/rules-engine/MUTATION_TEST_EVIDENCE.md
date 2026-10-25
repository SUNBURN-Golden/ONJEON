# Audit 1 mutation test evidence

## Fix round 2 — fixture path scope (2026-10-25)

The reported out-of-scope edit to
`packages/fixtures/rules/real/kyobo-small-cancer-skin.cases.json` is removed.
All seven shared case files changed by this node now match merge parent
`8d6db8673bb44423cfc38b63b795404dfa2e0d6d` byte-for-byte. The complete
`packages/fixtures/rules` directory has zero diff against that parent.
The 59 added boundary cases moved into the allowed
`packages/rules-engine/tests/fixtures/cases/` directory; combining each shared
file and its supplement reproduces the pre-relocation case table exactly.
See [fixture scope and preservation checks](evidence/scope-round2-fixtures.log).

The common test loader appends supplemental cases while preserving the shared
base inputs and rule metadata, and rejects duplicate IDs against the shared
cases or within a supplement. Golden, mutation, soundness, and real-clause tests
all use the extended tables. Four regression tests cover preservation of the
shared tables, base-input inheritance and per-case overrides, and both duplicate
ID failures. A mutation negative control confirms that the six shared Kyobo skin
cases miss 16 mutants that its eleven local boundary cases kill.

Mutation coverage is unchanged: 120 cases across eight rules kill all 336
loadable generated mutants; zero survivors and zero equivalence exceptions.
The eleven hand-written mutants also remain killed. The per-rule counts in the
historical table below still apply.

| Command | Result |
|---|---|
| `cargo test -p onjeon-rules-engine --test fixture_supplements --test mutation --test golden --test real_clauses --test soundness -- --nocapture` | Pass: 29 tests, including 7 mutation tests and 4 supplement tests |
| `cargo test --all` | Pass: 398 Rust tests including 3 doc tests; 1 existing ignored fixture-regeneration test; embedded Python suites also pass |
| `cargo fmt --all -- --check` | Pass |
| `cargo clippy --all-targets -- -D warnings` | Pass |
| `python3 -m unittest discover -s tools/tests -v` | Pass: 568 tests, 562 passed and 6 existing skips |
| `python3 tools/vocab_check.py` | Pass: 45 axes, 228 values |
| `python3 tools/validation_check.py` | Pass: 14 samples internally consistent; originals not re-verified |
| `python3 tools/validation_check.py --selftest` | Pass: 38 tampering cases caught |
| Ontology runner build (`--locked`) and `ontology_check.py` | Pass: 11/11 questions, 15/15 constraint self-tests, 25/25 release/document-model tests |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | Pass: 44/44 machine checks, 72/72 existence checks |

Logs: [focused tests and mutation counts](evidence/scope-round2-focused.log),
[workspace tests](evidence/scope-round2-workspace.log),
[Python tools tests](evidence/scope-round2-python.log),
[Clippy](evidence/scope-round2-clippy.log),
[ontology](evidence/scope-round2-ontology.log).
Toolchain: rustc/cargo 1.98.1, Python 3.13.5.
No commits, pushes, or GitHub calls were made.

---

## Historical verification — merge with main

Executed locally on 2026-10-25 while resolving the merge of
`8d6db8673bb44423cfc38b63b795404dfa2e0d6d` into branch HEAD
`0b0326d518fcc8f814edc98584cef147c15f3d3e`.
Toolchain: rustc/cargo 1.98.1, Python 3.13.5, boto3 1.43.100.

The README conflict now retains the generic mutation coverage and main's pinned
trace/hash coverage, rule-0.2 tests, overflow tests, and immutable-rule checks.
The first `cargo test --all` exposed two integration failures: main pinned 14
synthetic cases while this branch has 15, so the rounding case had no trace or
input hash pin. The shared fixture paths are outside this node's allowed edits.
A supplemental pin in
`tests/fixtures/fixture-rule-001.rounding.golden.json` now covers
`t15_rounding_floor_vs_half_even`; the golden tests combine both pin files,
reject duplicate IDs, and require exactly the set of cases being exercised.
The existing shared pins and real-rule content hash checks are retained.

For the added case, 1003 × 0.5 floors to 501 KRW, whereas half-even produces
502 KRW. Its trace was derived from the existing 1001 KRW rounding case with
the changed input/result, and its snapshot hash was calculated independently
with Python SHA-256 over the engine's sorted `name=value\n` format.
Changing either the supplemental trace result to 502 KRW or its snapshot hash
to zeros makes `golden_table_pins_trace_and_hashes` fail specifically for this
case; restoring the pin returns all seven golden tests to passing.
See [pin negative controls](evidence/merge-main/pin-controls.log).

## Current verification

| Command | Result |
|---|---|
| `cargo test -p onjeon-rules-engine --test mutation -- --nocapture` | Pass: 6 tests; 336 generated mutants over 8 rules, zero survivors, zero equivalence entries; 11 hand-written mutants also killed |
| `cargo test --all` | Pass: 393 Rust tests including 3 doc tests; 1 existing ignored fixture-regeneration test; embedded Python codegen/API suites also pass |
| `cargo fmt --all -- --check` | Pass |
| `cargo clippy --all-targets -- -D warnings` | Pass |
| `python3 tools/vocab_check.py` | Pass: 45 axes, 228 values |
| `python3 tools/validation_check.py` | Pass: 14 samples internally consistent; originals not re-verified |
| `python3 tools/validation_check.py --selftest` | Pass: 38 tampering cases caught |
| `python3 -m unittest discover -s tools/tests -v` | Pass: 568 tests, 562 passed, 6 existing skips; no errors (including the three formerly socket-blocked R2 tests) |
| `cargo build --locked --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir target/merge-main-onto` | Pass |
| `python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py target/merge-main-onto/debug/ontology-case-runner` | Pass: 11/11 questions, 15/15 constraint self-tests, 25/25 release/document-model tests |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | Pass: 44/44 machine checks, 72/72 existence checks |

Logs: [workspace tests](evidence/merge-main/cargo-test.log),
[mutation counts](evidence/merge-main/mutation.log),
[Python tools tests](evidence/merge-main/python-tests.log),
[Clippy](evidence/merge-main/clippy.log),
[ontology build](evidence/merge-main/ontology-build.log),
[ontology checks](evidence/merge-main/ontology.log).

No unmerged index entries remain. The merge is left uncommitted for the
supervisor. Hosted CI was not triggered or inspected; this task prohibits
GitHub access, commits, and pushes.

---

## Historical verification — fix round 5

Executed locally on 2026-10-21, starting from `126cfbd` (fix round 4).
This round re-runs the existing checks for the reported `CI FAIL:no-ci-runs`;
no rule, mutator, test, or workflow behaviour was changed.
Toolchain: rustc/cargo 1.98.1, Python 3.13.5,
boto3 1.43.100 (the version pinned by CI).

The generic mutators already cover the synthetic fixture and every rule loaded
from `packages/fixtures/rules/real`. The harness fails when any rule generates
zero mutants and prints the per-rule counts so coverage is visible in test
output. The mutators include comparator flips, literal ±1 changes,
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
| `cargo build --locked --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir /tmp/audit1-round5-onto` | Pass |
| `python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py /tmp/audit1-round5-onto/debug/ontology-case-runner` | Pass |
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
The existing `.github/workflows/ci.yml` already runs `cargo test --all` (including
the mutation integration test) on pull requests and on pushes to `main` or
`claude/**`. No workflow change is needed to include these tests. Resolving
`no-ci-runs` requires the supervisor to obtain a run for the submitted revision;
changing the local test implementation cannot create that hosted run.
