# Audit 2 duplicate keys — fix round 1

The execution-loader finding remains **unresolved**. The node allowlist excludes
`packages/twin-runtime/**`; neither its loader nor its tests have been edited.
`runtime-loader.patch` contains the exact pending change for those files. It uses
the new public engine parser before removing artifact metadata, then keeps the
existing DSL validation and hashing. The patch includes three runtime regression
tests, including nine duplicate-key cases for each DSL version.

Implemented within the allowlist:

- Public `onjeon_rules_engine::parse_rule_json(&[u8])` uses the existing recursive
  duplicate-rejecting deserializer; `Rule::from_json_str` shares that implementation.
- Engine tests cover the byte parser, duplicate artifact metadata, invalid UTF-8,
  malformed/trailing JSON, and preservation of source, hash and evaluation after
  metadata removal. All existing duplicate tests also exercise the byte parser.
- Two schema test callers now load raw rules with `Rule::from_json_str`.
- BLUEPRINT, engine README and audit report explicitly disclose the runtime bypass.

## Reproduce the current runtime failure

From the worktree root:

```sh
cargo build -p onjeon-twin-runtime --offline
rustc --edition=2021 --test tools/evidence/audit2-engine-duplicate-json-keys-round1/runtime_loader.rs -L dependency=target/debug/deps --extern onjeon_twin_runtime=target/debug/libonjeon_twin_runtime.rlib -o target/audit2-runtime-loader-regression
target/audit2-runtime-loader-regression
```

This links directly to the actual, unchanged runtime crate. `runtime-before.log`
records **2 passed, 1 failed** (exit 101): the duplicate `amount` rule loads with
`Money(100000000)` and a content hash. This is evidence of an outstanding defect,
not a passing check. The other tests preserve valid metadata handling and existing
malformed JSON/declaration rejection.

## Pending runtime patch

`git apply --check tools/evidence/audit2-engine-duplicate-json-keys-round1/runtime-loader.patch`
passes. The patch has **not** been applied. Its runtime tests are identical to
`runtime_loader.rs`. Applying it requires authorization to edit these paths:

- `packages/twin-runtime/src/input_stage.rs`
- `packages/twin-runtime/tests/duplicate_json_keys.rs`

After that authorization, apply the patch, run
`cargo test -p onjeon-twin-runtime --test duplicate_json_keys --offline`, rerun the
workspace checks, and update the documentation to match those results. Do not
claim the finding is resolved while the patch remains unapplied.

## Checks for the implemented changes

- `cargo test -p onjeon-rules-engine --test loader_and_arith --offline`: 15 passed,
  0 failed (`loader.log`).
- `cargo test --all --offline`: 416 Rust tests passed, 0 failed, 1 ignored
  (`workspace.log`); embedded Python suites also passed.
- `cargo fmt --all -- --check`: passed (`fmt.log`).
- `cargo clippy --all-targets --offline -- -D warnings`: passed (`clippy.log`).
- `python3 -I tools/blueprint_status.py`: decision index current (36 ADR/DEC files).

No commit, push, GitHub call, production action, or decision about money, legal
matters, or secrets was made. No `DECISION_REQUIRED.md` was created: the remaining
blocker is the edit allowlist, not an irreversible decision.
