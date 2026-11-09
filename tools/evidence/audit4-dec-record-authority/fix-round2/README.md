# Audit 4 DEC authority: round 2 local verification

Historical record. The latest supplied failure and current supervisor actions
are recorded in [round 3](../fix-round3/README.md).

Node `audit4-dec-record-authority`. Verified on 2026-11-04 at base
`de12fdea3a0fa8b2d846946799a0b9de0873c767` plus the uncommitted round 2 changes.
Commands ran from the repository root with `RUSTUP_TOOLCHAIN=1.98.1` for Rust
and the Python suites that invoke Cargo. No GitHub call, commit, or push was
made by this round's editor.

The decision note directly cites DEC-O17 and preserves its six delegation
exclusions. The added documentation regression compares those exclusions with
the source record and checks that the ADR path, separate approval, and gate
restrictions remain explicit. No executable behavior or gate definition changed.

| Command | Local result | Log |
|---|---|---|
| `python3 -I tools/ci/check_pr_body_traceability.py` with `PR_BODY` loaded from each supplied body | Failed body: expected exit 1, `PR-TRACE-MISSING`; replacement: exit 0 | [traceability.log](traceability.log) |
| `python3 -I tools/ci/check_pr_body_traceability.py --selftest` | Exit 0 | [traceability.log](traceability.log) |
| `python3 -m unittest tools.tests.test_pr_body_traceability -v` | 17 tests, exit 0; rerun after final body wording edit | [traceability.log](traceability.log) |
| `python3 -m unittest tools.tests.test_decision_records tools.tests.test_decisions_ledger_sync tools.tests.test_purpose_table_decision_sync tools.tests.test_daemon_dry_run.StartGateEnforcement tools.tests.test_daemon_dry_run.PrereqAndMergeGateCond tools.tests.test_blueprint_status -v` | 77 tests, exit 0 | [decision-gates.log](decision-gates.log) |
| `python3 -I tools/blueprint_status.py` | 37 ADR/DEC records current, exit 0 | [decision-gates.log](decision-gates.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,392 tests run, 6 skipped, no failures/errors, exit 0 | [python-tests.log](python-tests.log) |
| `cargo test --all --locked --offline` | 495 passed, 1 ignored, exit 0 | [rust-tests.log](rust-tests.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4 passed, exit 0 | [ontology-runner-tests.log](ontology-runner-tests.log) |
| `cargo fmt --all -- --check` and `cargo clippy --locked --offline --all-targets -- -D warnings` | Both exit 0 | [checks.log](checks.log) |

[checks.log](checks.log) also records exact commands and exit 0 results for
workflow pins, vocabulary, validation and its selftest, blueprint counts,
design spec consistency, and daemon dry-run checks. The design checker reports
existing specification gaps; these checks do not close those gaps. The Python
skips and Rust ignored test have the same reasons as the [round 1 record](../README.md).
`git diff --check` passes. All edits are under the allowed `docs/decisions/` and
`tools/` paths; the generated ADR/DEC inventory needs no refresh.

The supplied remote CI run 41795070906 is still a failure. These local results
do not establish remote CI success or change PR #417's body. The supervisor must
apply [pr-body.md](../pr-body.md), run CI with that body as event input, and record
a green `rules-engine` result for the resulting head before merge. The replacement
body leaves that verification checkbox unchecked. `STATUS: READY` in the editor
handoff means ready for those supervisor actions, not ready to merge.
