# Audit 6 — source workflow secret scope

Date: 2026-11-15. Node: `audit6-sources-workflow-secret-scope`.
Scope and P03 traceability: [audit record](../../../docs/blueprint/audits/2026-11-15_sources_workflow_secret_scope.md),
[BLUEPRINT §11](../../../docs/BLUEPRINT.md),
[09 product purpose table](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md).

The baseline already scopes the five R2 secret bindings to the two archive
consumer steps, pins direct pip dependencies, and declares read-only CI token
permissions. Those settings remain in place. This change routes bucket variables
through the reproduction job's non-secret environment and quotes their shell
expansion instead of interpolating repository variables into shell source.

Reproduce from the worktree root, keeping Cargo build output in this worktree:

```sh
export RUSTUP_TOOLCHAIN=1.98.1
export CARGO_TARGET_DIR="$PWD/target/audit6-sources"
python3 -m unittest discover -s tools/tests -p 'test_workflow*.py' -v
python3 -m unittest discover -s tools/tests -p test_ci_workflow_security.py -v
python3 tools/workflow_check.py .github/workflows/ci.yml .github/workflows/pr-traceability.yml
python3 -m unittest discover -s tools/tests -v
cargo test --all --locked --offline
cargo fmt --all -- --check
cargo clippy --locked --offline --all-targets -- -D warnings
cargo test --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml
python3 tools/vocab_check.py
python3 tools/validation_check.py
python3 tools/validation_check.py --selftest
python3 -I tools/ci/check_product_purpose.py
python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py
python3 -I tools/blueprint_counts.py
python3 -I tools/check_tracked_secrets.py
```

The machine-readable [Python check record](python-checks.json) and
[Rust check record](rust-checks.json) contain exact commands, exit codes and elapsed
times. Each named check has a corresponding `.log` file in this directory.

- [Baseline regression](before-variables.log): the new environment-binding contract
  fails against an in-memory copy of the local HEAD workflow, before this fix.
- [Workflow regressions](workflow-tests.log): 37 pass, including three new tests
  for environment binding, four inline-variable mutations, and four combinations
  of actual Bash consumer scripts with ordinary/hostile values and both OCR modes.
- [CI security regressions](ci-security-tests.log): 5 pass, including removal or
  broadening of the actual workflow's permissions and checkout/action mutations.
- [Full Python discovery](python-tests.log): 1,633 run, no failures/errors,
  6 existing skips (five need private local originals, one targets older botocore).
  All new tests execute. Vocabulary, validation, its 40 mutation selftests,
  product-purpose mapping, design specification, blueprint counts and tracked
  credential checks all exit 0.
- [Rust workspace](rust-tests.log): 532 pass, 1 existing ignored; formatting and
  Clippy pass. [Ontology runner](ontology-tests.log): 4 pass.

[Source hashes](source-hashes.json) identify the verified workflow and security
test sources. [Final checks](final-checks.log) confirm authorized changed paths,
secret-reference counts and clean whitespace checks.

No GitHub calls, R2 operations, credential reads, commits or pushes were made.
These are local workflow/tool checks. Actual R2 observations, product data, twins,
consumer screens and P01–P19 release evidence remain separate.
