# Audit 4: DEC record authority — fix round 5

Node `audit4-dec-record-authority`. Local base:
`fc6bd92a7872972787252415034e0c0e041d1283` plus the round 5 working-tree
changes, verified on 2026-11-09.

## Current blocker and supervisor handoff

Round 4's two blocking review findings are fixed locally:

1. **A body edit could overwrite a test job with success.** The traceability
   guard previously ran at the top of `rules-engine`, and `edited` reran only
   that guard. A bad body failed `rules-engine` before any test ran; fixing the
   body then produced a green `rules-engine` with every test skipped. The guard
   now lives in its own [`pr-traceability` workflow](../../../.github/workflows/pr-traceability.yml)
   and `ci.yml` has no `edited` trigger or `github.event.action` gating. A body
   edit re-runs only `pr-traceability`; `rules-engine` is created only by a
   full code run, so it can never report green without the suite running.
2. **The authority classification was incomplete.** It missed
   [DEC-CANON-T-CT-02](../../../docs/decisions/DEC-CANON-T-CT-02.md), which
   records a separate 2026-10-13 16:58 KST delegation, and the 2026-10-26
   amendment to [DEC-D-16](../../../docs/decisions/DEC-D-16.md). The note now
   classifies every `DEC-*.md` record and every amendment/addendum timestamp,
   scopes the earlier delegation's record to T-CT-02 while noting that no other
   DEC cites it, and reconciles the O12 and D-08 gate-lifting sentences.
   Regressions iterate the whole directory and discover amendment markers from
   the source records.

Supervisor actions (required before merge):

1. Publish this round through the supervisor's normal process.
2. Replace PR #417's body with [pr-body.md](pr-body.md), for example:
   `gh pr edit 417 --body-file tools/evidence/audit4-dec-record-authority/pr-body.md`.
3. Observe the `pr-traceability` run receives
   `Node audit4-dec-record-authority` in `PR_BODY` and succeeds.
4. Observe a full `rules-engine` run on the resulting head (the commit push,
   not a body-edit run) and record its URL and full head SHA in
   [round 5 evidence](fix-round5/README.md). Keep the remote acceptance box
   unchecked until both are observed.
5. If branch protection lists required checks, add `pr-traceability` so a
   missing body handle still blocks merge now that it no longer runs inside
   `rules-engine`.

**Remote result remains unverified and merge remains blocked.** The editor is
prohibited from GitHub calls, commits and pushes; no such action was taken.
Local results cannot establish remote success. `STATUS: READY` means ready for
supervisor handoff only.

## Round 5 changes

The [decision note](../../../docs/decisions/audit4-dec-record-authority.md) now
classifies all 18 `DEC-*.md` records, not just the six pre-delegation ones:
owner rulings (D-04, D-12), earlier user decisions (DEC-BUNDLE-STATUS part 1 and
D-08's 2026-10-12 confirmation), the separate T-CT-02 delegation
(DEC-CANON-T-CT-02), pre-delegation autoloop records (D-02, O12, O04, D-08,
D-07, D-16), and post-2026-10-15-delegation records (D-03, D-06, D-14, D-17,
D-18, O02, O14, O17 and DEC-BUNDLE-STATUS part 2). It also classifies the
D-16 2026-10-26 amendment, the O17 2026-10-26 addendum, and the
DEC-BUNDLE-STATUS 2026-10-29 partial replacement by ADR-0019. The note states
that DEC-O12's and DEC-D-08's "registering lifts" sentences are existing
registration procedures subject to their remaining conditions, not
self-executing gate releases or gate-definition changes.

Round 4's claim that the note classified "every record" was inaccurate; this
round corrects it and adds tests that fail on an unclassified record or
amendment. No ADR-* or DEC-* source record, gate definition, registration, or
approval state changed. The edited audit note is outside the generated ADR/DEC
inventory; `blueprint_status.py` still confirms all 37 records without a
refresh.

## Path scope by round

The branch contains five rounds, so path claims name their round:

- Rounds 1–2: `docs/decisions/`, `tools/tests/`, `tools/evidence/`.
- Round 3: `.github/workflows/`, `tools/tests/`, `tools/evidence/`.
- Round 4: `docs/decisions/`, `.github/workflows/`, `tools/tests/`,
  `tools/evidence/`.
- Round 5: `docs/decisions/`, `.github/workflows/`, `tools/tests/`,
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

## Round 5 verification

Commands ran from the repository root with `RUSTUP_TOOLCHAIN=1.98.1`.
Full details are in [round 5 evidence](fix-round5/README.md).

| Command | Result | Log |
|---|---|---|
| Guard selftest, failed fixture, and the replacement body through CI's `PR_BODY` input | Selftest exit 0; failed body expected exit 1, `PR-TRACE-MISSING`; replacement exit 0 | [traceability.log](fix-round5/traceability.log) |
| `python3 -m unittest tools.tests.test_pr_body_traceability -v` | 21 tests pass; includes the separated-workflow and DEC-ID regressions | [traceability.log](fix-round5/traceability.log) |
| Decision/ledger/purpose, start/merge gate, blueprint freshness, workflow security/pin and registry suites | 126 tests pass | [decision-gates.log](fix-round5/decision-gates.log) |
| `python3 -I tools/blueprint_status.py` | 37 ADR/DEC records current | [decision-gates.log](fix-round5/decision-gates.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,403 tests run, 6 skipped, no failures/errors, exit 0 | [python-tests.log](fix-round5/python-tests.log) |
| `cargo test --all --locked --offline` | 495 passed, 1 ignored, exit 0 | [rust-tests.log](fix-round5/rust-tests.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4 passed, exit 0 | [ontology-runner-tests.log](fix-round5/ontology-runner-tests.log) |
| Workflow hardening for both workflows, vocabulary, validation and selftest, blueprint counts, Rust format/lint, design spec, daemon dry run and `git diff --check` | All exit 0; exact commands in log | [checks.log](fix-round5/checks.log) |

## Earlier verification

[Round 4](fix-round4/README.md) records the round 4 local checks and its
correction note. [Round 3](fix-round3/README.md) records the round 3 local checks
and the then-current supplied failure 41802792915. It was committed as
`fb7a400`; the review at `83837b5` could not include it.
[Round 2](fix-round2/README.md) records checks at `de12fdea` and the historical
failure 41795070906. The round 1 logs below are retained as historical local
evidence, not a remote CI result.

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
