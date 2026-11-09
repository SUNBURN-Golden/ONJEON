# Audit 4 DEC authority: round 5 local verification and remote handoff

Node `audit4-dec-record-authority`. Local base:
`fc6bd92a7872972787252415034e0c0e041d1283`, verified on 2026-11-09 plus the
round 5 working-tree changes. Commands ran from the repository root with
`RUSTUP_TOOLCHAIN=1.98.1`. No GitHub call, commit or push was made.

## Review findings and round 5 response

1. **[BLOCKING] A body edit could report the test job green without tests.**
   Rounds 3–4 added the `edited` event and skipped every heavy step inside
   `rules-engine`; a bad body failed that job before `cargo test`, and a later
   `edited` run replaced the failure with a green run. Round 5 removes `edited`
   from `ci.yml` and removes all `github.event.action != 'edited'` gating. The
   traceability self-test and body check move to a separate
   [`pr-traceability` workflow](../../../../.github/workflows/pr-traceability.yml)
   with its own check name. A body edit re-runs only that guard; `ci.yml` is
   triggered only by code pushes and GitHub's default PR events, so no
   `rules-engine` check can be created or replaced by a body edit. Regressions
   pin the separated trigger sets, the distinct check name, the absence of
   edit gating, and the absence of heavy steps in the guard workflow.
2. **[BLOCKING] The authority classification was incomplete.**
   - [DEC-CANON-T-CT-02](../../../../docs/decisions/DEC-CANON-T-CT-02.md)
     records a Fable 5.1 decision made under the owner's **2026-10-13 16:58
     KST** delegation, not DEC-O17's 2026-10-15 delegation. The note now has a
     separate row for it, scopes the record's use of that delegation to the
     T-CT-02 canon change, states that no other DEC cites that delegation and it
     does not substitute for the 2026-10-15 delegation, and keeps the record's
     merge approval as not given.
   - [DEC-D-16](../../../../docs/decisions/DEC-D-16.md) was **amended
     2026-10-26** to add U7. The note now classifies the amendment as a
     post-2026-10-15-delegation delegated record, distinct from the original
     2026-10-15 10:34 provisional record.
   - The note also classifies the DEC-O17 2026-10-26 addendum and the
     DEC-BUNDLE-STATUS 2026-10-29 partial replacement by ADR-0019.
   - New tests iterate every `DEC-*.md` file and map every record to a category,
     so an unclassified record fails. A second test discovers
     `amended`/`Addendum`/`부분 대체` dates from the source records themselves,
     so an unclassified amendment fails.
3. **[Non-blocking] O12 and D-08 gate-lifting language.** The note now has a
   `Gate wording (O12·D-08)` section. It reads both "registering lifts" sentences
   as the existing registration procedures, subject to the records' remaining
   conditions (S6 per-operation evidence for O12; the closed-by-default
   T-KN-14 gate, no defaults, and open O05 for D-08). Recording a DEC is not a
   self-executing gate release, and neither record changes a gate definition.
   A regression pins the reconciliation and the source sentences.
4. **[Non-blocking] Evidence state.** The parent evidence now describes the
   separated workflow and keeps the remote result explicitly unverified. The
   round-4 README carries a correction note for its inaccurate "every record"
   claim and its superseded `edited` gating. No evidence file asserts a remote
   pass that this session did not observe.

## Guard behaviour note

The PR body now cites `DEC-CANON-T-CT-02`. The guard's task-ID pattern previously
extracted the hyphenated suffix `T-CT-02` from that decision-record ID and could
reject a valid body with `PR-TRACE-TASK`. The pattern now treats hyphens as part
of the token boundary (`(?<![A-Za-z0-9-])…(?![A-Za-z0-9-])`), and both a unit
test and the guard selftest cover the DEC-ID case.

## Local results

| Command / check | Result | Log |
|---|---|---|
| Guard selftest; failed fixture; replacement body through CI's `PR_BODY` input | Selftest exit 0; failed body exit 1 with `PR-TRACE-MISSING`; replacement exit 0 | [traceability.log](traceability.log) |
| `python3 -m unittest tools.tests.test_pr_body_traceability -v` | 21 tests pass | [traceability.log](traceability.log) |
| Decision/ledger/purpose, start/merge gate, blueprint freshness, workflow security/pin and registry suites (`126 tests`) | All pass | [decision-gates.log](decision-gates.log) |
| `python3 -I tools/blueprint_status.py` | 37 ADR/DEC records current | [decision-gates.log](decision-gates.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,403 tests run, 6 skipped, no failures/errors, exit 0 | [python-tests.log](python-tests.log) |
| `cargo test --all --locked --offline` | 495 passed, 1 ignored, exit 0 | [rust-tests.log](rust-tests.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4 passed, exit 0 | [ontology-runner-tests.log](ontology-runner-tests.log) |
| Workflow hardening for both workflows, workflow pin/security/registry/toolchain tests, vocabulary, validation and selftest, blueprint counts, Rust format/lint, design spec, daemon dry run and `git diff --check` | All exit 0; exact commands in log | [checks.log](checks.log) |

The design checker still reports pre-existing specification gaps; a passing
mechanical check does not close those gaps. The Rust ignored test is
`regenerate_declared_abox_fixture`. The six Python skips are two
archived-original tests without `ONJEON_ARCHIVE_RAW`, three reproduction tests
requiring a local archive and `pdftotext`, and one old-botocore test that does
not apply to the installed version. Local tests do not establish owner sign-off,
live access, product completion or a green required remote check.

## Required supervisor action

Publish this round's changes, then apply [pr-body.md](../pr-body.md) to PR #417.
Observe the `pr-traceability` run for the corrected body and a full
`rules-engine` run on the resulting head. Record both run URLs and the full head
SHA here after they succeed. Keep the remote acceptance box unchecked until that
evidence exists. If branch protection lists required checks, add
`pr-traceability` so a missing body handle still blocks merge now that it no
longer runs inside `rules-engine`.

- Green `pr-traceability` run URL: pending supervisor observation.
- Green `rules-engine` run URL: pending supervisor observation.
- Green run head SHA: pending supervisor observation.
- Merge readiness: blocked on those remote results.

`STATUS: READY` denotes readiness for supervisor handoff only. No irreversible,
monetary, legal, secrets or production decision is needed for this fix, so this
round does not create `DECISION_REQUIRED.md`.
