# Audit 1: blueprint vocabulary axis count

Verified on 2026-10-25 in the `audit1-blueprint-axis-count` worktree.

The two references in `docs/BLUEPRINT.md` and
`docs/blueprint/proposals/인계_설계책임/README.md` now omit the hand-written count.
`python3 tools/vocab_check.py --write` generates the count in
`docs/blueprint/VOCABULARY.md` from `packages/schemas/vocabulary.json` (currently
45 axes, 228 values). The check requires the generated document to match exactly,
including its count, and fails on stale counts in contract documents and proposals.

Regression tests cover both repaired references, the committed generated document,
adding an axis, missing/stale/duplicate generated counts, stale prose counts causing
CLI failure, and the per-line opt-out for intentional historical quotations.
Fixtures use temporary files; these tests have no expected failures.

The out-of-scope review file
`docs/review/2026-10-22_audit1_blueprint_axis_count.md` added by an earlier attempt
was removed, restoring that path to the base revision (`bbcdb0b`). Evidence lives
here under the allowed `tools/` path. Protected paths remain identical to the base.

| Command | Result |
|---|---|
| `python3 -m unittest tools.tests.test_blueprint_axis_count tools.tests.test_vocab_check -v` | PASS: 24 tests |
| `python3 -m unittest discover -s tools/tests -v` | PASS: 568 tests run, 6 skipped, no expected failures |
| `python3 tools/vocab_check.py --write` followed by `python3 tools/vocab_check.py` | PASS: 45 axes, 228 values |
| `python3 tools/validation_check.py` | PASS: internal consistency; archived originals not re-verified |
| `python3 tools/validation_check.py --selftest` | PASS: 38 mutations caught for their intended reasons |
| `cargo test --all` | PASS: 388 passed, 0 failed, 1 ignored across Rust result summaries |
| `cargo fmt --all -- --check` | PASS |
| `cargo clippy --all-targets -- -D warnings` | PASS |
| `git diff --check` | PASS |
