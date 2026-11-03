# Audit 4: registry normalization tests and atomic CSV replacement

`tools/registry_normalize.py` now leaves zero-byte and header-only access logs
unchanged and returns zero. Both normalization paths write a temporary CSV in
the destination directory, preserve file permissions, flush and fsync it, close
it, then publish with `os.replace`. Partial write, sync and replacement failures
propagate while retaining the original bytes and removing the temporary file.
Atomicity applies to each CSV separately; there is no four-file transaction or
directory fsync guarantee for power loss.

Tests, CI discovery and safe handling of a missing `disclosure_access` column
already existed at the starting revision. The additional missing-column test
uses a populated disclosure URL with missing, reachable or denied home access;
it preserves the distinction between unqueried, failed and blocked, records the
missing disclosure entry, and checks idempotence. A dedicated stdlib-only CI
step now runs this suite before installing dependencies or building Rust.

All commands ran locally in this worktree, using the installed Rust 1.98.1 and
boto3 1.43.100. Tests use disposable CSVs, local fixtures and loopback services;
the repository registry CSVs were not normalized or edited. No GitHub request,
commit, push, real R2 request or production change was made.

| Command / check | Result and evidence |
|---|---|
| Baseline behavior from read-only `git show HEAD:tools/registry_normalize.py`, compiled with the live module path for vocabulary lookup | Three current disposable CSV tests run against the baseline module: three empty-log subcases raise `IndexError`, both partial-write subcases detect damaged originals, missing-column test passes. Expected 2 failures / 3 errors: [baseline-behavior.log](baseline-behavior.log) |
| `python3 -m unittest discover -s tools/tests -p test_registry_normalize.py -v` (exact CI command) | 24 passed, exit 0: [normalizer-tests.log](normalizer-tests.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_registry*.py' -v` | 46 passed, exit 0: [registry-tests.log](registry-tests.log) |
| `cargo build --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir target/onto` | Exit 0, before full Python discovery: [ontology-build.log](ontology-build.log) |
| `ONJEON_ONTOLOGY_RUNNER="$PWD/target/onto/debug/ontology-case-runner" python3 -m unittest discover -s tools/tests -v` | 1,350 run; 1,344 passed, 6 existing skips, no failures/errors, exit 0: [python-tests.log](python-tests.log) |
| `cargo test --all --locked --offline` | 491 passed, 1 existing ignored test, no failures, exit 0; embedded Python suites 39 and 129 passed: [rust-tests.log](rust-tests.log) |
| `cargo test --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir target/onto` | 3 passed, exit 0: [runner-tests.log](runner-tests.log) |
| Workflow, vocabulary, validation and its self-test, blueprint status/counts, product-purpose mapping, design bundle spec, whitespace | All exit 0; exact commands: [static-checks.log](static-checks.log) |
| Final allowed/protected path checks, Python parsing, new local documentation links and whitespace | [scope-check.log](scope-check.log) |

The baseline run selects `RegistryCsv.test_empty_access_log_is_unchanged`,
`RegistryCsv.test_partial_write_failure_preserves_original_and_cleans_temporary_file`
and `RegistryCsv.test_missing_disclosure_access_does_not_claim_reachable_or_archived`
from the current test module, replacing only its `rn` binding with the baseline
module inside that process. The failing baseline log is intentional evidence.
The current implementation passes every new test. The full suite skips five
tests requiring private local archive inputs and one old-botocore test because
the installed version supports conditional PUT. GitHub CI execution is not
claimed; the declared CI command was run locally.

## Fix round 1: stale shared-target Rust artifacts

The reported `fixture_supplements` failure was environmental, not a source
regression. The shared `CARGO_TARGET_DIR` reused a test binary compiled in a
since-deleted review worktree (`/workspace/onjeon-run/wt/_review_2026331_91631817`),
so `env!("CARGO_MANIFEST_DIR")` at runtime pointed at a missing
`tests/fixtures/cases` directory. Touching the local Rust sources invalidated
the stale fingerprints and rebuilt the artifacts against this worktree; no
tracked file content changed. Re-run results: `cargo test --all --locked
--offline` → 491 passed, 0 failed, 1 ignored; `python3 -m unittest discover -s
tools/tests -v` → 1,350 run, 1,344 passed, 6 skipped, 0 failures.

Product mapping: A1, Q7, L0/L1, I6 (evidence preservation foundation), V0/M1,
P01/P02. See the [audit record](../../../docs/blueprint/audits/2026-11-03_registry_normalize_tests.md)
and its entry in `09_제품목적_대응표.md`. This is registry-tool regression evidence;
it does not close real product/document enumeration, disclosure acquisition,
digital twins, consumer UX or first-release completion.
