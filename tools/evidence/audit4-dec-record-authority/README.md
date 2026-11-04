# Audit 4: DEC record authority — fix round 3

Node `audit4-dec-record-authority`. Current local base:
`83837b547eeaab42434790c24eed557431182e11` (2026-11-04).

## Current blocker and supervisor handoff

The latest supplied `rules-engine` failure is run **41802792915**, PR #417,
head **83837b547eeaab42434790c24eed557431182e11**. It fails with
`PR-TRACE-MISSING` because the body still lacks a trace handle; its supplied body
matches [failed-pr-body.md](failed-pr-body.md). The prepared
[replacement body](pr-body.md) passes the unchanged guard locally.

Round 3 also adds the `edited` pull-request event to CI, preserving `opened`,
`synchronize` and `reopened`. This lets a PR body correction start a fresh run
with the corrected event payload even when no further commit is needed.
A regression checks all four triggers; existing CLI regressions prove that
CI's `PR_BODY` input rejects the failed body and accepts the replacement.

Supervisor actions (required before merge):

1. Publish this round's workflow/test/evidence changes through the supervisor's
   normal process. The previously reviewed head already exists remotely.
2. Replace PR #417's body with [pr-body.md](pr-body.md), for example:
   `gh pr edit 417 --body-file tools/evidence/audit4-dec-record-authority/pr-body.md`.
3. Inspect the new `pull_request` / `edited` run for the resulting head. Confirm
   the traceability step receives `Node audit4-dec-record-authority` (with or
   without Markdown backticks) in `PR_BODY`. Do not rely on rerunning the old
   failed event to pick up a changed body.
4. Record the green `rules-engine` run URL and full head SHA in
   [round 3 evidence](fix-round3/README.md), then check the remote-verification
   acceptance box in the PR body only after observing that result.

**Remote result remains unverified and merge remains blocked.** The editor is
prohibited from GitHub calls, commits and pushes; no such action was taken.
Local results cannot establish remote success. The external `onjeonloop.py`
mentioned in earlier review is absent from this repository, so its PR creation
logic was not changed. `STATUS: READY` means ready for supervisor handoff only.

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

## Earlier verification

[Round 2](fix-round2/README.md) records local checks at `de12fdea` and the
then-current supplied failure 41795070906. That historical failure is superseded
by the supplied round 3 failure above. Round 2 added the DEC-O17 delegation
citation and six exclusions. The round 1 logs below are retained as historical
local evidence, not a remote CI result.

## Round 1 reproduction

Round 1 was verified on 2026-11-04 at base
`582104b9dd41725f28d380af7f17b8c9aabc6029` plus that round's changes.
Commands ran from the repository root using the prerequisites in the root README.

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
