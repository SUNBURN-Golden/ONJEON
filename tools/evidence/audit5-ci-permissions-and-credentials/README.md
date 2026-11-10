# Audit 5 — CI permissions and checkout credentials

Date: 2026-11-10. Node: `audit5-ci-permissions-and-credentials`.
Baseline: `8e7a079a78ec302b999cc97c05f472a630563599` plus this node's uncommitted changes.
Scope and product-purpose traceability:
[audit record](../../../docs/blueprint/audits/2026-11-10_ci_permissions_and_credentials.md),
[BLUEPRINT §11](../../../docs/BLUEPRINT.md), and
[09 §5 development tools](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md).

The baseline already has exactly `permissions: contents: read`, both CI checkouts
set `persist-credentials: false`, and all external action references pinned to
full commit SHAs. Those workflow settings are preserved. The local files, rather
than the status of an older branch, establish the finding's current resolution.

Two new integration tests execute the security gate extracted from the actual
CI workflow in temporary repositories. Removing or enabling credential persistence
on each checkout fails with the expected diagnostic (four mutations). Moving the
safe setting to a different step also fails. The existing integration tests cover
six permission mutations and six mutable/short action-reference mutations.

## Reproduction and evidence

Run from the worktree root:

```sh
python3 tools/workflow_check.py .github/workflows/ci.yml .github/workflows/pr-traceability.yml
python3 -m unittest discover -s tools/tests -p 'test_workflow*.py' -v
python3 -m unittest discover -s tools/tests -p test_ci_workflow_security.py -v
python3 -m unittest discover -s tools/tests -v
cargo test --all --locked --offline
```

Full commands, working directories, exit codes, and elapsed times are in
[checks-summary.json](checks-summary.json). Cargo checks use the installed
Rust 1.98.1 and cached dependencies. Python discovery uses its normal offline
ontology-runner build path; no runner override is required. The additional
ontology build/test/case checks use `target/audit5-ci-ontology`.
[source-hashes.json](source-hashes.json) records the SHA-256 hashes of all three
workflows and the security checker/test files.

| Check | Result / log |
|---|---|
| Workflow token policy CLI | Exit 0: [permissions.log](permissions.log) |
| Workflow and CI security regressions | 32 + 5 tests pass: [workflow-tests.log](workflow-tests.log), [ci-security-tests.log](ci-security-tests.log) |
| Full Python project tests | 1,429 run, no failures/errors, 6 existing skips: [python-tests.log](python-tests.log) |
| Rust workspace tests | 513 pass, 1 existing ignored: [rust-tests.log](rust-tests.log) |
| Rust formatting / Clippy | Exit 0: [fmt.log](fmt.log), [clippy.log](clippy.log) |
| Ontology runner build / tests / case checks | Exit 0; 4 runner tests pass: [ontology-build.log](ontology-build.log), [ontology-tests.log](ontology-tests.log), [ontology-check.log](ontology-check.log) |
| Vocabulary / validation / mutation selftest | Exit 0; 40 selftest mutations: [vocabulary.log](vocabulary.log), [validation.log](validation.log), [validation-selftest.log](validation-selftest.log) |
| Design bundle / daemon dry run / blueprint counts | Exit 0; existing daemon specification gaps remain: [spec-check.log](spec-check.log), [daemon-dry-run.log](daemon-dry-run.log), [blueprint-counts.log](blueprint-counts.log) |
| Additional CI checker suite | 20 run, 2 failures from existing dependency-zone findings: [ci-checker-tests.log](ci-checker-tests.log) |

The six Python skips are five tests needing private local originals and one
conditional-PUT compatibility test for an older botocore. All new tests execute.

The additional `tools/ci/tests` suite is outside the commands currently declared
in `ci.yml`. Its two failing assertions share three dependency findings:
`packages/ontology/Cargo.toml:15`, `packages/ontology/tests/common/mod.rs:350`,
and `packages/ontology/tests/fixture_origin/main.rs:126` depend on/import the
rules engine from the knowledge zone. A temporary snapshot of the relevant
local HEAD files, extracted inside this worktree from `git archive`, produces
the identical diagnostics and exit code as the current worktree:
[baseline-dependency-check.log](baseline-dependency-check.log). This node leaves
that existing ontology dependency policy issue unchanged. The overall command
batch exits 1 because this additional suite fails; all declared CI checks pass.

This is local verification. GitHub Actions execution, upstream action tag-to-SHA
verification, actual product data and screen tests, and first-release evidence
remain separate. No commits, pushes, GitHub calls, credential reads, or external
storage requests were made by this task. The permission checker supports the
repository's block-style YAML layout rather than general YAML syntax.
