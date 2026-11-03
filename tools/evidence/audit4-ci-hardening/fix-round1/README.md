# Fix round 1: local Rust toolchain selection

The reported local-test failure was not a test assertion. Python discovery ran
1,330 tests successfully, then the run stopped with:

```text
error: rustup could not choose a version of cargo to run, because one wasn't
specified explicitly, and no default is configured.
```

Rust 1.98.1 was installed but this worktree had no rustup override, so plain
`cargo` could not select the toolchain that CI pins through
`RUSTUP_TOOLCHAIN: "1.98.1"`. Following [README §로컬 시험](../../../../README.md),
this worktree now registers the documented path-local override:

```sh
rustup override set --path "$PWD" 1.98.1
```

No global rustup default was set and no Git-tracked file changed for this.
`cargo --version` now resolves 1.98.1 at the worktree root (see
[toolchain-selection.log](toolchain-selection.log)). All commands below were run
from the worktree root with `RUSTUP_TOOLCHAIN`, `ONJEON_ONTOLOGY_RUNNER`, and
`CARGO_TARGET_DIR` unset, to exercise ordinary local discovery.

The audit finding itself was already resolved at the baseline: `ci.yml` has
carried the top-level `permissions:\n  contents: read` block and
`persist-credentials: false` checkouts since the Audit 3 change, and the
broadened mutation test continues to require exactly that minimal permission.
This round re-ran the full local suite after fixing toolchain selection.

| Command | Result / evidence |
|---|---|
| `cargo --version` (no env override) | 1.98.1: [toolchain-selection.log](toolchain-selection.log) |
| `python3 -m unittest discover -s tools/tests -v` | Exit 0: 1,330 run, 6 existing skips, no failures/errors: [python-tests.log](python-tests.log) |
| `cargo test --all --locked --offline` | Exit 0: 478 passed, 1 existing ignored: [rust-tests.log](rust-tests.log) |
| `cargo fmt --all -- --check` | Exit 0: [fmt.log](fmt.log) |
| `cargo clippy --all-targets --locked --offline -- -D warnings` | Exit 0: [clippy.log](clippy.log) |
| Ontology runner build, unit tests, and case check | Exit 0, 3 runner tests: [ontology-build.log](ontology-build.log), [ontology-tests.log](ontology-tests.log), [ontology-check.log](ontology-check.log) |
| `python3 tools/workflow_check.py` and workflow tests | Exit 0; 35 tests, including the six permission mutations: [permissions.log](permissions.log), [workflow-tests.log](workflow-tests.log) |
| Vocabulary, validation, and validation selftest | Exit 0; 38 selftest mutations: [vocabulary.log](vocabulary.log), [validation.log](validation.log), [validation-selftest.log](validation-selftest.log) |
| Design bundle check, daemon dry run, blueprint counts | Exit 0: [spec-check.log](spec-check.log), [daemon-dry-run.log](daemon-dry-run.log), [blueprint-counts.log](blueprint-counts.log) |

The six existing Python skips are unchanged (five tests needing local originals
and one conditional-PUT test not applicable to the installed botocore). This is
local test evidence only; no commits, pushes, GitHub calls, external services,
or credentials were used.
