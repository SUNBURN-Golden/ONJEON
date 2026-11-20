# Audit 7 Git ignore rules for credential files

Verified on 2026-11-20 against `1e8ea79` and this worktree patch, then re-run
after merging `origin/main` (`7a3d51e`, the Audit 7 CI permissions and pins
node). The merge conflict in 09 §5 kept both Audit 7 paragraphs. The development
tool evidence is linked from [09 §5](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md#5-출시-완성품이-아닌-것혼동-방지).

The ignore files in `apps/`, `data/`, `infra/`, `packages/schemas/`,
`packages/rules-engine/`, `services/`, and `tools/` now cover `.env*`, `*.pem`,
`*.key`, `credentials*`, `.aws/`, and `*.tfstate`, alongside the existing `.venv/`
rule. The CI check rejects matching tracked paths anywhere in the repository.
The checked-in `infra/compose/.env.example` placeholder is the tracked template
exception. The Compose static test checks that its secret fields are empty.

The node's path allowlist excludes the root `.gitignore`. The local ignore gap
there remains. A matching path created outside the seven trees can still be
staged. The tracked-path check detects it in the index, and remote CI runs
after a push.

## Regression evidence

The new cases failed against the baseline for each of the three missing patterns.
After the fix, Git reported all 133 matching probes as ignored across the seven
trees. In a disposable local repository, `git add --all` staged only the ignore
files and the control paths. The controls include a plain file named `.aws`,
which is distinct from a directory with that name. A second disposable repository
proved that the CI command reports matching index entries at the root and in
nested paths. The tests use empty synthetic files. A separate `git check-ignore`
probe at the worktree root returned exit 1 for all six filename patterns.

| Check | Result |
|---|---|
| `python3 -m unittest tools/tests/test_gitignore.py tools/tests/test_tracked_secrets.py -v` | 12 passed |
| `python3 -I tools/check_tracked_secrets.py` | Exit 0 on the worktree index |
| `python3 -I tools/check_tracked_secrets.py --selftest` | 26 path cases passed |
| `python3 -m unittest discover -s tools/tests -v` | 1,737 run, 6 skipped, exit 0 (post-merge; 1,732 before the merge) |
| `python3 -I -m unittest discover -s tools/ci/tests` | 21 passed |
| `python3 -m unittest discover -s infra/compose/tests -p test_compose_static.py -v` | 32 passed, 1 skipped because ShellCheck was unavailable |
| `cargo test --all --locked --offline` | 537 passed, 1 ignored |
| `cargo test --manifest-path services/scenario-api/Cargo.toml --locked --offline --target-dir target/scenario-api` | 4 passed |
| Ontology runner `cargo test --locked --offline` | 4 passed |
| Design bundle `spec_check.py` and `tools/ci/check_product_purpose.py` | 119 design bundle checks passed and product-purpose links validated |
| `git diff --check` | Exit 0 |

The six Python skips were five archive-dependent tests and one test for legacy
Botocore. The ignored Rust test regenerates a declared fixture.
