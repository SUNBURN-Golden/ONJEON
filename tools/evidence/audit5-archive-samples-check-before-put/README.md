# Audit 5: check sample hashes before put_raw

The base already contains Audit 2's fix: read once, compare the byte hash with
`samples.csv`, then pass the same bytes to `put_raw` only on a match. This node
preserves that behavior, documents the snapshot requirement in code, and adds
two regressions using synthetic documents and real temporary local stores.

The recovery regression checks rejection without creating either store,
repair and successful raw/observation/derived storage, later rejection with
byte-for-byte preservation of both stores, and an idempotent repaired rerun.
The snapshot regression replaces or removes the cache after verification and
checks that the original bytes, hash and observation size are still archived.

The mutation script changes only an in-memory function. Three tests reject
upload-before-check, including the new recovery regression. The new snapshot
test rejects rereading the cache after verification (both replacement and
removal subcases). The intentional unittest failures/errors in the log are
followed by `MUTATION REJECTED`; the script requires all selected tests to
reject their mutant, with no skips, and exits 0.

Commands run on 2026-11-10 from the worktree root, with Rust 1.98.1 and
boto3 1.43.100. `runner` means `docs/blueprint/proposals/온톨로지/검증/runner`.
Each log records the command's exit code.

| Command | Evidence |
|---|---|
| `python3 tools/evidence/audit5-archive-samples-check-before-put/check_order_mutations.py` | Two mutants rejected, exit 0: [mutation log](mutations.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_source_archive*.py' -v` | 69 passed, no skips, exit 0: [archive tests](archive-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,405 run, 1,399 passed, 6 existing skips, no failures/errors, exit 0: [Python tests](python-tests.log) |
| `cargo test --all --locked --offline` | 513 Rust tests passed (including 3 doctests), 1 existing ignored; embedded Python suites 39 and 129 passed; exit 0: [workspace tests](rust-tests.log) |
| In `runner`: `cargo test --locked --offline` | 4 passed, exit 0: [runner tests](runner-tests.log) |
| Vocabulary, validation, validation self-test, design specs, Blueprint counts, whitespace | All exit 0; exact commands/results: [static checks](static-checks.log) |
| Allowed paths, Python syntax and local Markdown links | Passed: [scope checks](scope-checks.log) |

Five Python skips require private local archived originals (three also require
`pdftotext`); the sixth tests an old botocore version and does not apply to the
installed conditional-PUT-capable version. Both added regressions, their
subcases and the R2 upload-boundary tests ran without skips.

Product mapping: A1, Q7, L1, I6, M1, P02/P03. These are local archive-tool
finding closure evidence; actual disclosure acquisition, R2 reconciliation,
consumer UX and first-release completion remain separate requirements. See the
[audit record](../../../docs/blueprint/audits/2026-11-10_archive_samples_check_before_put.md)
and its entry in `09_제품목적_대응표.md`. No actual R2 requests or existing archive
deletion/recovery were performed.
