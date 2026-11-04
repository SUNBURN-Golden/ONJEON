# Audit 4 decision ID collision — fix round 5

Node `audit4-decision-id-collision`. Local verification on 2026-11-04.

## Blocking failure and fix

CI run 41809010985 failed `PR traceability (tasks.json task ID, node ID, or 09 P row)`.
Its log shows the workflow step passed only `PR_BODY`:

```text
env:
  RUSTUP_TOOLCHAIN: 1.98.1
  PR_BODY: Audit 4 finding: <decision description quoting both colliding IDs> ...
```

That run used the round-3 workflow, which had no `PR_HEAD_REF` mapping, so the
round-4 head-branch source was not supplied. Round 4's wiring alone does not
explain the observed environment.

The checker now falls back to GitHub's built-in `GITHUB_HEAD_REF`, which Actions
exports for every `pull_request` run regardless of the workflow's own `env`
block. Precedence is `--head-ref`, then `PR_HEAD_REF`, then `GITHUB_HEAD_REF`.
An empty explicit mapping falls through instead of suppressing the built-in
value. This pull request's head branch,
`grokbot/onjeon-audit4-decision-id-collision`, therefore supplies the handle even
when the workflow predates the mapping.

The namespace decision itself is unchanged: blueprint directions keep
`BP-D-01` through `BP-D-20`, `BP-D-08` is public-price
collection·display·comparison, and the criteria service gate keeps `D-08` /
`DEC-D-08.md` with its `T-KN-14` release assignment. No gate approval or decision
meaning changed in this round.

- `tools/ci/check_pr_body_traceability.py`: reads the head ref from
  `GITHUB_HEAD_REF` when the CLI and `PR_HEAD_REF` are absent or empty. Body-only
  invocation is unchanged and still rejects a body with no handle.
- `tools/tests/test_pr_body_traceability.py`: a new command-line regression
  replays run 41809010985's body with only `GITHUB_HEAD_REF` set (passes), with an
  empty `PR_HEAD_REF` plus `GITHUB_HEAD_REF` (falls through and passes), and with
  an unrelated built-in branch (still fails `PR-TRACE-MISSING`). The test helpers
  also clear `GITHUB_HEAD_REF` so an ambient value cannot mask a case.
- `docs/BLUEPRINT.md` §10 rule 1, `tools/ci/README.md` and
  `docs/decisions/audit4-decision-id-collision.md` state the third source and
  this round honestly.
- `pr-body-with-node.txt` is an optional supervisor handoff: the failing body
  plus the node line. The guard accepts it, but the CI step no longer depends on
  a remote body edit.

No GitHub request, commit or push was made here.

## Reproduction

Run from the worktree root. The first check must exit 1 (body only); the second
must exit 0 with the head branch supplied only through the built-in variable:

```sh
python3 -I tools/ci/check_pr_body_traceability.py --selftest
PR_BODY="$(cat tools/evidence/audit4-decision-id-collision/fix-round2/pr-body-before.txt)" \
  python3 -I tools/ci/check_pr_body_traceability.py
PR_BODY="$(cat tools/evidence/audit4-decision-id-collision/fix-round2/pr-body-before.txt)" \
  GITHUB_HEAD_REF='grokbot/onjeon-audit4-decision-id-collision' \
  python3 -I tools/ci/check_pr_body_traceability.py
python3 -I tools/ci/check_pr_body_traceability.py \
  --body-file tools/evidence/audit4-decision-id-collision/fix-round5/pr-body-with-node.txt
python3 -B -m unittest tools.tests.test_pr_body_traceability tools.tests.test_decision_records \
  tools.tests.test_price_display_scope tools.tests.test_blueprint_status \
  tools.tests.test_purpose_table_decision_sync -v
python3 -B -m unittest discover -s tools/tests -v
cargo test --all --locked --offline
(cd docs/blueprint/proposals/온톨로지/검증/runner && cargo test --locked --offline)
python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py \
  docs/blueprint/proposals/온톨로지/검증/runner/target/debug/ontology-case-runner
```

## Results

| Check | Result | Evidence |
|---|---|---|
| Traceability selftest | 8 violations caught for their rules, 10 clean cases | [traceability-selftest.log](traceability-selftest.log) |
| Failing CI body, body only | Exit 1, `PR-TRACE-MISSING` | [pr-body-before.log](pr-body-before.log) |
| Same body plus `GITHUB_HEAD_REF` | Exit 0 | [pr-body-with-github-head-ref.log](pr-body-with-github-head-ref.log) |
| Suggested body with node line | Exit 0 | [pr-body-with-node.log](pr-body-with-node.log) |
| Traceability, namespace, price, status and purpose regressions | 82 passed | [regressions.log](regressions.log) |
| Full Python suite | 1,394 run, 1,388 passed, 6 skipped, 0 failed | [python-tests.log](python-tests.log) |
| Rust workspace | 495 passed, 1 ignored, 0 failed | [rust-tests.log](rust-tests.log) |
| Ontology runner | 4 passed | [ontology-tests.log](ontology-tests.log) |
| Ontology semantic check | Whole check passed (questions 11/11, constraint self-tests 15/15, release/document model 25/25, amount 10/10) | [ontology-check.log](ontology-check.log) |

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

- The check proves only that a trace handle exists. It does not prove the named
  task, node or P row is complete, that evidence exists, or that this PR
  performed the work.
- A contributor can choose a branch name containing an audit slug. The handle is
  a traceability token, not an authorization or identity proof; CI permissions
  remain `contents: read`.
- `GITHUB_HEAD_REF` is read only inside Actions. Local runs keep the same strict
  body-only default unless `--head-ref` or `PR_HEAD_REF` is supplied.
- Remote GitHub CI is outside this worktree. The replay uses the exact failing
  body and the pull request's actual branch name; the next push is the final
  remote check.
