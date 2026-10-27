# Audit 2 ontology runner: fix round 2

Local verification on 2026-10-26. Blueprint links: A1/A2/A3, Q7, L6, I2.

The blocking `rules-engine` CI failure came from Python discovery invoking the
runner tests' offline Cargo fallback before any Rust dependency download. The
job now builds the standalone runner with dependency downloads enabled before
discovery and supplies its binary through `ONJEON_ONTOLOGY_RUNNER`, using the
same target path as `design-specs`. Build failures still fail the job; the tests
do not skip a failed offline build.

[Cold-cache evidence](cold-cache-build.log) first reproduces Cargo exit 101
with an empty registry and no prebuilt binary, then successfully builds using
the new CI command with dependency downloads enabled. The exit 101 in this log
is the intentional reproduction of the original failure.

[Full Python discovery](python-tests.log) uses that prebuilt binary and another
empty Cargo home. The verification also asserts that discovery leaves this
second Cargo registry absent. Two additional setup regressions verify that a
prebuilt runner bypasses Cargo entirely and that a failed fallback build raises
an error. The existing seven runner regressions still exercise release/schema
fields and per-job errors through the real binary. Discovery runs 922 tests
without failures, with six existing skips: five need unavailable archived
originals and one targets an old-botocore branch.

Other local checks, with commands and exit codes in each log:

- Workspace [format](workspace-fmt.log), [Clippy](workspace-clippy.log), and
  [tests](workspace-tests.log): all pass; 443 tests pass and one existing doctest
  is ignored.
- Standalone runner [format](runner-fmt.log), [Clippy](runner-clippy.log), and
  [unit tests](runner-unit.log): all pass; three unit tests.
- [Ontology checks](ontology-check.log), [design specification](spec-check.log),
  [vocabulary](vocabulary.log), [validation](validation.log), and
  [validation self-tests](validation-selftest.log): all pass.

These are local reruns of the required workflow checks. GitHub was not called,
and no commit or push was made, per the node instructions. No production or R2
access was exercised.
