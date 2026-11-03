# Fix round 3: independently rerun the reported failure

The supervisor reported 1,322 passing Python tests followed by a root Cargo
failure because rustup has no default toolchain. The workflow-level Rust setting
does not configure the supervisor's shell. The runner-local toolchain file does
not apply at the root either. These are toolchain-selection boundaries, not
failures in the ledger regression.

The reruns below were executed in this worktree. Every test/check command exited
0. Global Rust settings and files outside the node's allowed paths were not
changed. No real R2 requests or credentials were used.

| Command | Result / evidence |
|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_r2*.py' -v` | 125 passed, no skips: [budget-tests.log](budget-tests.log) |
| `env -u CARGO_TARGET_DIR -u ONJEON_ONTOLOGY_RUNNER -u RUSTUP_TOOLCHAIN python3 -m unittest discover -s tools/tests -v` | 1,322 run, 1,316 passed, 6 existing skips, no failures/errors: [python-tests.log](python-tests.log) |
| `env -u CARGO_TARGET_DIR RUSTUP_TOOLCHAIN=1.98.1 cargo test --all --locked --offline` | 478 Rust tests passed, 1 existing ignored test, no failures across 65 result summaries; nested Python checks also passed: [workspace-rust-tests.log](workspace-rust-tests.log) |
| From `docs/blueprint/proposals/온톨로지/검증/runner`: `env -u CARGO_TARGET_DIR -u RUSTUP_TOOLCHAIN cargo test --locked --offline` | 3 passed: [runner-rust-tests.log](runner-rust-tests.log) |
| `python3 tools/evidence/audit4-r2-ledger-get-bytes-unmetered/mutation_check.py` | Both regressions detect the removed ledger body-meter binding, with 6 expected assertion failures and no errors/skips; verifier exit 0: [mutation-check.log](mutation-check.log) |
| `env -u CARGO_TARGET_DIR RUSTUP_TOOLCHAIN=1.98.1 python3 -I tools/blueprint_counts.py` | Passed: [blueprint-counts.log](blueprint-counts.log) |
| Workflow, vocabulary, validation, validation self-test, product-purpose, spec and whitespace checks | All passed; exact commands and exit codes: [static-checks.log](static-checks.log) |

[Toolchain selection evidence](toolchain-selection.log) separately reproduces
the failing bare root Cargo invocation and verifies that explicitly selecting
the installed `1.98.1` toolchain succeeds offline. Bare root Cargo remains
unconfigured; a root `rust-toolchain.toml` requires an exception to this node's
allowed paths. Until that exception is granted, the supervisor must select Rust
for its own Cargo invocation, as in the passing command above (or use
`cargo +1.98.1 test --all --locked --offline`). CI and README settings alone cannot
change an independently launched supervisor process.

[Scope checks](scope-check.log) confirm allowed paths, protected-file
preservation, Python parsing and whitespace validation.
