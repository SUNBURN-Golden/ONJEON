# Audit 5: tasks.json shell-invalid test commands

Audit 5 found `tasks.json` test entries that a shell cannot run: unquoted
`<시험용 원격>`/`<날짜>`/`<prev_tag>` (read as redirections), prose or a parenthesized
description appended to a command, and `cargo test` calls with two positional filters
(cargo accepts one TESTNAME). The same classes were present in
`feature_registry[].acceptance_tests`. Lines that start with `시험 ` are descriptions
(required test IDs, manual evidence), not commands, and are skipped.

G48 in `spec_check.py` validates task test entries as shell commands (quoted text is
ignored; unquoted `<…>` and parentheses are rejected; the first token must look like a
command) and counts positional `cargo test` filters in both task tests and registry
acceptance tests, skipping value-taking flags and everything after `--`. The check fails
if it examined zero commands. Registry acceptance tests are a mix of commands and prose,
so only their `cargo test` filter count is checked. The invalid
entries were rewritten as one-line shell commands (`$TEST_REMOTE`, `$RUN_DATE`,
`$PREV_TAG`, `infra/db/public/test.sh`, one command per filter) or, for manual items, as
`시험 …` descriptions.

Commands run on 2026-11-10 in this worktree with Rust 1.98.1 and Python 3:

| Command | Result / evidence |
|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_spec_check_shell.py' -v` | 15 passed, exit 0: [focused tests](focused-tests.log) |
| `python3 -I tools/evidence/audit5-tasks-json-shell-invalid-tests/check_old_commands.py` | All 19 reported commands detected, all replacements accepted, exit 0: [old-command log](old-commands.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 46/46 machine checks, 72/72 existence checks passed, exit 0: [spec check](spec-check.log) |
| `python3 -I tools/ci/check_bootstrap.py` | exit 0; six advisory path notes unrelated to this change: [bootstrap](bootstrap.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,506 run, 1,500 passed, 6 existing skips, exit 0: [full Python tests](python-tests.log) |
| `cargo test --all --locked --offline` | 70 test binaries/doc-test groups passed, no failures, exit 0: [workspace tests](rust-tests.log) |
| `(cd docs/blueprint/proposals/온톨로지/검증/runner && cargo test --locked --offline)` | 4 passed, exit 0: [runner tests](runner-tests.log) |

`check_old_commands.py` feeds the pre-fix strings back through the same validator used by
G48 and exits successfully only when every one is rejected and every current command for
the same task/feature IDs is accepted. It reads the live bundle and writes nothing.
G48 counted 101 task commands and 66 registry `cargo test` commands, skipping 115
`시험 …` descriptions.

Scope: G48 validates shell syntax and cargo's single-filter rule only. It does not prove
the commands succeed, that referenced scripts exist, or that environment variables are
set; `check_bootstrap.py` gives a separate advisory path check. This is static design-bundle
evidence, not daemon/service behavior or first-release completion evidence. See the
[audit record](../../../docs/blueprint/audits/2026-11-10_tasks_json_shell_invalid_tests.md).
