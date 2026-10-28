# Audit 2: explicit string literals — fix round 1

Baseline: `239ce59564baa9043221896136f32a1d505fe269`. Commands ran against this worktree plus the changes described in [the decision](../../../docs/decisions/audit2-engine-string-literals.md), on 2026-10-28. No commits or fixture/hash-pin updates were made.

| Evidence | Command / result |
|---|---|
| [before.log](before.log) | `cargo test -p onjeon-rules-engine --test string_literals` before the parser change: exit 101, 7 failures on missing `str` support and 1 passing legacy compatibility test. Captured before rustfmt; diagnostic line numbers reflect that source layout. |
| [workspace-tests.log](workspace-tests.log) | `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked`: exit 0; 466 Rust tests passed, 1 existing fixture-regeneration test ignored. Includes all 8 new regressions, vocabulary allow-list tests, golden traces/hashes, mutation/soundness, schema Python tests (129), schema compatibility self-test, and generated file checks. Engine: 201 unit/integration tests + 3 doctests. |
| [python-tests.log](python-tests.log) | `python3 -m unittest discover -s tools/tests -v`: exit 0; 1,161 tests run, 6 skipped (5 need archived originals/reproduction tools, 1 tests an older botocore lacking conditional writes). The existing ontology runner from the configured Cargo target directory was supplied via `ONJEON_ONTOLOGY_RUNNER`. |
| [lint.log](lint.log) | `cargo fmt --all -- --check`; `cargo clippy --all-targets --locked -- -D warnings`: both exit 0. |
| [checks.log](checks.log) | Vocabulary check (49 axes, 270 values), generated files (30 current), validation consistency and 38 tamper self-tests, 27 vocabulary checker unit tests, BLUEPRINT counts: all exit 0. |
| [compatibility.log](compatibility.log) | Compared vocabulary with baseline HEAD: only version/date and `rule_operator.str` added; existing definitions/order preserved. `git diff --exit-code HEAD -- packages/fixtures/rules packages/rules-engine/tests/fixtures` exits 0. Existing pins pass in the workspace test log. |
| [generated-build.log](generated-build.log) | Generated Rust contracts/API build, including API skeleton feature. TypeScript/Dart skipped because neither toolchain is installed; exit 3 explicitly means incomplete. No claim that those two languages were built on this tree. |

Old engines still reject new `str` expressions. Compatibility evidence covers existing rules on the updated engine, not new rules on old engines. Existing bare strings retain input-first/rate-fallback semantics. New compiler output must use explicit `input` and `str` forms.

Logs retain command output and exit status. Machine-specific worktree/target paths are replaced with `<worktree>`/`<target>`; test diagnostics and results are otherwise preserved. The original schema evidence directory records older trees; these logs are the current evidence for the 1.8.0 vocabulary update.

Schema tree SHA-256 (`bash packages/schemas/codegen/tree_hash.sh`, excluding historical evidence and Python caches): `ec776b0220f7a72e01b4f0025b172e2935beb215f92de293103225d3c9b8b5db`.
