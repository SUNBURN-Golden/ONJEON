# Audit 4 DEC authority: round 4 local verification and remote handoff

Node `audit4-dec-record-authority`. Local base:
`fb7a400a0825fabe12ce7bd3b1180b499a3a85d5`, verified on 2026-11-04 plus the
round 4 working-tree changes. Commands ran from the repository root with
`RUSTUP_TOOLCHAIN=1.98.1`. No GitHub call, commit or push was made.

## Review findings and round 4 response

> **Round 5 correction (2026-11-09).** Two claims in this round-4 record were
> wrong or superseded. (a) The note did **not** classify every record:
> [DEC-CANON-T-CT-02](../../../../docs/decisions/DEC-CANON-T-CT-02.md) (a
> separate 2026-10-13 16:58 KST delegation) and D-16's 2026-10-26 amendment
> were missing; round 5 adds the complete classification and tests that iterate
> every `DEC-*.md`. (b) The `edited`-event gating described in item 1 was itself
> a blocker: a body edit could report `rules-engine` green with every test
> skipped. Round 5 moves the guard into a separate `pr-traceability` workflow so
> a body edit cannot create or overwrite the `rules-engine` check. The local logs
> below remain historical evidence for the tree they were run on.

1. **Required `rules-engine` check red / body not applied.** The supplied
   failure is **41802792915**, PR #417, head
   **83837b547eeaab42434790c24eed557431182e11**. Its body lacks a trace handle
   and matches [the failing fixture](../failed-pr-body.md). The editor cannot
   edit the PR, so [the replacement body](../pr-body.md) is prepared and passes
   the unchanged guard. Round 4 narrows the `edited` event so that confirming
   the body reruns only the traceability steps at the same commit. **Remote
   verification remains pending: no green run URL or head SHA has been observed
   in this session.**
2. **Claimed fix not at the reviewed head.** Round 3's changes are committed in
   `fb7a400`, one commit after the reviewed `83837b5`; a diff generated at
   `83837b5` cannot contain them. Round 4 is based on `fb7a400`, and the
   supervisor's commit will be the new head to review.
3. **Pre-delegation DECs, especially O04.** The decision note now classifies
   every record by recorded time. D-04 and D-12 are direct owner rulings;
   DEC-BUNDLE-STATUS part (1) records the 2026-10-13 user decision, and DEC-D-08
   confirms the 2026-10-12 owner decision. D-02 (2026-10-14 06:31), O12 (07:35),
   O04 (08:06), D-08 (08:22), D-07 and D-16 (10:34) predate DEC-O17's
   2026-10-15 14:44 delegation and are classified as provisional autoloop
   design-scope records, not delegated or owner-confirmed. The note states that
   DEC-O04 is condition satisfaction for the existing O04 gate, not a
   gate-definition change: `compare_price` still needs the I7/I8/K13/bundle
   tests and registration, and recording the DEC releases nothing. Three new
   regressions read the source records' own timestamps and pin these claims.
4. **Evidence path claims.** [The parent evidence](../README.md) now names the
   path scope of each round; round 3's README claim is marked as round-3-only.
5. **`edited` trigger broader than needed.** The four-event trigger list is
   retained, but every heavy step in `rules-engine` is gated with
   `if: github.event.action != 'edited'` and the `design-specs` job is skipped
   on edits. On an edit, only the traceability self-test and body check run.
   A regression pins the step gating.

## Local results

| Command / check | Result | Log |
|---|---|---|
| `python3 -I tools/ci/check_pr_body_traceability.py --body-file …/failed-pr-body.md` | Expected exit 1, `PR-TRACE-MISSING` | [traceability.log](traceability.log) |
| `PR_BODY="$(cat …/pr-body.md)" python3 -I tools/ci/check_pr_body_traceability.py` | Exit 0 | [traceability.log](traceability.log) |
| `python3 -I tools/ci/check_pr_body_traceability.py --selftest` | Exit 0 | [traceability.log](traceability.log) |
| `python3 -m unittest tools.tests.test_pr_body_traceability -v` | 19 tests pass | [traceability.log](traceability.log) |
| Decision/ledger/purpose, start/merge gate, blueprint freshness and traceability suites | 99 tests pass | [decision-gates.log](decision-gates.log) |
| `python3 -I tools/blueprint_status.py` | 37 ADR/DEC records current | [decision-gates.log](decision-gates.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,397 tests run, 6 skipped, no failures/errors, exit 0 | [python-tests.log](python-tests.log) |
| `cargo test --all --locked --offline` | 495 passed, 1 ignored, exit 0 | [rust-tests.log](rust-tests.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4 passed, exit 0 | [ontology-runner-tests.log](ontology-runner-tests.log) |
| Workflow security/pin/registry regressions, vocabulary, validation and selftest, blueprint counts, Rust format/lint, design spec and daemon dry run | All exit 0; exact commands in log | [checks.log](checks.log) |

The design checker still reports pre-existing specification gaps; a passing
mechanical check does not close those gaps. The Rust ignored test remains
`regenerate_declared_abox_fixture`. The six Python skips are two
archived-original tests without `ONJEON_ARCHIVE_RAW`, three reproduction tests
requiring a local archive and `pdftotext`, and one old-botocore test that does
not apply to the installed version. `git diff --check` passes. Round 4's edits
are under `docs/decisions/`, `.github/workflows/`, `tools/tests/` and
`tools/evidence/`, within this node's allowed paths. Local tests do not establish
owner sign-off, live access, product completion or a green required remote
check.

## Required supervisor action

Publish this round's changes, then apply [pr-body.md](../pr-body.md) to PR #417.
Observe the resulting `edited` run, confirm it receives the corrected `PR_BODY`,
and record its URL and full head SHA here after `rules-engine` succeeds. Keep the
remote acceptance box unchecked until that evidence exists. The exact body-edit
command and handoff are in the
[parent evidence](../README.md#current-blocker-and-supervisor-handoff).

- Green `rules-engine` run URL: pending supervisor observation.
- Green run head SHA: pending supervisor observation.
- Merge readiness: blocked on that remote result.

`STATUS: READY` denotes readiness for supervisor handoff only. No irreversible,
monetary, legal, secrets or production decision is needed for this fix, so this
round does not create `DECISION_REQUIRED.md`.
