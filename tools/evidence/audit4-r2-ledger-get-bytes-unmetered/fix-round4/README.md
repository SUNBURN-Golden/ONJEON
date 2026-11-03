# Fix round 4: scoped local Rust setup and ledger regression evidence

The reported failure occurred after Python passed: plain root Cargo had no
selected toolchain. CI environment variables and the runner's nested pin do not
configure a separately launched root Cargo process.

Selected the already-installed Rust version for this worktree using:

```sh
rustup override set --path "$PWD" 1.98.1
```

This registers a directory override in rustup's local settings. It leaves the
global default and other worktrees unchanged. No root toolchain file or protected
repository file was added. The override is local environment setup, not a Git
change: a new checkout or separate verification environment must repeat the
README setup command. Remove it from this worktree with
`rustup override unset --path "$PWD"`.

The new isolated-rustup regression proves that plain Cargo succeeds in the
directory with an override, while a sibling directory still fails without a
global default. CI and runner pin consistency remains tested.

All commands below were run in this worktree. No real R2 service, credentials,
GitHub operation, commit, or push was used.

| Command | Result / evidence |
|---|---|
| `env -u RUSTUP_TOOLCHAIN -u ONJEON_ONTOLOGY_RUNNER -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -v` | 1,323 run, 1,317 passed, 6 existing skips, no failures/errors, exit 0: [python-tests.log](python-tests.log) |
| `python3 -m unittest discover -s tools/tests -p test_ci_rust_toolchain.py -v` | 3 passed, no skips: [toolchain-tests.log](toolchain-tests.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_r2*.py' -v` | 125 passed, no skips: [budget-tests.log](budget-tests.log) |
| `cargo test --all --locked --offline` | Plain Cargo, no environment pin: 478 passed, 1 existing ignored test, 0 failures across 65 summaries: [plain-cargo-tests.log](plain-cargo-tests.log) |
| `cargo +1.98.1 test --all --locked --offline` | Initial explicitly selected run also passed: [rust-tests.log](rust-tests.log) |
| From `docs/blueprint/proposals/온톨로지/검증/runner`: `cargo test --locked --offline` | 3 passed: [runner-rust-tests.log](runner-rust-tests.log) |
| `python3 tools/evidence/audit4-r2-ledger-get-bytes-unmetered/mutation_check.py` | Exit 0: removing the ledger body-meter binding causes 6 expected assertion failures in the two regressions; no errors/skips: [mutation-check.log](mutation-check.log) |
| `cargo fmt --all -- --check` | Passed: [final-checks.log](final-checks.log) |
| `cargo clippy --all-targets --locked --offline -- -D warnings` | Passed: [rust-clippy.log](rust-clippy.log) |
| Workflow, vocabulary, validation, validation self-test, product-purpose, spec, blueprint counts, whitespace | All passed; exact commands/exit codes: [static-checks.log](static-checks.log) |
| Changed path scope, protected files, Python parsing, whitespace | Passed: [scope-check.log](scope-check.log) |

[Toolchain selection](toolchain-selection.log) confirms plain Cargo and workspace
metadata work with `RUSTUP_TOOLCHAIN` unset. The initial full Python run before
adding the directory-override regression also passed: 1,322 run, 6 existing skips,
no errors/failures ([log](python-tests-before-toolchain-regression.log)).

The ledger meter binding remains before the first ledger access and survives
`ACTIVE` being cleared for settlement. The real-botocore loopback tests check
exact downloaded byte totals, admission exhaustion before reservation, and
settlement exhaustion with the full unsettled reservation retained. The mutation
check confirms these tests detect removal of body accounting while request hooks
remain attached.
