# Audit 6: observation core fields override extra metadata

`put_observation` now builds `{**extra, **core}`. Existing reserved-key rejection
in the function and CLI remains in place. Serialization preserves the historical
core-first field order, so immutable observations with normal extra metadata
remain byte-identical and return `already_present` on rerun.

Two added tests isolate merge precedence by bypassing only reserved-key validation
and check compatibility with a pre-existing serialized observation. The merge
test tries all seven provenance fields independently, including a valid SHA-256
and key for another object actually present in the temporary archive. It checks
the final record, referenced bytes, digest and unchanged input metadata.

## Fix round 1 (2026-11-15): stale shared-target artifacts, no source change

The supervisor's local gate reported four `loader_tightening` failures
(`duplicate_top_level_members…`, `duplicate_nested_members…`,
`duplicate_keys_are_compared…`, `example_kind_rejects_wrong_types…`).
Reproduced in this worktree: the test binary loaded rules that the source at
HEAD rejects. `packages/rules-engine/src/strict_json.rs` and `rule.rs` were
unmodified and already contained the duplicate-key and `example_kind`
validation, and `cargo test` finished without recompiling. The environment sets
`CARGO_TARGET_DIR=/workspace/onjeon-run/shared-target` for every worktree; the
deps directory held a 0-byte `libloader_tightening-*.rmeta` and a test binary
built by a concurrent session, and the round-0 rust log itself records
"Blocking waiting for file lock on build directory". The cached test binary was
stale against the current library source.

Resolution: `cargo clean -p onjeon-rules-engine` (removed 6,234 files) and a
fresh build. All six `loader_tightening` tests then passed without any source
change. No Rust or Python behavior was modified in round 1; the merge fix and
its two regression tests are unchanged from round 0. All suites below were
re-run after the clean rebuild on 2026-11-15 and their logs replaced.

## Commands and results

Round 0 (2026-11-14), kept as the before/after record of the fix itself:

| Command | Result / evidence |
|---|---|
| Before implementation: `python3 -m unittest tools.tests.test_source_archive.Observations -v` | Expected exit 1: 8 tests, failures in all 7 forged-field subcases; [before.log](before.log). The CLI's existing rejection layer was deliberately bypassed only in the new merge test. |

Fix round 1 (2026-11-15), after `cargo clean -p onjeon-rules-engine`:

| Command | Result / evidence |
|---|---|
| `cargo test -p onjeon-rules-engine --test loader_tightening --locked --offline` | First run reproduced the 4 reported failures on the stale binary; after the clean rebuild, 6 passed, exit 0. |
| `python3 -m unittest discover -s tools/tests -p 'test_source_archive*.py' -v` | 74 passed, no skips, exit 0: [archive-tests.log](archive-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,611 run, 1,605 passed, 6 existing skips, exit 0: [python-tests.log](python-tests.log) |
| `cargo test --all --locked --offline` | 532 Rust tests passed, 1 existing ignored, exit 0: [rust-tests.log](rust-tests.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4 passed, exit 0: [runner-tests.log](runner-tests.log) |
| Vocabulary, validation/self-test, design bundle and product-purpose checks | All exit 0; exact commands: [static-checks.log](static-checks.log) |
| `cargo fmt --all -- --check`, `cargo clippy --locked --all-targets --offline -- -D warnings`, `python3 -I tools/blueprint_counts.py`, `python3 -I tools/check_tracked_secrets.py`, workflow pins, daemon dry run (`--scenario all --require-all`), `ontology_check.py` with the built runner | All exit 0 (CI-equivalent local gate). |
| Allowed paths, Python parsing, local Markdown links and whitespace | Passed: [scope-checks.log](scope-checks.log). Verbatim `.log` output keeps its original trailing whitespace, matching existing committed evidence logs. |

Five existing Python skips require private local archived originals (three also
require `pdftotext`). The sixth tests an older botocore without conditional PUT
support; the installed version supports it. All new tests ran without skips.

Product mapping: A1, Q7, L1, I6, M1, P02/P03. See the
[audit record](../../../docs/blueprint/audits/2026-11-14_archive_observation_extra_override.md)
and its entry in `09_제품목적_대응표.md`. These are local archive-tool regression
results using temporary stores and mocked services. Actual disclosure acquisition,
R2 observation reconciliation, product twins, consumer screens and first-release
completion remain separate requirements.
