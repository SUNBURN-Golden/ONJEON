# Audit 2 V1 closure decision — fix round 1

Local verification on 2026-10-28. This node records the concrete V1 closure
path; V1 remains open. No private archive, provider API, secrets, GitHub,
commit, push, or production access was used.

## Blocking runner failure

The environment sets `CARGO_TARGET_DIR` to a shared build directory. The
Python runner tests built there but launched the hard-coded runner-local
`target/debug/ontology-case-runner`. [Before](runner-before.log): nine tests,
18 errors, including the reported missing binary and cascading `IndexError`.

The fallback now supplies an absolute, worktree-local `--target-dir` matching
the executable path. An empty `ONJEON_ONTOLOGY_RUNNER` uses that fallback too.
An explicit prebuilt runner still bypasses Cargo, and a failed build still
fails setup. The added regression checks missing/empty prebuilt overrides
with a conflicting Cargo target directory. The seven existing real-binary
regressions continue to check batch errors, continuation, schema/release
fields and hashes.

Both focused runs passed all ten tests:

- [Normal environment](runner-after.log): `python3 -m unittest discover -s tools/tests -p test_ontology_runner_io_error.py -v`.
- [Empty override](runner-empty-override.log): the same command with `ONJEON_ONTOLOGY_RUNNER=''`.

## Project checks

Each named check log records its command and exit code. Rust workspace checks
used `CARGO_TARGET_DIR=$PWD/target` to keep generated artifacts in this worktree.

| Check | Result |
|---|---|
| [Python discovery](python-tests.log), `python3 -m unittest discover -s tools/tests -v` | 1,158 run, six existing skips, no failures (exit 0) |
| [Rust workspace tests](workspace-tests.log), `cargo test --offline --all` | 458 passed, one existing ignored doctest |
| [Runner unit tests](runner-unit.log) | 3 passed |
| [Workspace format](workspace-fmt.log), [Clippy](workspace-clippy.log) | Exit 0 |
| [Vocabulary](vocabulary.log), [validation](validation.log), [validation self-tests](validation-selftest.log) | Exit 0 |
| [Ontology](ontology.log), [design specification](spec.log), [blueprint counts](blueprint-counts.log) | Exit 0 |

The six Python skips are five private-archive checks without local originals
and one old-botocore branch that does not apply to the installed version.

The supplemental `python3 -I -m unittest discover -s tools/ci/tests` run has
[two existing failures](ci-tests.log) among 20 tests. Both report the same three
ontology knowledge-to-twin dependency violations: the rules-engine dev
dependency and its imports in two ontology test files. [Baseline comparison](dependency-baseline.log)
proves the checker, rules and flagged files are unchanged from HEAD; the same
findings are already recorded in
[an earlier baseline](../audit2-blueprint-open-decisions-stale/baseline-ci-tests.log).
This node does not weaken dependency rules or modify the out-of-scope
`packages/ontology/` files to hide them. Required `.github/workflows/ci.yml`
checks pass; the supplemental checker suite is not claimed green.

## V1 evidence boundary

[The decision](../../../docs/decisions/audit2-v1-gate-closure.md) enumerates the
six missing regeneration paths, assigns responsible roles, and defines the
14/14 reproduction, independent ReviewDecision, and S1/S6 evidence required
before V1 can pass. BLUEPRINT §9.2 and the validation README link to it.
The historical reproduction report remains 8 reproduced / 6 unverified.
Local synthetic tests and document consistency checks do not supply missing
private-source reproduction or actual cross-family knowledge review.
