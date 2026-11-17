# Audit 6: missing decision gates — fix round 1

The dependency is retained. D-09/D-10 now gate T-CT-05 merges; D-15 gates T-CT-03, T-CT-08 and T-MB-01 merges. O03 gates regular-label promotion (`release`) for T-KN-05 and T-KN-08. Each has a pending DEC record and matching task/index/document entries. No decision is registered as approved.

T-KN-05 owns the dictionary candidate, code-revision mapping, review evidence and promotion rejection tests before M1. T-KN-08 retains P04's `label-kinds-complete` acceptance requirement. O03's dictionary content is still undecided. The daemon does not implement release gates, and the knowledge-service promotion path does not exist yet: service enforcement and real per-kind accepted/basis evidence remain explicit product-task obligations. This resolves the missing task-contract links and records; it is not M1, P04 or product completion evidence.

Regression coverage:

- G5d detects removed gates even when both task and decision index are edited, missing index entries and gates broadened to start.
- Actual daemon core transitions reject absent, partial and unrelated merge decisions; matching synthetic approvals permit the transition. Record file existence does not register a decision.
- O03 leaves candidate implementation/merge available. Task ownership, pre-M1 timing and P04's required test remain pinned.
- The readiness checker rejects failed or missing `label-kinds-complete` execution results. The synthetic result test does not implement the future label-data validator or claim real label completeness.

The reported 30-second workflow-security timeout did not reproduce in isolation (5 tests in 1.104s). Its subprocess budget is now 120 seconds to tolerate scheduling contention. CI command execution, timeout bounding, exit-code checks and every negative security assertion remain intact.

| Verification | Command | Result / log |
|---|---|---|
| Focused regressions | `python3 -m unittest tools.tests.test_audit6_missing_gates tools.tests.test_decision_records tools.tests.test_ci_workflow_security -v` | 46 passed; [focused.log](focused.log) |
| Index/baseline consistency | `python3 -m unittest tools.tests.test_o13_ruling tools.tests.test_blueprint_status -v` | 29 passed; [consistency.log](consistency.log) |
| Full Python suite | `python3 -m unittest discover -s tools/tests -v` | 1,696 run, 6 skipped, no failures; [python.log](python.log) |
| Rust workspace | `cargo test --all --locked --offline` | 532 passed, 1 ignored; [cargo.log](cargo.log) |
| Ontology runner | `cargo test --locked --offline` in `docs/blueprint/proposals/온톨로지/검증/runner` | 4 passed; [ontology.log](ontology.log) |
| Specification | `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 47/47 mechanical, 72/72 presence; [spec.log](spec.log) |
| Product-purpose contract | `python3 -I tools/ci/check_product_purpose.py` | Passed, static only; [purpose.log](purpose.log) |
| Workflow security | `python3 tools/workflow_check.py .github/workflows/ci.yml .github/workflows/pr-traceability.yml` | Passed; [workflow.log](workflow.log) |
| BLUEPRINT regression suite | `python3 -m unittest discover -s tools/tests -p 'test_blueprint*.py' -v` | 73 passed; [blueprint-tests.log](blueprint-tests.log) |
| Blueprint decision index | `python3 -I tools/blueprint_status.py` | Passed, 41 ADR/DEC files; [blueprint-status.log](blueprint-status.log) |
| Blueprint counts | `python3 -I tools/blueprint_counts.py` | Passed; [blueprint-counts.log](blueprint-counts.log) |

[Scope check](scope.log): only this worktree's allowed paths were changed. Protected files were not edited. No commit, push or GitHub call was made.

The [first full run](python-first-run.log) completed 1,696 tests with two consistency failures (6 skipped): the generated §11 decision hash/index was stale after adding four records, and the historical O13 test expected the old gate inventory. The generated index was refreshed with `blueprint_status.py --write`; the O13 test now compares its unchanged historical baseline plus only the four explicit Audit 6 additions, preserving every original gate, ledger row and protected-file hash check. Both regressions pass in [consistency.log](consistency.log).

The [second full run](python-second-run.log) had one remaining date-consistency failure: the index generator stamps §11 in UTC but does not change BLUEPRINT’s top-line revision date. The top-line date was aligned with §11; all 73 BLUEPRINT regressions then passed.

Final full Python run: passed (1,696 tests, 6 skipped). After clarifying that D-15 common design review precedes T-CT-03 without waiting for downstream implementation, the 46 focused regressions and 73 BLUEPRINT tests were also rerun and passed. Common design approval does not replace per-PR implementation review. No release gate was approved by this work.
