# Audit 4: DEC record authority — fix round 1

Node `audit4-dec-record-authority`. Verified locally on 2026-11-04 against
`582104b9dd41725f28d380af7f17b8c9aabc6029` plus this worktree's changes.

## Resolution and supervisor handoff

CI run 41783150105 rejected the decision PR because its body had no trace handle.
The supplied failure body is preserved in [failed-pr-body.md](failed-pr-body.md).
It still fails with exit 1 and `PR-TRACE-MISSING`; prepending
`Node audit4-dec-record-authority` makes it pass. The existing guard and CI
workflow retain their requirements.

The supervisor must replace the PR body with [pr-body.md](pr-body.md) and rerun CI
against the resulting head. This body passes the unchanged checker locally.
No GitHub operation, commit, or push was performed in this worktree. This evidence
does not claim that the existing remote body has changed or that remote CI is green.
The external `onjeonloop.py` mentioned in review is absent from this repository;
its PR creation logic was not changed.

The [decision note](../../../docs/decisions/audit4-dec-record-authority.md) now has
a complete heading and distinguishes the user decision in DEC-BUNDLE-STATUS part
(1) from its delegated part (2). Its operative interpretation follows BLUEPRINT
§0.1, §10 rule 3 and ADR-0019: DEC records can supply conditional development
criteria within existing authority; changing higher-level decisions or gate
definitions requires an ADR followed by §7 and related contract updates. An ADR
does not substitute for required owner approval. Existing gate conditions and
registration remain separate from the existence of a decision document.

No ADR-* or DEC-* source record, gate definition, registration, or approval state
changed. The edited audit note is outside the generated ADR/DEC inventory;
`blueprint_status.py` still confirms all 37 records without a refresh. Existing
§11 already preserves delegated status, the bundle's user decision, and remaining
gate conditions.

## Reproduction

Run from the repository root using the prerequisites in the root README.

| Command | Result / log |
|---|---|
| `python3 -I tools/ci/check_pr_body_traceability.py --body-file tools/evidence/audit4-dec-record-authority/failed-pr-body.md` | Expected exit 1, `PR-TRACE-MISSING` ([log](traceability.log)) |
| `python3 -I tools/ci/check_pr_body_traceability.py --body-file tools/evidence/audit4-dec-record-authority/pr-body.md` | Exit 0 ([log](traceability.log)) |
| `python3 -I tools/ci/check_pr_body_traceability.py --selftest` | Exit 0 ([log](traceability.log)) |
| `python3 -m unittest tools.tests.test_pr_body_traceability -v` | 17 tests, exit 0; includes both bodies through CI's `PR_BODY` environment entry point ([log](traceability.log)) |
| `python3 -m unittest tools.tests.test_decision_records tools.tests.test_decisions_ledger_sync tools.tests.test_purpose_table_decision_sync tools.tests.test_daemon_dry_run.StartGateEnforcement tools.tests.test_daemon_dry_run.PrereqAndMergeGateCond tools.tests.test_blueprint_status -v` | 76 tests, exit 0 ([log](decision-gates.log)) |
| `python3 -I tools/blueprint_status.py` | 37 ADR/DEC records current, exit 0 ([log](decision-gates.log)) |
| `python3 -m unittest discover -s tools/tests -v` | 1,391 tests run, 6 skipped, no failures/errors, exit 0 ([log](python-tests.log)) |
| `cargo test --all --locked --offline` | 495 tests pass, 1 ignored, exit 0 ([log](rust-tests.log)) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4 tests pass, exit 0 ([log](ontology-runner-tests.log)) |

[checks.log](checks.log) contains exact commands and exit codes for workflow,
vocabulary, validation (including selftest), blueprint counts, design spec and
daemon dry-run checks. All exit 0. The design checker also prints its pre-existing
gap inventory; its passing mechanical checks do not resolve those gaps.

The six Python skips are two archived-original tests without `ONJEON_ARCHIVE_RAW`,
three reproduction tests requiring a local archive and `pdftotext`, and one
old-botocore test that does not apply to the installed conditional-write-capable
version. The Rust ignored test is `regenerate_declared_abox_fixture`.
`git diff --check` passes, and all changed/new files are under `docs/decisions/`
or `tools/`, within this node's allowed paths.

The focused suite includes all 16 `test_blueprint_status.Freshness` tests that
previously failed because temporary directories could not be created. They now
pass without changing the tests or skipping them. Gate tests exercise mock
registration and blocked transitions; they do not authenticate the authority of
an arbitrary real-world decision observation. These checks are repository
regressions, not owner sign-off, live access authorization, or product release
evidence.
