# Audit 4: DEC record authority — fix round 4

Node `audit4-dec-record-authority`. Local base:
`fb7a400a0825fabe12ce7bd3b1180b499a3a85d5` plus the round 4 working-tree
changes, verified on 2026-11-04.

## Current blocker and supervisor handoff

The latest supplied `rules-engine` failure is run **41802792915**, PR #417,
head **83837b547eeaab42434790c24eed557431182e11**. Its body matched
[failed-pr-body.md](failed-pr-body.md) and lacks a trace handle. The prepared
[replacement body](pr-body.md) starts with `Node audit4-dec-record-authority`
and passes the unchanged guard.

The reviewer also noted that the reviewed head (`83837b5`) was one commit behind
the branch ref (`fb7a400`). The round 3 workflow, replacement body and evidence
are committed in `fb7a400`; a diff generated at `83837b5` cannot contain them.
Round 4 is based on `fb7a400`, and the supervisor's commit becomes the head to
review.

Round 3 added the `edited` pull-request event. Round 4 narrows it: on an
`edited` event the `rules-engine` job still runs the traceability self-test and
body check, but skips the heavy build/test steps because a body or title edit
cannot change code; the separate `design-specs` job is skipped too. This
refreshes the required check at the same commit without rerunning the full
suite. Regressions pin both the four-event trigger list and the edited-only
step/job gating.

Supervisor actions (required before merge):

1. Publish this round through the supervisor's normal process.
2. Replace PR #417's body with [pr-body.md](pr-body.md), for example:
   `gh pr edit 417 --body-file tools/evidence/audit4-dec-record-authority/pr-body.md`.
3. Observe the resulting `edited` run. Confirm the traceability step receives
   `Node audit4-dec-record-authority` (with or without Markdown backticks) in
   `PR_BODY` and that `rules-engine` succeeds.
4. Record the green run URL and full head SHA in
   [round 4 evidence](fix-round4/README.md), then check the remote-verification
   box in the PR body only after observing that result.

**Remote result remains unverified and merge remains blocked.** The editor is
prohibited from GitHub calls, commits and pushes; no such action was taken.
Local results cannot establish remote success. `STATUS: READY` means ready for
supervisor handoff only.

## Round 4 changes

The [decision note](../../../docs/decisions/audit4-dec-record-authority.md) now
classifies every record by recorded time. D-04 and D-12 are direct owner rulings;
DEC-BUNDLE-STATUS part (1) records the 2026-10-13 user decision, and DEC-D-08
confirms the 2026-10-12 owner decision. D-02 (2026-10-14 06:31), O12 (07:35),
O04 (08:06), D-08 (08:22), D-07 and D-16 (10:34) all predate DEC-O17's
2026-10-15 14:44 delegation. The note does not claim that delegation for them:
they are provisional development criteria inside existing design scope, not owner
confirmations, and they cannot change gate definitions, completion criteria or
approval state. The note also states that DEC-O04 is condition satisfaction for
the existing O04 gate, not a gate-definition change: `compare_price` still needs
the I7/I8/K13/bundle tests, and the record alone releases nothing.

No ADR-* or DEC-* source record, gate definition, registration, or approval state
changed. The edited audit note is outside the generated ADR/DEC inventory;
`blueprint_status.py` still confirms all 37 records without a refresh.

## Path scope by round

The branch contains four rounds, so path claims name their round:

- Rounds 1–2: `docs/decisions/`, `tools/tests/`, `tools/evidence/`.
- Round 3: `.github/workflows/`, `tools/tests/`, `tools/evidence/`.
- Round 4: `docs/decisions/`, `.github/workflows/`, `tools/tests/`,
  `tools/evidence/`.

Round 3's README says its own edits are under `.github/workflows/` and `tools/`;
that claim covers round 3 only. Earlier rounds changed `docs/decisions/`.

## Round 4 verification

Commands ran from the repository root with `RUSTUP_TOOLCHAIN=1.98.1`.

| Command | Result | Log |
|---|---|---|
| Traceability guard on the failed fixture, the replacement body through CI's `PR_BODY` input, and `--selftest` | Failed body: expected exit 1, `PR-TRACE-MISSING`; replacement: exit 0; selftest exit 0 | [traceability.log](fix-round4/traceability.log) |
| `python3 -m unittest tools.tests.test_pr_body_traceability -v` | 19 tests pass; includes the edited-event step gating | [traceability.log](fix-round4/traceability.log) |
| Decision/ledger/purpose, start/merge gate, blueprint freshness and traceability suites | 99 tests pass | [decision-gates.log](fix-round4/decision-gates.log) |
| `python3 -I tools/blueprint_status.py` | 37 ADR/DEC records current | [decision-gates.log](fix-round4/decision-gates.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,397 tests run, 6 skipped, no failures/errors, exit 0 | [python-tests.log](fix-round4/python-tests.log) |
| `cargo test --all --locked --offline` | 495 passed, 1 ignored, exit 0 | [rust-tests.log](fix-round4/rust-tests.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4 passed, exit 0 | [ontology-runner-tests.log](fix-round4/ontology-runner-tests.log) |
| Workflow security/pin/registry regressions, vocabulary, validation and selftest, blueprint counts, Rust format/lint, design spec and daemon dry run | All exit 0; exact commands in log | [checks.log](fix-round4/checks.log) |

The design checker still reports pre-existing specification gaps; a passing
mechanical check does not close those gaps. The Rust ignored test is
`regenerate_declared_abox_fixture`. The six Python skips are two
archived-original tests without `ONJEON_ARCHIVE_RAW`, three reproduction tests
requiring a local archive and `pdftotext`, and one old-botocore test that does
not apply to the installed version. `git diff --check` passes. Local tests do
not establish owner sign-off, live access, product completion or a green
required remote check.

## Earlier verification

[Round 3](fix-round3/README.md) records the round 3 local checks and the
then-current supplied failure 41802792915. It was committed as `fb7a400`; the
review at `83837b5` could not include it. [Round 2](fix-round2/README.md) records
checks at `de12fdea` and the historical failure 41795070906. The round 1 logs
below are retained as historical local evidence, not a remote CI result.

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
daemon dry-run checks at round 1. All exit 0. The design checker also prints its
pre-existing gap inventory; its passing mechanical checks do not resolve those
gaps.

The six Python skips are two archived-original tests without `ONJEON_ARCHIVE_RAW`,
three reproduction tests requiring a local archive and `pdftotext`, and one
old-botocore test that does not apply to the installed conditional-write-capable
version. The Rust ignored test is `regenerate_declared_abox_fixture`.
`git diff --check` passes. Round 1's changed/new files are under
`docs/decisions/`, `tools/tests/` and `tools/evidence/`, within this node's
allowed paths; later rounds added `.github/workflows/`.

The focused suite includes all 16 `test_blueprint_status.Freshness` tests that
previously failed because temporary directories could not be created. They now
pass without changing the tests or skipping them. Gate tests exercise mock
registration and blocked transitions; they do not authenticate the authority of
an arbitrary real-world decision observation. These checks are repository
regressions, not owner sign-off, live access authorization, or product release
evidence.
