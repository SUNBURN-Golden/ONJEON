# Audit 4 DEC authority: round 3 local verification and remote handoff

Node `audit4-dec-record-authority`. Local base:
`83837b547eeaab42434790c24eed557431182e11`, verified on 2026-11-04 plus
uncommitted round 3 changes. Commands ran from the repository root with
`RUSTUP_TOOLCHAIN=1.98.1`. No GitHub call, commit or push was made.

## Review findings and current state

The supplied required-check failure is **41802792915**, `rules-engine`, PR #417,
head **83837b547eeaab42434790c24eed557431182e11**. Its body still lacks a trace
handle and matches [the failing fixture](../failed-pr-body.md). The reviewer’s
blocking remote verification is **pending**: no green run URL or green head SHA
has been observed in this editor session. Runs 41783150105 and 41795070906 are
historical failures, not the latest result.

The [replacement body](../pr-body.md) contains this node ID and passes the
unchanged guard through CI's `PR_BODY` environment input. CI now also subscribes
to `pull_request: edited`, retaining `opened`, `synchronize` and `reopened`.
A body correction can therefore trigger a fresh check at the same head once
this workflow is published. Title edits also trigger CI. No gate, decision
record, owner approval requirement or traceability exemption changed.

The new regression checks the event list. Local mutation checks remove each of
the four event types in turn and confirm that the regression fails. Existing
CLI tests exercise both failed and corrected PR bodies. These checks verify
configuration and guard behavior locally; they do not execute GitHub Actions.

## Local results

| Command / check | Result | Log |
|---|---|---|
| `python3 -I tools/ci/check_pr_body_traceability.py`, loading each body into `PR_BODY` | Failed body: expected exit 1, `PR-TRACE-MISSING`; corrected body: exit 0 | [traceability.log](traceability.log) |
| `python3 -I tools/ci/check_pr_body_traceability.py --selftest` | Exit 0 | [traceability.log](traceability.log) |
| `python3 -m unittest tools.tests.test_pr_body_traceability -v` | 18 tests pass; four missing-event mutations rejected | [traceability.log](traceability.log) |
| Decision/ledger/purpose, start/merge gate and blueprint freshness suites (exact command in log) | 77 tests pass | [decision-gates.log](decision-gates.log) |
| `python3 -I tools/blueprint_status.py` | 37 ADR/DEC records current | [decision-gates.log](decision-gates.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,393 tests run, 6 skipped, no failures/errors, exit 0 | [python-tests.log](python-tests.log) |
| `cargo test --all --locked --offline` | 495 passed, 1 ignored, exit 0 | [rust-tests.log](rust-tests.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4 passed, exit 0 | [ontology-runner-tests.log](ontology-runner-tests.log) |
| Workflow security/pin regressions, vocabulary, validation and selftest, blueprint counts, Rust format/lint, design spec and daemon dry run | All exit 0; exact commands in log | [checks.log](checks.log) |

The design checker still reports pre-existing specification gaps; a passing
mechanical check does not close those gaps. The Rust ignored test remains
`regenerate_declared_abox_fixture`. The six Python skips are two archived-original
tests without `ONJEON_ARCHIVE_RAW`, three reproduction tests requiring a local
archive and `pdftotext`, and one old-botocore test that does not apply to the
installed version. `git diff --check` passes; all edits are under the allowed
`.github/workflows/` and `tools/` paths. Local tests do not establish owner sign-off,
live access, product completion or a green required remote check.

## Required supervisor action

The prior head is already published. Publish **this round's changes**, then apply
[pr-body.md](../pr-body.md) to PR #417. Observe the resulting `edited` event run,
confirm it receives the corrected `PR_BODY`, and record its URL and full head SHA
here after `rules-engine` succeeds. Keep the remote acceptance box unchecked
until that evidence exists. The exact body-edit command and handoff are in the
[parent evidence](../README.md#current-blocker-and-supervisor-handoff).

- Green `rules-engine` run URL: pending supervisor observation.
- Green run head SHA: pending supervisor observation.
- Merge readiness: blocked on that remote result.

`STATUS: READY` denotes readiness for supervisor handoff only. No irreversible,
monetary, legal, secrets or production decision is needed for this fix, so this
round does not create `DECISION_REQUIRED.md`.
