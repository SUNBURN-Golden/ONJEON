# Audit 4 decision ID collision — fix round 2

Node `audit4-decision-id-collision`. Local verification on 2026-11-04.

The adopted namespace remains `BP-D-01` through `BP-D-20` for blueprint directions. `BP-D-08` covers public-price collection, display and comparison. The criteria gate remains `D-08`, recorded in `DEC-D-08.md` and used only for `T-KN-14` release.

## Supervisor action required for PR #419

Prepend this line and a blank line to the existing PR body:

```text
Node `audit4-decision-id-collision`
```

[pr-body-before.txt](pr-body-before.txt) transcribes the body supplied in CI run 41795807949's failure report. [pr-body.txt](pr-body.txt) is the same body with only the node line prepended, ready for the supervisor to apply. The failing body returns `PR-TRACE-MISSING` / exit 1 ([log](pr-body-before.log)); the corrected body returns exit 0 ([log](pr-body.log)). Neither the workflow nor the checker was relaxed.

The new `CommandLine.test_decision_node_body_requires_the_missing_trace_handle` regression exercises both snapshots through the `PR_BODY` environment variable used by CI, verifies the expected exit codes, and verifies that the node line is the only difference.

No GitHub request, commit or push was made in this round, as required by the task. These files do not update the live PR body. The supervisor must apply the body edit and trigger a fresh pull-request CI run at the final head; the old failed run is not evidence of the corrected body. Remote CI remains unverified here.

## Review corrections

The decision record now limits the legacy-reference rule to the current-document guard's scan scope and explicitly accounts for historical research documents outside that scope. The round 1 evidence now attributes namespace regression coverage to Audit 3. Its original pre-fix output was not retained in this worktree's evidence bundle, so the unsupported pre-fix-result claim was removed; no historical log was fabricated. The new before/after logs above reproduce the PR-body failure, not that historical document failure.

## Reproduction

Run from the worktree root. The first command must exit 1; the second must exit 0:

```sh
python3 -I tools/ci/check_pr_body_traceability.py --body-file tools/evidence/audit4-decision-id-collision/fix-round2/pr-body-before.txt
python3 -I tools/ci/check_pr_body_traceability.py --body-file tools/evidence/audit4-decision-id-collision/fix-round2/pr-body.txt
python3 -B -m unittest tools.tests.test_pr_body_traceability tools.tests.test_decision_records tools.tests.test_price_display_scope -v
python3 -B -m unittest discover -s tools/tests -v
cargo test --all --locked --offline
(cd docs/blueprint/proposals/온톨로지/검증/runner && cargo test --locked --offline)
```

The focused run passed all 52 tests and is recorded in [regressions.log](regressions.log). The full Python suite ran 1,390 tests: 1,384 passed, 6 skipped, no failures. The Rust workspace passed 495 tests (1 ignored), and the ontology runner passed 4 tests. Full-suite results are in [python-tests.log](python-tests.log), [rust-tests.log](rust-tests.log), and [ontology-tests.log](ontology-tests.log).

The ontology semantic check also passed ([ontology-check.log](ontology-check.log)). To reproduce, first run `cargo build --locked --offline --target-dir target` in the ontology runner directory ([ontology-build.log](ontology-build.log)), then from the worktree root run `python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py "$PWD/docs/blueprint/proposals/온톨로지/검증/runner/target/debug/ontology-case-runner"`. The explicit build supplies the executable independently of any configured Cargo target-directory override; the first attempt without it could not locate the executable.

Additional local checks are recorded by command name: `python3 -I tools/ci/check_pr_body_traceability.py --selftest` ([traceability-selftest.log](traceability-selftest.log)), `python3 tools/workflow_check.py` ([workflow-check.log](workflow-check.log)), `python3 tools/vocab_check.py` ([vocab-check.log](vocab-check.log)), `python3 tools/validation_check.py` ([validation-check.log](validation-check.log)), `python3 tools/validation_check.py --selftest` ([validation-selftest.log](validation-selftest.log)), `cargo fmt --all -- --check` ([format.log](format.log)), `cargo clippy --locked --offline --all-targets -- -D warnings` ([lint.log](lint.log)), `python3 -I tools/blueprint_counts.py` ([blueprint-counts.log](blueprint-counts.log)), `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` ([spec-check.log](spec-check.log)), and `python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all --quiet` ([daemon-dry-run.log](daemon-dry-run.log)).

These checks establish repository consistency, namespace separation, and local PR-body validation. They do not change decision approvals or release status.

All additional local checks listed above exited 0. Log trailing whitespace was normalized after execution; results are unchanged.

After the documentation edits, the current-document reference guard was rerun with `python3 -B -m unittest tools.tests.test_decision_records.BlueprintDecisionIds.test_current_document_references_use_only_known_namespaced_ids -v` ([document-references.log](document-references.log)); it passed.
