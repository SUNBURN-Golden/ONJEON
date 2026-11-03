# Fix round 1: ledger GET accounting and local build setup

The two reported setup errors came from rustup having an installed Rust 1.98.1
toolchain but no selected global default. A prebuilt-runner environment override
in the earlier evidence did not fix ordinary local discovery.

The ontology runner now selects Rust 1.98.1 in its own `rust-toolchain.toml`.
CI builds and tests from that directory, with the lockfile enforced, so it
prepares the same toolchain before Python's offline build and Cargo-lock tests.
The Python test module documents the offline prerequisites. Global Rust settings
were not changed. Build failures and timeouts remain failures.
[Toolchain selection evidence](toolchain-selection.log) shows no active global
toolchain at the root and the pinned toolchain selected in the runner directory,
with the environment overrides removed.

Commands below run from the worktree root unless indicated. Logs are captured
from actual executions. No R2 account, external service, or real credentials
were used; the S3 tests use loopback stubs.

| Command | Result / evidence |
|---|---|
| `env -u RUSTUP_TOOLCHAIN -u ONJEON_ONTOLOGY_RUNNER -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -p test_ontology_runner_io_error.py -v` | 15 passed, including the real Cargo-lock test and runner batch tests: [runner-tests.log](runner-tests.log) |
| `env -u RUSTUP_TOOLCHAIN -u ONJEON_ONTOLOGY_RUNNER -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -p 'test_r2*.py' -v` | 125 passed, none skipped: [budget-tests.log](budget-tests.log) |
| `env -u RUSTUP_TOOLCHAIN -u ONJEON_ONTOLOGY_RUNNER -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -v` | Exit 0: 1,320 run, 1,314 passed, 6 existing skips, no failures/errors: [python-tests.log](python-tests.log) |
| From `docs/blueprint/proposals/온톨로지/검증/runner`: `env -u RUSTUP_TOOLCHAIN cargo test --locked --offline` | 3 passed: [runner-rust-tests.log](runner-rust-tests.log) |
| `python3 tools/evidence/audit4-r2-ledger-get-bytes-unmetered/mutation_check.py` | Exit 0: both regressions reject the removed body-meter binding; six expected assertion failures, no errors/skips: [mutation-check.log](mutation-check.log) |
| `python3 tools/workflow_check.py` | Passed: [workflow-check.log](workflow-check.log) |
| `python3 -I tools/ci/check_product_purpose.py` | Passed: [product-purpose.log](product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | Passed: [spec-check.log](spec-check.log) |

The R2 regressions assert actual `get_bytes` before reservation and after
`finish()` clears `ACTIVE`, for both default and injected S3 ledger stores.
Removing only `st.meter = self.meter` leaves request hooks intact and makes all
six subcases fail, demonstrating that request counts alone cannot satisfy them.

[Scope and link checks](scope-check.log) verify allowed paths, protected-file
preservation, local evidence links, Python parsing, and `git diff --check`.
