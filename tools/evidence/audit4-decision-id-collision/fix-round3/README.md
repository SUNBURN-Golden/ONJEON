# Audit 4 decision ID collision — fix round 3

Node `audit4-decision-id-collision`. Local verification on 2026-11-04.

## Required supervisor handoff

Replace the PR body with [pr-body.txt](pr-body.txt), which starts with:

```text
Node `audit4-decision-id-collision`
```

Apply that body before pushing the final head so the new pull-request run receives it. The current workflow uses the default `pull_request` event types; a body edit alone does not start this workflow. Do not rely on rerunning the old failed event to validate the new body. Verify the new run's traceability step receives the node line.

CI run 41804857097 supplied the same body as the retained [round 2 failing snapshot](../fix-round2/pr-body-before.txt): a decision description and `Refs #418`, with no task ID, node ID or P row. The checker correctly rejects that input. A repository commit cannot modify the remote PR body. No GitHub request, commit or push was made here; remote CI is still unverified. `STATUS: READY` in the builder handoff means the local work and replacement body are ready for the supervisor, not that the remote failure is already cleared.

## Decision and regression coverage

Blueprint directions retain the existing `BP-D-01` through `BP-D-20` namespace. `BP-D-08` covers public-price collection, display and comparison. The criteria gate remains `D-08`, with `DEC-D-08.md` and its existing release gate assignment. This round does not change gate approvals or decision meanings.

The existing namespace tests check unique IDs, the complete legacy mapping, current document references, decision meanings and execution gate preservation. The traceability regression now exercises both round 2 and round 3 replacement bodies through `PR_BODY` and `--body-file`. Removing the leading node line fails with `PR-TRACE-MISSING` for both bodies. Neither the checker nor the workflow was relaxed.

## Results and reproduction

Run from the worktree root:

```sh
# Expected exit 1; this is the input supplied by the failed CI run.
python3 -I tools/ci/check_pr_body_traceability.py --body-file tools/evidence/audit4-decision-id-collision/fix-round2/pr-body-before.txt
# Expected exit 0; this is the replacement body for the supervisor.
python3 -I tools/ci/check_pr_body_traceability.py --body-file tools/evidence/audit4-decision-id-collision/fix-round3/pr-body.txt
python3 -B -m unittest tools.tests.test_pr_body_traceability tools.tests.test_decision_records tools.tests.test_price_display_scope -v
python3 -B -m unittest discover -s tools/tests -v
cargo test --all --locked --offline
(cd docs/blueprint/proposals/온톨로지/검증/runner && cargo test --locked --offline)
```

| Check | Result | Evidence |
|---|---|---|
| Failing body through CI's `PR_BODY` input | Exit 1, `PR-TRACE-MISSING` | [pr-body-before.log](pr-body-before.log) |
| Replacement body through `PR_BODY` | Exit 0 | [pr-body.log](pr-body.log) |
| Traceability, namespace and public-price regressions | 52 passed | [regressions.log](regressions.log) |
| Full Python suite | 1,390 run, 1,384 passed, 6 skipped | [python-tests.log](python-tests.log) |
| Rust workspace | 495 passed, 1 ignored | [rust-tests.log](rust-tests.log) |
| Ontology runner | 4 passed | [ontology-tests.log](ontology-tests.log) |

Additional checks below all exited 0; each command has a correspondingly named log in this directory:

| Log | Command |
|---|---|
| [traceability-selftest.log](traceability-selftest.log) | `python3 -I tools/ci/check_pr_body_traceability.py --selftest` |
| [workflow-check.log](workflow-check.log) | `python3 tools/workflow_check.py` |
| [vocab-check.log](vocab-check.log) | `python3 tools/vocab_check.py` |
| [validation-check.log](validation-check.log) | `python3 tools/validation_check.py` |
| [validation-selftest.log](validation-selftest.log) | `python3 tools/validation_check.py --selftest` |
| [format.log](format.log) | `cargo fmt --all -- --check` |
| [lint.log](lint.log) | `cargo clippy --locked --offline --all-targets -- -D warnings` |
| [blueprint-counts.log](blueprint-counts.log) | `python3 -I tools/blueprint_counts.py` |
| [spec-check.log](spec-check.log) | `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` |
| [daemon-dry-run.log](daemon-dry-run.log) | `python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all --quiet` |

The ontology semantic check also passed ([ontology-check.log](ontology-check.log)). Reproduce by first running `cargo build --locked --offline --target-dir target` in the ontology runner directory ([ontology-build.log](ontology-build.log)), then from the root running `python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py "$PWD/docs/blueprint/proposals/온톨로지/검증/runner/target/debug/ontology-case-runner"`.

After updating this evidence and the decision note, the focused suite was rerun to check the final document references; [regressions.log](regressions.log) contains that final run. Trailing whitespace in captured logs was normalized without changing results.
