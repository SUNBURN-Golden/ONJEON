# Audit 1 DSL vocabulary — merge repair, round 2

Verified on 2026-10-25 in the resolved merge tree:

- Node parent: `9ec9db46664288d1dd6d3004646e1590f62b53b2`.
- Incoming main (`MERGE_HEAD`): `98c24ce8fd93f677e1c640c0073815301a16ccf3`.
- The sole unmerged file was `packages/rules-engine/README.md`. Both parents' explanatory paragraphs are preserved verbatim: the node's DSL vocabulary registration and main's mutation coverage, supplementary fixtures, and evidence link.
- The four vocabulary axes and their existing regression tests remain intact. No engine behavior changed in this repair.

Commands run against the resolved tree (all exited 0):

| Command | Result |
|---|---|
| `cargo test -p onjeon-rules-engine --test vocabulary` | 8 passed. Includes exact input-type, rounding, duration-unit, and operator sets; loader acceptance/rejection; and rule-0.2 version restrictions. |
| `cargo test --all` | 402 passed, 0 failed, 1 ignored across 56 result groups. The ignored test is the existing `regenerate_declared_abox_fixture` helper. Embedded Python suites also passed (39 and 129 tests). |
| `cargo fmt --all -- --check` | Passed. |
| `cargo clippy --all-targets -- -D warnings` | Passed. |
| `python3 -m unittest discover -s tools/tests -v` | 764 run, 6 skipped, no failures or errors. |
| `python3 tools/vocab_check.py` | 49 axes, 269 values; generated vocabulary document current. |
| `python3 tools/validation_check.py` | Internal consistency passed for 14 samples; archived originals were not re-verified. |
| `python3 tools/validation_check.py --selftest` | All 38 mutations caught for their intended reasons. |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 44/44 machine checks and 72/72 presence checks passed. |
| `cargo build --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir target/audit1-vocab-ontology` | Runner built. |
| `python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py target/audit1-vocab-ontology/debug/ontology-case-runner` | 11/11 questions, 15/15 constraint self-tests, 25/25 release/document-model tests; all passed. |
| `git diff MERGE_HEAD --check -- packages/rules-engine/README.md` | No whitespace errors in the resolution. |

The six Python skips cover unavailable archived originals (five tests) and an old-botocore compatibility test that does not apply to the installed version (one test).

`git diff --name-only --diff-filter=U` returned no paths after staging the README resolution. The merge is left uncommitted for the supervisor. No protected files were edited.
