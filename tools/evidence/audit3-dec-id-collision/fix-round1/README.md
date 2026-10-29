# Audit 3 decision ID migration — fix round 1

2026-10-29. The ledger's 19 confirmed directions now use `BP-D-01` through `BP-D-19`. The execution gates and `DEC-D-xx.md` filenames keep their existing identifiers. The [ledger mapping](../../../../docs/blueprint/DECISIONS.md#11-이전-id-대응표) resolves every former identifier. ADR/DEC references, design proposals, R2 documentation and related regression assertions use the new namespace.

The historical research README outside this node's allowed paths is unchanged and explicitly covered by the mapping. Historical raw logs/diffs and unrelated medical-code fixtures are also preserved. The migration does not change decision meaning, approval status, task gates or operational permissions.

Evidence:

- [Before](before.log): the six added regression tests expose the pre-migration defects; 19 tests ran with 32 failures including subtests. The original 13 tests still passed.
- [Decision regressions](decision-records.log): 19 pass. Checks cover all 19 unique IDs, the complete one-to-one mapping, stale/unknown prose references, Korean suffixes and ranges, the five reported decisions' meanings, and preservation of their execution gates and DEC filenames.
- [Price-display regressions](price-display.log): 12 pass with the new ledger IDs; public-price and R2 operating decisions remain distinct.
- [Migration integrity](migration-integrity.log): comparing against HEAD with only the identifier substitution, all 19 direction rows and all 36 ADR/DEC records retain their content. `tasks.json` and `daemon_rules.json` are byte-identical to HEAD.
- [Blueprint status](blueprint-status.log): current 36-record index and content hash after reviewing §11 and running the documented refresh command.
- [Full Python suite](python-tests.log): 1,286 tests run, 1,280 pass, 6 skipped, no failures. Two skips need `ONJEON_ARCHIVE_RAW`, three need the local archive and `pdftotext`, and one targets old botocore without conditional-put support (the installed version supports it). The ontology runner was built locally ([build log](ontology-build.log)).
- [Rust workspace tests](rust-tests.log): 475 pass, 1 ignored, 0 failures (`cargo test --all`, including doctests).
- [Blueprint counts](blueprint-counts.log): current inventory matches the generated table.
- [Scope and links](scope-check.log): changed files stay inside the allowed paths, forbidden documents are untouched, and blueprint/decision/evidence links resolve.
- [Design specification check](spec-check.log): 45/45 machine checks and 72/72 presence checks pass.

Commands (from the worktree root; Cargo output stays under its ignored `target/`):

```bash
python3 -B tools/tests/test_decision_records.py
python3 -B tools/tests/test_price_display_scope.py
python3 -I tools/blueprint_status.py --write
python3 -I tools/blueprint_status.py
python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py
CARGO_TARGET_DIR="$PWD/target" cargo build --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir "$PWD/target/onto"
CARGO_TARGET_DIR="$PWD/target" ONJEON_ONTOLOGY_RUNNER="$PWD/target/onto/debug/ontology-case-runner" python3 -B -m unittest discover -s tools/tests -v
CARGO_TARGET_DIR="$PWD/target" cargo test --all
CARGO_TARGET_DIR="$PWD/target" python3 -I tools/blueprint_counts.py
git diff --check
```
