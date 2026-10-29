# Audit 3 decision ID migration — merge resolution, fix round 2

2026-10-29. Resolved the conflicts in BLUEPRINT and the decision ledger while preserving both merge parents' intents. The original 19 directions retain their `BP-D-xx` identifiers and unchanged content. Main's ADR-0019 limited adoption becomes `BP-D-20`, with an additional legacy mapping and updated audit reference. Execution gate identifiers and DEC filenames remain unchanged. BLUEPRINT retains the limited adoption text and migration evidence; its generated index now covers 37 ADR/DEC files.

The regression suite now checks all 20 directions, mappings and references, including the twentieth decision's adoption limits and evidence requirements. Log output has trailing whitespace normalized, including three lines in the incoming validation self-test log; historical results are preserved.

Validation run from this worktree:

- [Merge integrity](merge-integrity.log): original 19 rows unchanged; all 20 incoming rows preserved except identifier normalization; incoming adoption sections, task contracts and ADR retained; forbidden documents unchanged.
- [Decision regressions](decision-records.log): 20 tests passed (`python3 -B tools/tests/test_decision_records.py`).
- [Full Python suite](python-tests.log): 1,291 tests run, 1,285 passed, 6 skipped, no failures (`CARGO_TARGET_DIR="$PWD/target" ONJEON_ONTOLOGY_RUNNER="$PWD/target/onto/debug/ontology-case-runner" python3 -B -m unittest discover -s tools/tests -v`). Skips concern unavailable archived originals and the old-botocore compatibility case. The existing local ontology runner was used.
- [Rust workspace](rust-tests.log): 475 passed, 1 ignored, no failures (`CARGO_TARGET_DIR="$PWD/target" cargo test --all`).
- [Format](cargo-fmt.log) and [Clippy](cargo-clippy.log): `cargo fmt --all -- --check` and `cargo clippy --all-targets -- -D warnings` passed.
- [Decision index](blueprint-status.log), [inventory](blueprint-counts.log), [vocabulary](vocabulary.log), [validation](validation.log) and [tamper self-test](validation-selftest.log): corresponding `tools/blueprint_status.py`, `tools/blueprint_counts.py`, `tools/vocab_check.py` and `tools/validation_check.py` checks passed; the self-test used `--selftest`.
- [Design specification](spec-check.log): `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` passed.
- [Final scope and merge state](scope-check.log): allowed paths only, no unmerged index entries, no whitespace errors. The merge remains uncommitted for the supervisor.

These checks establish document and repository consistency; they do not authorize operational access or establish product completion.
