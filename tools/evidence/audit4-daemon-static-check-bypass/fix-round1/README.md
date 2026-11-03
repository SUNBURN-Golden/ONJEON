# Fix round 1: local Rust toolchain selection

The reported local-test failure was not a test assertion. Python discovery ran
1,340 tests successfully, then the combined run stopped with:

```text
error: rustup could not choose a version of cargo to run, because one wasn't
specified explicitly, and no default is configured.
```

Rust 1.98.1 was installed in this worktree's rustup home, but the worktree had
no active toolchain and no global default. CI pins the channel through the
workflow-level `RUSTUP_TOOLCHAIN: "1.98.1"` in `.github/workflows/ci.yml`, and
the ontology runner pins the same channel in its own `rust-toolchain.toml`; the
repository root deliberately has no toolchain file (root `rust-toolchain.toml`
is outside this node's allowed paths, and
`tools/tests/test_ci_rust_toolchain.py` requires bare Cargo in an isolated
rustup home to keep failing with "no default is configured").

Following the remedy recorded by earlier Audit 4 nodes and the repository
README, this worktree now registers the path-local override:

```sh
rustup override set --path "$PWD" 1.98.1
```

No global rustup default was set and no Git-tracked file changed for this.
`cargo --version` now resolves 1.98.1 at the worktree root (see
[toolchain-selection.log](toolchain-selection.log)). All commands below ran from
the worktree root with `RUSTUP_TOOLCHAIN`, `ONJEON_ONTOLOGY_RUNNER`, and
`CARGO_TARGET_DIR` unset, so ordinary local discovery exercises the override.

The audit finding itself is implemented in this node's uncommitted changes:
`tools/daemon/static_checks.py` now uses an AST allowlist for imports and
external module members, resolving `import`/`from ... import` aliases and simple
assignment aliases, rejecting wildcard and above-package relative imports, and
applying the member policy to module `getattr`. The process-call, forbidden
`getattr`, `__builtins__` mapping, and truthy-literal `while` checks remain. The
new regression tests and the real static CLI pass.

| Command | Result / evidence |
|---|---|
| `rustup override set --path "$PWD" 1.98.1`; `cargo --version` | 1.98.1, no global default: [toolchain-selection.log](toolchain-selection.log) |
| `python3 -m unittest discover -s tools/tests -v` | Exit 0: 1,340 run, 6 existing skips, no failures/errors: [python-tests.log](python-tests.log) |
| `cargo test --all --locked --offline` | Exit 0: 478 passed, 1 existing ignored, 0 failed: [rust-tests.log](rust-tests.log) |
| `python3 -m unittest tools/tests/test_daemon_static_checks.py -v` | Exit 0: 19 tests: [static-check-tests.log](static-check-tests.log) |
| `python3 -I tools/daemon/static_checks.py` | Exit 0: 13 checks, 0 failed: [static-checks.log](static-checks.log) |

The six existing Python skips are unchanged (five tests needing local originals
and one conditional-PUT test not applicable to the installed botocore). This is
local test evidence only; no global toolchain default, commits, pushes, GitHub
calls, external services, or credentials were used.
