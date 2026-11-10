# Audit 5 — ignore local credentials and virtual environments

Date: 2026-11-10. Node: `audit5-gitignore-secret-files`.
Baseline: `308b4fa28f5dec99d212d9a8477d019f4d8a5e89` plus this node's changes.

## Why the rules are not only in the root file

The finding asks for `.env*`, `*.pem`, `*.key` and `.venv/` ignore rules. The
repository-root `.gitignore` is outside this node's `allowed_paths`, so changing
it is rejected and that change was reverted. The same policy is installed in two
allowed layers instead:

1. **Per-tree ignore files.** `apps/.gitignore`, `data/.gitignore`,
   `infra/.gitignore`, `packages/schemas/.gitignore`,
   `packages/rules-engine/.gitignore`, `services/.gitignore` and
   `tools/.gitignore` each contain the four rules. Git applies a directory's
   ignore file to that whole subtree, so local files named `.env`, `.env.*`,
   `*.pem`, `*.key` or inside `.venv/` stay untracked there.
2. **Tracked-path gate.** [`tools/check_tracked_secrets.py`](../../check_tracked_secrets.py)
   reads `git ls-files` and exits 1 if any tracked path has one of those names at
   any depth (including the repository root). `.github/workflows/ci.yml` runs it
   before dependency installation. This covers the root paths that the per-tree
   files cannot cover.

`infra/compose/.env.example` is the only allowed tracked `.env*` path. It is the
placeholder template copied to `.env` by `infra/compose/up.sh`; its password and
key fields are empty and `infra/compose/tests/test_compose_static.py` keeps them
empty. The ignore rule still hides a newly created `.env.example`; the existing
template is tracked because it predates the rule.

## Tests

`tools/tests/test_gitignore.py` reads the seven actual ignore files. It uses
`git check-ignore --no-index` in this worktree (with global/system excludes and
`GIT_*` environment removed) to prove root and nested credential paths are
ignored, while `env.example`, `certificate.pem.txt`, `private.key.example` and
`.venv-notes/` are not. A disposable repository copies the same ignore files and
runs `git add --all` to prove ordinary staging keeps the controls and drops the
sensitive names.

`tools/tests/test_tracked_secrets.py` covers each sensitive kind and near match,
the one template exception, clean and dirty disposable repositories through the
CLI exit code, the live tree, the selftest, and the `ci.yml` wiring. Synthetic
files are empty; no credential values are created or read, and nothing is staged
in this worktree.

Reproduce from the worktree root:

```sh
python3 -m unittest tools/tests/test_gitignore.py tools/tests/test_tracked_secrets.py -v
python3 -I tools/check_tracked_secrets.py
python3 -I tools/check_tracked_secrets.py --selftest
python3 -m unittest discover -s tools/tests -v
cargo test --all --locked --offline
git diff --check
```

## Results

| Command | Result | Evidence |
|---|---|---|
| Focused ignore and gate tests | Exit 0; 12 tests pass | [focused-tests.log](focused-tests.log) |
| Tracked-path gate and selftest | Exit 0; live tree clean; 16 selftest paths pass | [tracked-secrets-check.log](tracked-secrets-check.log) |
| `python3 -m unittest discover -s tools/tests -v` | Exit 0; 1,443 run, 6 skips, no failures/errors | [python-tests.log](python-tests.log) |
| `cargo test --all --locked --offline` | Exit 0; 513 passed, 1 pre-existing ignored | [rust-tests.log](rust-tests.log) |
| `git diff --check` | Exit 0 | [diff-check.log](diff-check.log) |
| Changed paths and root ignore file | Root `.gitignore` unchanged; all changes in allowed trees | [scope-check.log](scope-check.log) |

## Limits

Ignore rules and the gate govern tracked content only. They do not remove files
that are already tracked, and they do not stop a forced `git add -f`; the gate
does stop such a path from passing CI once it is tracked. Untracked root-level
`.env` or `.venv/` files are not ignored locally because the root `.gitignore` is
out of scope, but they cannot reach a merged commit without the CI gate failing.
Pattern-based path matching cannot prove that every possible credential filename
is covered. This is local development-tool evidence following
[09 §5](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md);
it does not establish a product-purpose row or first-release completion.
