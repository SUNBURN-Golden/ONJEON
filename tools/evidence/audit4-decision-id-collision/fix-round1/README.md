# Audit 4 decision ID collision — fix round 1

2026-11-04. The blueprint direction namespace is `BP-D-xx`; public-price collection, display and comparison remain `BP-D-08`. The criteria application gate remains `D-08`, with record `DEC-D-08.md`. This round corrects three legacy references in the Audit 4 decision record. The existing migration and operational gate conditions are unchanged.

The original pre-fix run was not saved in this bundle; the logs below establish only the post-fix results. The namespace guard and its regression cases were already present from the Audit 3 migration, including quoted and Korean-suffixed references, the public-price meaning, preserved criteria gate and record, and the gate's exclusive use for `T-KN-14` release. Fix round 1 changed the decision document, not those tests.

Commands run from the worktree root unless stated otherwise:

- [Decision and price-scope regressions](decision-records.log): `python3 -B -m unittest tools.tests.test_decision_records tools.tests.test_price_display_scope -v` — 36 passed.
- [Full Python suite](python-tests.log): `python3 -B -m unittest discover -s tools/tests -v` — 1,389 run, 1,383 passed, 6 skipped, no failures.
- [Rust workspace](rust-tests.log): `cargo test --all --locked --offline` — 495 passed, 1 ignored, no failures.
- [Ontology runner](ontology-tests.log): `cargo test --locked --offline` from `docs/blueprint/proposals/온톨로지/검증/runner` — 4 passed.
- [Validation self-test](validation-selftest.log): `python3 tools/validation_check.py --selftest` — all 40 mutations caught for their intended reasons.

These checks verify repository consistency and identifier separation; they do not change approvals or release status.

Log trailing whitespace was normalized after execution; results are unchanged.
