# Audit 5: ontology checker temporary rule isolation

2026-11-10, node `audit5-ontology-check-tmp-in-tree`.
[Finding and scope](../../../docs/blueprint/audits/2026-11-10_ontology_check_tmp_in_tree.md).
All commands run from this worktree's root with Rust 1.98.1 and Python 3.
No external services, credentials, commit, push or GitHub calls are needed.

| Command | Evidence |
|---|---|
| `cargo build --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir target` | [runner-build.log](runner-build.log), exit 0 |
| `python3 -B -m unittest discover -s tools/tests -p test_ontology_check_tempfile.py -v` | [focused-tests.log](focused-tests.log), 6 passed |
| `ONJEON_ONTOLOGY_RUNNER="$PWD/target/debug/ontology-case-runner" python3 -B -m unittest discover -s tools/tests -v` | [python-tests.log](python-tests.log), exit 0; 1,449 run, 0 failures, 6 existing skips |
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | [workspace-tests.log](workspace-tests.log), 513 passed, 1 existing ignored doctest |
| `cargo test --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir target` | [runner-tests.log](runner-tests.log), 4 passed |
| `python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py "$PWD/target/debug/ontology-case-runner"` (two simultaneous processes) | [concurrent-check.json](concurrent-check.json), both exit 0, byte-identical stdout, rule files unchanged; [ontology-check.log](ontology-check.log) contains the common output |
| Design bundle, product purpose, BLUEPRINT counts/status, whitespace checks | [checks.json](checks.json), all exit 0; commands and individual logs included |

The baseline regression executes only HEAD's `with_bad_rule` function, extracted
with `ast` from read-only `git show`, in memory with the current module globals.
The new path regression fails on the old relative repository path as expected
([baseline-regression.log](baseline-regression.log)); the old function's `finally`
still runs to delete its temporary file. The fixed helper passes all six tests.

The concurrency regression uses a barrier to keep both files live, writes distinct
markers and verifies each caller reads its own marker before either cleans up.
The SIGKILL regression waits until a child has written its mutation, kills it,
and compares the rule directory's complete file names and bytes. A parent-owned
OS temporary directory removes that deliberately killed child's residue afterward.
SIGKILL cannot promise automatic deletion in OS temporary storage.

The full checker was also launched twice before waiting for either process. The
verification captured both stdout/stderr streams, required zero exits and empty
stderr, compared stdout byte for byte, compared all rule-directory file names and
bytes with the pre-run snapshot, and required `규칙/_tmp_bad.json` to be absent.
The common output passes questions 11/11, constraints 15/15, release/document
tests 25/25 and amount tests 10/10.

Existing reader `ResourceWarning`s in `ontology_check.py` may appear under unittest;
this change closes the source reader in the changed helper and does not refactor
other readers. These are local fixture/tool checks, not product launch evidence.
Five Python skips require locally archived originals; the sixth applies only to
old botocore versions without conditional put support.
