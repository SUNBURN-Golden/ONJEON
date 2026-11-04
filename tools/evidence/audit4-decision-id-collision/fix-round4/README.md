# Audit 4 decision ID collision — fix round 4

Node `audit4-decision-id-collision`. Local verification on 2026-11-04.

## Blocking failure and fix

CI run 41809010985 failed `PR body traceability (tasks.json task ID, node ID, or 09 P row)`:
the pull-request body was the same auto-generated decision description with `Refs #418`,
which names no task ID, node ID or P row. Rounds 2 and 3 handed the supervisor a
replacement body, but the remote body was not changed, so the guard failed again.

The namespace decision itself is unchanged: blueprint directions keep `BP-D-01` through
`BP-D-20`, `BP-D-08` is public-price collection·display·comparison, and the criteria
service gate keeps `D-08` / `DEC-D-08.md` with its `T-KN-14` release assignment. No gate
approval or decision meaning changed in this round.

A repository commit cannot edit a remote PR body. The repo-side fix therefore makes the
traceability check accept a second trace source the orchestrator already controls: the PR
head branch. Branch names are derived from the node slug
(`grokbot/onjeon-audit4-decision-id-collision`), so this pull request has been traceable
all along even though its generated body omitted the slug.

- `tools/ci/check_pr_body_traceability.py`: `check(body, tasks_path, head_ref=None)` reads
  task IDs, node IDs and P rows from the body **and** the optional head branch. A task ID
  from either source must exist in `tasks.json`. Body-only invocation is unchanged and
  still rejects a body with no handle.
- `.github/workflows/ci.yml`: the `pull_request` step now passes
  `PR_HEAD_REF: ${{ github.head_ref }}` as well as `PR_BODY`; the selftest still runs on
  every event.
- `docs/BLUEPRINT.md` §10 rule 1, `tools/ci/README.md`, and the reviewed bundle notes
  (`tasks.json`, `README.md`, `03_작업명세.md`) state the second source honestly.
- New regressions accept a handle from the head branch, keep an unrelated branch failing,
  validate a task ID found only in the branch, and replay the exact run 41809010985 body
  with and without `PR_HEAD_REF`.
- `docs/decisions/audit4-decision-id-collision.md` records this round; §11's decision
  index date was refreshed with `python3 -I tools/blueprint_status.py --write`.

The remote body is still the supervisor's to update; the CI step no longer depends on it.
No GitHub request, commit or push was made here.

## Reproduction

Run from the worktree root. The first check must exit 1 (body only), the second must exit 0
(unchanged body plus the orchestrator's head branch):

```sh
python3 -I tools/ci/check_pr_body_traceability.py --selftest
PR_BODY="$(cat tools/evidence/audit4-decision-id-collision/fix-round2/pr-body-before.txt)" \
  python3 -I tools/ci/check_pr_body_traceability.py
PR_BODY="$(cat tools/evidence/audit4-decision-id-collision/fix-round2/pr-body-before.txt)" \
  PR_HEAD_REF='grokbot/onjeon-audit4-decision-id-collision' \
  python3 -I tools/ci/check_pr_body_traceability.py
python3 -B -m unittest tools.tests.test_pr_body_traceability tools.tests.test_decision_records \
  tools.tests.test_price_display_scope tools.tests.test_blueprint_status \
  tools.tests.test_purpose_table_decision_sync -v
python3 -B -m unittest discover -s tools/tests -v
cargo test --all --locked --offline
(cd docs/blueprint/proposals/온톨로지/검증/runner && cargo test --locked --offline)
```

## Results

| Check | Result | Evidence |
|---|---|---|
| Traceability selftest | 8 violations caught for their rules, 10 clean cases (incl. head-branch cases) | [traceability-selftest.log](traceability-selftest.log) |
| Failing CI body, body only | Exit 1, `PR-TRACE-MISSING` | [pr-body-before.log](pr-body-before.log) |
| Same body plus head branch | Exit 0 | [pr-body-with-head-ref.log](pr-body-with-head-ref.log) |
| Traceability, namespace, price, status and purpose regressions | 81 passed | [regressions.log](regressions.log) |
| Full Python suite | 1,393 run, 1,387 passed, 6 skipped, 0 failed | [python-tests.log](python-tests.log) |
| Rust workspace | 495 passed, 1 ignored, 0 failed | [rust-tests.log](rust-tests.log) |
| Ontology runner | 4 passed | [ontology-tests.log](ontology-tests.log) |
| Ontology semantic check | Whole check passed | [ontology-check.log](ontology-check.log) |

Additional checks, all exit 0:

| Log | Command |
|---|---|
| [workflow-check.log](workflow-check.log) | `python3 tools/workflow_check.py` |
| [ci-workflow-security.log](ci-workflow-security.log) | `python3 -B -m unittest discover -s tools/tests -p test_ci_workflow_security.py -v` |
| [workflow-pins.log](workflow-pins.log) | `python3 -B -m unittest discover -s tools/tests -p test_workflow_pins.py -v` |
| [spec-check.log](spec-check.log) | `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` |
| [blueprint-status.log](blueprint-status.log) | `python3 -I tools/blueprint_status.py` |
| [blueprint-counts.log](blueprint-counts.log) | `python3 -I tools/blueprint_counts.py` |
| [vocab-check.log](vocab-check.log) | `python3 tools/vocab_check.py` |
| [validation-check.log](validation-check.log) | `python3 tools/validation_check.py` |
| [validation-selftest.log](validation-selftest.log) | `python3 tools/validation_check.py --selftest` |
| [format.log](format.log) | `cargo fmt --all -- --check` |
| [lint.log](lint.log) | `cargo clippy --locked --offline --all-targets -- -D warnings` |
| [daemon-dry-run.log](daemon-dry-run.log) | `python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all --quiet` |
| [document-references.log](document-references.log) | `python3 -B -m unittest tools.tests.test_decision_records.BlueprintDecisionIds.test_current_document_references_use_only_known_namespaced_ids -v` |

Trailing whitespace in captured logs was normalized without changing results.

## Limits

- The check proves only that a trace handle exists. It does not prove the named task, node
  or P row is complete, that evidence exists, or that this PR performed the work.
- A fork can choose a branch name containing an audit slug. The handle is a traceability
  token, not an authorization or identity proof; CI permissions remain `contents: read`.
- Remote GitHub CI is outside this worktree. The replay above uses the exact failing body
  and the pull request's actual branch name; the next push is the final remote check.
