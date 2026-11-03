# Audit 4: R2 status endpoint disclosure

`tools/r2_budget.py` now runs its CLI through `main()`, which handles botocore's
`BotoCoreError` and `ClientError` using the same convention as `source_archive.py`:
print the exception type with `(message and endpoint withheld)` to stderr and
return exit code 5. This covers errors before a session opens and errors during
status retrieval, and applies to the shared CLI entrypoint's other subcommands.
Budget refusals retain exit code 4, unexpected programming errors still propagate,
and the existing status JSON and settlement behavior remain unchanged.

The regressions inject real botocore exception objects containing a synthetic
account URL at session startup and ledger reads. They check both output streams
for the account ID, URL, exception message and traceback, and check exit code 5.
A successful run uses a temporary local ledger and verifies the JSON report,
persisted settlement and released active session. The budget refusal regression
checks the original exception identity and exit code.

All commands ran in this worktree. The already-installed Rust toolchain was
selected with the root README's directory-local setup:
`rustup override set --path "$PWD" 1.98.1`. No real R2 service, credentials,
GitHub operation, commit or push was used. The URL in the pre-fix failure log is
the synthetic account fixture already used by `test_r2_budget.py`.

| Command / check | Evidence |
|---|---|
| Original entrypoint behavior: invoke `_cli()` directly for `StatusCli` (see reproduction below) | 4 tests, 4 storage-error subtest errors; the other tests pass: [before-tests.log](before-tests.log) |
| `python3 -m unittest discover -s tools/tests -p test_r2_budget.py -k StatusCli -v` | 4 passed, exit 0: [regression-tests.log](regression-tests.log) |
| Separate process: inject `EndpointConnectionError` from `S3Store`, run the script via `runpy.run_path(..., run_name="__main__")` with `ONJEON_GATE_DIR` in a temporary directory | Exit 5; stdout empty; stderr exactly the sanitized error: [cli-smoke.log](cli-smoke.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,341 run, 1,335 passed, 6 existing skips, no failures/errors, exit 0: [python-tests.log](python-tests.log) |
| `cargo test --all --locked --offline` | 478 passed, 1 existing ignored, exit 0: [rust-tests.log](rust-tests.log) |
| `cargo test --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml` | 3 passed, exit 0: [runner-tests.log](runner-tests.log) |
| Workflow, vocabulary, validation and its self-test, product-purpose, spec, blueprint counts, whitespace | All passed; exact commands and exit codes: [static-checks.log](static-checks.log) |
| Allowed paths, protected paths, Python syntax and whitespace | [scope-check.log](scope-check.log) |

To reproduce the original entrypoint behavior without changing files:

```sh
python3 - <<'PY'
import sys
import unittest
sys.path.insert(0, 'tools/tests')
import test_r2_budget
test_r2_budget.b.main = test_r2_budget.b._cli
suite = unittest.defaultTestLoader.loadTestsFromTestCase(test_r2_budget.StatusCli)
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
PY
```

Product mapping: A1/A2/A4, Q7, L1, I1, M1, P02/P03. This is local archive-tool
regression evidence. It does not close actual disclosure acquisition, R2
observation reconciliation, consumer UX or first-release completion requirements.
See the [audit record](../../../docs/blueprint/audits/2026-11-03_r2_status_endpoint_leak.md)
and its linked entry in `09_제품목적_대응표.md`.
