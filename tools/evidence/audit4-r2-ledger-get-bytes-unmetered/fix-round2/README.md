# Fix round 2: select Rust for root workspace tests

The supervisor's Python run passed, then its root Cargo command failed because
rustup had no global default. The runner's directory-local toolchain file fixed
Python's fallback build in round 1, but does not select Rust at the worktree root.

`ci.yml` now sets `RUSTUP_TOOLCHAIN=1.98.1` at workflow scope, covering workspace
formatting, linting and tests as well as both ontology-runner jobs.
The root README documents the same environment selection and offline prerequisites.
Root `rust-toolchain.toml` is outside this node's allowed paths; no root toolchain
file or global rustup settings were changed. A bare root Cargo invocation still
needs the documented environment selection when no global default is configured.
[Toolchain selection evidence](toolchain-selection.log) records that distinction.

`tools/tests/test_ci_rust_toolchain.py` checks that CI and the runner select the
same version. Its real Cargo regression creates an isolated rustup home inside
the worktree with the installed toolchain linked but no default configured.
It reproduces the missing-default failure, then applies the workflow's environment
setting and successfully reads the root workspace metadata offline with the
lockfile enforced. It does not depend on a developer's global default.

Commands run from the worktree root unless specified. All commands below exited 0.
No R2 account, external service or real credentials were used. R2 tests use loopback
S3 stubs. The existing ResourceWarnings in Python output did not fail tests.

| Command | Result / evidence |
|---|---|
| `env -u RUSTUP_TOOLCHAIN -u ONJEON_ONTOLOGY_RUNNER -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -v` | 1,322 run, 1,316 passed, 6 existing skips, no failures/errors: [python-tests.log](python-tests.log) |
| `env -u CARGO_TARGET_DIR RUSTUP_TOOLCHAIN=1.98.1 cargo test --all --locked --offline` | 478 Rust tests passed, 1 existing ignored test, no failures across 65 result summaries: [workspace-rust-tests.log](workspace-rust-tests.log). Nested schema/codegen Python checks also passed. |
| From `docs/blueprint/proposals/온톨로지/검증/runner`: `env -u RUSTUP_TOOLCHAIN cargo test --locked --offline` | 3 passed: [runner-rust-tests.log](runner-rust-tests.log) |
| `python3 tools/evidence/audit4-r2-ledger-get-bytes-unmetered/mutation_check.py` | Both ledger regressions reject the removed body-meter binding; 6 expected assertion failures, no errors/skips, verifier exit 0: [mutation-check.log](mutation-check.log) |
| `env -u CARGO_TARGET_DIR RUSTUP_TOOLCHAIN=1.98.1 python3 -I tools/blueprint_counts.py` | Passed: [blueprint-counts.log](blueprint-counts.log) |
| Workflow, vocabulary, validation, validation self-test, product-purpose, spec and whitespace checks | All passed; exact commands and exit codes: [static-checks.log](static-checks.log) |

The full Python run includes all 125 R2 budget/checkpoint tests without skips.
It verifies actual `get_bytes` before reservation and after `finish()` clears
`ACTIVE`, for both default and injected S3 ledger stores. Mutation verification
removes only `st.meter = self.meter`; request hooks remain attached, so request
counts alone cannot satisfy the regressions.

[Final scope checks](scope-check.log) cover allowed paths, protected-file
preservation, Python parsing, evidence links and `git diff --check`.
