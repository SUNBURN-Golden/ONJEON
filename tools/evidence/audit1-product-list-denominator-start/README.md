# audit1-product-list-denominator-start evidence

Logs from the fix round 1 working tree. Parent commit: `970331ac7fb36eee44cef412ee6f88890301f1ff`.

- `before.log`: `tools/tests/test_registry_denominator.py` run against the parent commit. 15 tests, 7 failures and 76 errors: the registry has no `product_list_reason_codes`, T-DT-04 `real_data` is only `D-04`, and DECISIONS.md, BLUEPRINT §12, DEC-O17, the bundle blocking tables and the registry README have no O19 domestic-IP gate.
- `python-tests.log`: `python3 -m unittest discover -s tools/tests -v` (the CI command) on this change. 886 tests, OK (6 skipped). ResourceWarning lines from the existing normalizer tests are filtered out.
- `doc-checks.log`: vocab_check, validation_check (and --selftest), spec_check, blueprint_status and check_product_purpose. All exit 0.

Registry counts checked against the committed CSVs: 53 insurers; disclosure entry points `archived` 8, `failed` 31, `blocked` 3, `unqueried` 11 (45 not archived); `product_list_status = unqueried` for all 53, each with `awaiting_T-DT-04;awaiting_domestic_env`, plus `disclosure_entry_missing` on the 45 and `foreign_sandbox_geo_blocked` on the 3 geo-blocked rows. No row is `not_disclosed`.
