# Audit 2 V1 closure decision — fix round 2 merge resolution

Local verification on 2026-10-28. The sole unmerged file was
`tools/tests/test_ontology_runner_io_error.py`. Both branches fixed a mismatch
between Cargo's build directory and the executable launched by Python tests.

The merged setup uses main's `compiler-artifact.executable` discovery, so the
build and launch agree even with target-directory or target overrides. It
preserves the 120-second build deadline, Cargo lock diagnostics, missing
artifact failure, build failure propagation, and prebuilt runner bypass.
This branch's missing/empty `ONJEON_ONTOLOGY_RUNNER` coverage now exercises
each of the default, redirected, and target-specific executable paths.

## Verification

Every log records the command, environment, exit code, and elapsed time.
Builds and temporary files use this worktree; dependencies are offline and
`ONJEON_ONTOLOGY_RUNNER` is unset to exercise fallback setup.
All checks below exited 0.

- [Focused runner regressions](runner-tests.log): 13 tests passed, including
  the actual Cargo lock timeout and both missing/empty override variants.
- [Full Python discovery](python-tests.log): 1,161 tests run, six existing skips,
  no failures. The skips are five unavailable-original cases and one
  inapplicable old-botocore branch.
- [Rust workspace tests](workspace-tests.log), [format](workspace-fmt.log),
  [Clippy](workspace-clippy.log), and [runner unit tests](runner-unit.log):
  458 workspace tests passed, one existing ignored doctest; three runner tests passed.
- [Vocabulary](vocabulary.log), [validation](validation.log),
  [validation mutation tests](validation-selftest.log), [ontology](ontology.log),
  [design specification](spec.log), and [blueprint counts](blueprint-counts.log).

The optional `tools/ci/tests` suite was not rerun; its previously recorded
dependency-baseline failures remain described in the [round 1 evidence](../README.md).
Existing incoming main evidence logs were preserved, including their original
trailing whitespace. Source/document whitespace checks for this resolution pass.

## Evidence boundary

The [V1 closure decision](../../../../docs/decisions/audit2-v1-gate-closure.md)
still requires 14/14 actual reproduction, independent cross-family
ReviewDecision records, and S1/S6 closure before V1 can pass. This merge resolves
test setup only. It does not add private-source reproduction or model review
evidence. No provider, secret, production, GitHub, commit, or push operation
was performed. The merge is left uncommitted for the supervisor.
