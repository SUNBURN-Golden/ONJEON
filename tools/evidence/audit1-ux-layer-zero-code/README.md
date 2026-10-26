# audit1-ux-layer-zero-code evidence (fix round 1)

Logs from the fix round 1 working tree. Parent commit: `3f75c5f660888cdbdae147bf17ba01c0724696e5`.

What changed:
- `docs/decisions/audit1-ux-layer-zero-code.md` now describes the merged T-MB-01 scaffold under `apps/mobile/`, and what it still lacks: API integration, feature screens, the screen × state capture catalog and user-comprehension evidence. It no longer calls the L8 contract settled. `Amount.evidence_kind` and `Amount.applicability` are optional pending-axis strings, so the contract accepts documents that leave them out or use invented values.
- `tasks.json` has a new task, T-CT-08 (S0; prerequisites T-CT-01, T-CT-02 and T-CT-03, all merged). It promotes the two axes into the vocabulary, makes both fields required on Amount, and ships the rejection test `amount-evidence-axes-required`. It follows the same `canon_change` approval rule as T-CT-02. T-AP-02's `prereq_tasks` now include T-CT-08, and the feature registry rows `coverage-detail` and `evidence-view` list it. `03_작업명세.md` (§3 tables and S0 order) and the bundle README task count (64) match.
- `tools/tests/test_ux_layer_zero_code.py` adds 12 tests. CI's `unittest discover -s tools/tests` picks them up automatically.

Logs:
- `before.log`: the new tests run against the parent commit. 10 of 12 fail. The record denies the scaffold and calls the contract fixed, T-CT-08 does not exist, and T-AP-02 has no such prerequisite. The 2 that pass are the D-16 check and the helper self-test.
- `focused.log`: the same 12 tests on this change. All pass.
- `python-tests.log`: `python3 -m unittest discover -s tools/tests -v` (the CI command). 889 tests, OK, 6 skipped. These are the existing conditional skips.
- `doc-checks.log`: vocab_check, validation_check (with `--selftest`), spec_check (44/44 machine checks, 72/72 presence checks), blueprint_status and check_product_purpose. All exit with 0.

Limits: this is spec-level evidence. It shows that the task graph and the record agree with the repo, and that the Amount gap exists today. The vocabulary promotion and the rejection test itself are T-CT-08's work and have not run. The daemon reports under `tools/daemon/` were not touched. One docstring in `tools/tests/test_daemon_dry_run.py` still says "59 of the 63 spec tasks"; the true count is now 60 of 64. That file is part of the daemon source hash, so it was left unchanged to avoid regenerating the reports.
