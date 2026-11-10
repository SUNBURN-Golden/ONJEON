# Audit 5: registry archival claims and empty access logs

The starting revision already contained the archival-status correction, the
empty-log guard, atomic CSV replacement, unit tests and a dedicated CI step.
This node adds a subprocess CLI regression using disposable copies of the real
registry and verifies that reintroducing either historical defect is detected.
The normalizer and repository registry CSVs are unchanged.

The new test combines all eight legacy `archived` claims with zero-byte and
header-only access logs. Both cases run the actual script twice from outside
its repository root. Each run must report `53 / 16 / 49 / 0` rows, restore the
insurer CSV byte-for-byte to the current canonical registry, preserve the other
two registries and empty log, and leave no temporary CSV. The final comparison
also checks that the repository's four original CSVs have not changed.

All builds and captured logs are in this worktree. Temporary test inputs are
owned and cleaned up by the tests. No real disclosure or R2 requests, GitHub
calls, commits, pushes or production changes were made. GitHub CI execution is
not claimed; its declared registry command was executed locally.

Commands below ran from the repository root with Rust 1.98.1. Cargo used the
worktree-local `target/` directory (the default, or `--target-dir target/onto`
for the ontology runner). The full Python run set
`ONJEON_ONTOLOGY_RUNNER="$PWD/target/onto/debug/ontology-case-runner"`.

| Command / check | Result / evidence |
|---|---|
| `python3 -m unittest discover -s tools/tests -p test_registry_normalize.py -v` | 25 passed, exit 0: [normalizer-tests.log](normalizer-tests.log) |
| `env -u TMPDIR ONJEON_ONTOLOGY_RUNNER="$PWD/target/onto/debug/ontology-case-runner" python3 -m unittest discover -s tools/tests -v` | 1,450 run; 1,444 passed, 6 existing skips, exit 0: [full Python suite](python-tests-os-tmp.log) |
| `python3 tools/evidence/audit5-registry-archived-mislabel/mutation_check.py` | Both defects detected, exit 0: [mutation-tests.log](mutation-tests.log). The archival mutation fails four comparisons (two log forms, two runs); removing the empty-log guard fails both subprocess runs with `IndexError`. Only temporary script copies are mutated. |
| `cargo build --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir target/onto` | Exit 0: [ontology-build.log](ontology-build.log) |
| `cargo test --all --locked --offline` | 513 Rust tests passed, 1 existing ignored test; embedded Python suites of 39 and 129 passed; exit 0: [rust-tests.log](rust-tests.log) |
| `cargo test --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir target/onto` | 4 passed, exit 0: [runner-tests.log](runner-tests.log) |
| Registry suite, vocabulary, validation/self-test, blueprint status/counts, product-purpose mapping, design bundle, ontology, whitespace | Registry suite 51 passed; all checks exit 0; exact commands: [consistency-checks.log](consistency-checks.log) |
| `python3 tools/evidence/audit5-registry-archived-mislabel/scope_check.py` | Changed paths allowed, protected paths untouched, Python parses, local evidence links resolve, normalizer and four registry CSVs match `HEAD` byte-for-byte, `git diff --check` clean: [scope-check.log](scope-check.log), [SHA-256 snapshot](registry-snapshot.json). |

The first full Python invocation set `TMPDIR="$PWD/target/tmp"`. That setting
conflicts with the existing ontology tests requiring temporary mutated rules
outside the repository. That run executed 1,450 tests with 3 failures and 6
existing skips, exit 1: [initial environment failure](python-tests-in-tree-tmp.log).
Removing the
override makes all six tempfile tests pass without code changes:
[tempfile-tests.log](tempfile-tests.log), command
`env -u TMPDIR python3 -m unittest discover -s tools/tests -p test_ontology_check_tempfile.py -v`.
The full suite is also rerun with the default OS temporary directory; its final
result is the passing full-Python-suite row above.

Product mapping: A1, Q7, L0/L1, I6 (evidence preservation foundation), V0/M1,
P01/P02. See the [audit record](../../../docs/blueprint/audits/2026-11-10_registry_archived_mislabel.md)
and its entry in `09_제품목적_대응표.md`. This closes the local registry-tool
finding, not product/document enumeration, verified immutable preservation,
digital twins, consumer UX, P01/P02 as a whole or first-release completion.
