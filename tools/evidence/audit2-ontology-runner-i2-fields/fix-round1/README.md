# Audit 2 ontology runner: fix round 1

Local verification on 2026-10-26. Blueprint links: A1/A2/A3, Q7, L6, I2.

The runner emits the engine's `release_id` (including explicit null for fixtures)
and `schema_version` on successful evaluations. Unreadable paths, invalid rules,
and evaluation failures produce ordered per-job error rows and allow later jobs
to run. Invalid batches and input/output failures return exit code 1 without a
panic. The seven runner regression tests cover both schema versions, release
variants, all payout states, mixed batches, malformed jobs, and malformed batches;
three Rust unit tests exercise input/output failures. CI runs both test groups.

The blocking uploader memory failure was intermittent: repeating the original
in-process memory test reproduced a 3,211,994-byte peak against its 3,145,728-byte
limit. A diagnostic snapshot attributed 939 KiB to Python 3.13's
`pathlib/_local.py:274`, which interns path components. Resizing that process-wide
table during measurement depended on allocations from earlier tests.

The memory regression now runs in a fresh isolated Python interpreter, retaining
the original 2 MiB fixture, 3 MiB peak limit, and offline guards. No uploader
runtime behavior or memory allowance changed. The uploader documentation records
the measurement isolation. [Stress evidence](memory-regression.log) contains 100
successful isolated runs and a negative control: holding a second full object
caused the original limit to fail, as expected. The failure in that log belongs
only to this intentional negative control.

Verification logs include the commands and exit codes:

- [Python project tests](python-tests.log): `python3 -m unittest discover -s tools/tests -v`; 920 tests, zero failures, six existing skips.
- [Runner regressions](runner-regressions.log): seven tests, using the built runner through `ONJEON_ONTOLOGY_RUNNER` as CI does.
- [Runner unit tests](runner-unit.log): three tests; [build](runner-build.log), [format](runner-fmt.log), [clippy](runner-clippy.log).
- [Workspace tests](workspace-tests.log): `cargo test --offline --all`; [format](workspace-fmt.log), [clippy](workspace-clippy.log).
- [Ontology checks](ontology-check.log): 11/11 questions, 15/15 constraint self-tests, 25/25 release/document-model tests.
- [Vocabulary](vocabulary.log), [validation](validation.log), [validation self-tests](validation-selftest.log), [design specification](spec-check.log).

The Python suite's existing six skips concern unavailable archived originals
(five tests) and an old-botocore branch in a current-botocore environment (one).
These checks do not establish production readiness or exercise live R2 access.

Supplemental check: `python3 -I -m unittest discover -s tools/ci/tests -v`
ran 20 tests, with two existing failures ([log](ci-checker-tests.log)). Both
assert that the repository passes dependency-zone checks. They report the
`packages/ontology` test dependency on `onjeon-rules-engine` and its two test
imports crossing from knowledge to twin. The dependency rule, checker, checker
tests, ontology manifest, and both ontology test files are unchanged from HEAD
(`git diff --quiet HEAD -- infra/ci/deps.json tools/ci/check_deps.py
tools/ci/tests/test_ci_checkers.py packages/ontology/Cargo.toml
packages/ontology/tests/common/mod.rs packages/ontology/tests/fixture_origin/main.rs`
returned 0). That separate suite is not in this node's required CI workflow;
this runner/uploader fix does not change the zone policy or ontology dependency.
