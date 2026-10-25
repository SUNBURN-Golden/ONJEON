# Audit 1: blueprint vocabulary axis count

Fix round 3, verified on 2026-10-25 in the `audit1-blueprint-axis-count` worktree.

Branch HEAD was `98f950b16a444f769fc37c25d2a22ad70e496bb8`. The locally available
target `origin/main` at `d88700be6a9f95a4934d849b88988823803792b3` was merged with
`git -c core.hooksPath=/dev/null merge --no-commit --no-ff origin/main`.
No commit, push, fetch or GitHub call was made. The merge remains uncommitted for
the supervisor. All incoming paths are allowed; protected paths match both parents.

The automatic text merge reproduced the CI failure: the generated document
included the target's new axes but retained `전체 45개 축.`. The vocabulary check
reported `axis count [45], vocabulary.json has 49`, and three artifact regression
tests failed ([before.log](axis-count-round3/before.log)). Regenerating with the
merged vocabulary fixes the mismatch; the vocabulary itself was not rewritten.

The two references in `docs/BLUEPRINT.md` and
`docs/blueprint/proposals/인계_설계책임/README.md` now omit the hand-written count.
`python3 tools/vocab_check.py --write` generates the count in
`docs/blueprint/VOCABULARY.md` from `packages/schemas/vocabulary.json` (currently
49 axes, 269 values). The check requires the generated document to match exactly,
including its count, and fails on stale counts in contract documents and proposals.

Regression tests cover both repaired references, the committed generated document,
adding an axis, missing/stale/duplicate generated counts, stale prose counts causing
CLI failure, and the per-line opt-out for intentional historical quotations.
The new CLI regression recreates the merged 45/49 mismatch in a temporary repository,
checks that validation fails without changing either file, and verifies that
`--write`, check, then `--write` all succeed with identical generated content and
unchanged vocabulary JSON. It uses the real loader, validator, renderer and linter.
Fixtures use temporary files; these tests have no expected failures.

The following are local executions of both jobs in `.github/workflows/ci.yml`,
not a claim of a hosted CI run. Logs are in [axis-count-round3/](axis-count-round3/).

| Command | Result |
|---|---|
| `python3 -m unittest tools.tests.test_blueprint_axis_count tools.tests.test_vocab_check -v` | PASS: 25 tests |
| `python3 -m unittest discover -s tools/tests -v` | PASS: 790 tests run, 6 skipped, no expected failures |
| `python3 tools/vocab_check.py --write` followed by `python3 tools/vocab_check.py` | PASS: 49 axes, 269 values |
| `python3 tools/validation_check.py` | PASS: internal consistency; archived originals not re-verified |
| `python3 tools/validation_check.py --selftest` | PASS: 38 mutations caught for their intended reasons |
| `cargo test --all` | PASS: 402 passed, 0 failed, 1 ignored across Rust result summaries |
| `cargo fmt --all -- --check` | PASS |
| `cargo clippy --all-targets -- -D warnings` | PASS |
| `cargo build --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir target/axis-count-round3-ontology` | PASS |
| `python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py "$PWD/target/axis-count-round3-ontology/debug/ontology-case-runner"` | PASS: questions 11/11, constraint self-tests 15/15, release/document tests 25/25 |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | PASS: machine checks 44/44, existence checks 72/72 |
| `git diff origin/main --check` | PASS: node changes relative to the merged target |

The target vocabulary also passes `additive_since` against the pre-merge branch
vocabulary: +4 axes and +41 values, version 1.6.0 → 1.7.0, with no existing
definitions removed or changed. Archived originals were not re-verified.
