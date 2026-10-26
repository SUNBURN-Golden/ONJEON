# audit1-start-gates-enforcement evidence

Logs from the fix round 1 working tree. Parent commit: `f9ee93bb5027c65e023e4a064cd01534bce79f6c`.

- `before.log`: the new `StartGateEnforcement` tests run against the parent commit's rules and core. Six fail: the row has no cond, a direct `prereqs_satisfied` moves a task with `start=[D-X]` to `queued`, and `start: null` is read as `[]`.
- `focused.log`: the same 10 tests on this change. All pass.
- `python-tests.log`: `python3 -m unittest discover -s tools/tests -v` (the CI command). 866 tests, OK (6 skipped).
- `doc-checks.log`: vocab_check, validation_check (and --selftest), spec_check (44/44 machine checks, 72/72 presence checks) and blueprint_status. All exit 0.

`tools/daemon/reports/dry_run.log` and `unittest.log` were regenerated for the new tools/daemon source hash (M1-M44 all PASS, 196 daemon tests OK).
