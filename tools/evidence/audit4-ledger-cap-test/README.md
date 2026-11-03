# Audit 4: ledger cap regression evidence

Node: `audit4-ledger-cap-test`. Product mapping: A1, Q7, L1/L2, I1, M1,
P02/P03. See the [audit record](../../../docs/blueprint/audits/2026-11-03_ledger_cap_test.md)
and its entry in `09_제품목적_대응표.md`.

The current implementation already rejects ordinary reads at 100 records and
checks every reservation/settlement append against the checkpoint-relative cap.
No production logic, policy or policy hash was changed. The new loopback S3
regression covers ordinary sessions starting at 98, 99 and 100 records, checks
the exact HTTP PUT keys and retained original bytes, and verifies that a failed
settlement retains both admission and reservation allowances in every dimension.

The existing recovery regression now also verifies checkpoint PUT -> checkpoint
verification GET -> reservation PUT ordering, the settlement's reservation
reference, and 102 retained ledger records with only 2 records after checkpoint
100. Those extra 2 are the recovery reservation and settlement; the cap stays 100.
The checkpoint object and admission records have separate prefixes and still
incur metered request/byte costs. BUDGET.md documents the distinction from the
historical unchecked 100 -> 101 -> 102 path.

| Command | Result / evidence |
|---|---|
| `env -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -v` | 1,330 run, 1,324 passed, 6 existing skips, no failures/errors, exit 0: [Full Python log](python-tests.log), including all R2 tests |
| `cargo test --all --locked --offline` | 478 passed, 1 existing ignored, no failures, exit 0: [Rust log](rust-tests.log) |
| From `docs/blueprint/proposals/온톨로지/검증/runner`: `cargo test --locked --offline` | 3 passed, exit 0: [Runner log](runner-tests.log) |
| `python3 tools/evidence/audit4-ledger-cap-test/verify_mutations.py` | 3 in-memory mutants detected, exit 0: [Mutation log](mutation-tests.log) |
| Workflow, vocabulary, validation/self-test, spec, blueprint status/counts, whitespace | All passed, commands and exit codes: [Static checks](static-checks.log) |
| Allowed paths, protected paths, Python syntax, whitespace | Passed: [Scope check](scope-check.log) |

The mutation log's failures are intentional: the same new HTTP test rejects a
read guard changed from `>=` to `>`, removal of the append guard, and both defects
together. The harness additionally reproduces reservation 101 and settlement 102
from a 100-record ledger under the combined mutant. Production source is never
written by this harness. [Source hashes and parent HEAD](source-hashes.log) pin the
tested implementation, regression tests and reproduction script.

All commands ran in this worktree, using Rust 1.98.1 and boto3 1.43.100. The README's
directory-local Rust override was applied. Python discovery unsets the shared
`CARGO_TARGET_DIR` so the ontology tests find their local runner. Only temporary
local ledgers and loopback HTTP were used; no real R2, credentials, GitHub
operation, commit or push was used.

This is local archive-tool regression evidence. It does not close actual
disclosure acquisition, R2 observation reconciliation, consumer UX or first-release
completion requirements. P02/P03 remain open.

The 6 existing Python skips are 5 tests requiring private archived originals and
1 test for an older botocore without conditional PUT support. The new and updated
R2 regressions executed without skips.
