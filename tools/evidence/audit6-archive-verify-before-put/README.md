# Audit 6: compare before archive writes; verify fetched bytes

The reported bugs were already fixed in this worktree's base. Production code
is preserved: compare the cache snapshot against `samples.csv` before `put_raw`,
store those same bytes, and hash downloaded bytes before creating or overwriting
restore files. A failed fetch returns 1 without printing `restored originals`.

The new regression exercises both commands through `main()` with temporary
samples and real local archive I/O. It rejects a same-length bad cache before
creating the archive, retries with accepted bytes, preserves the archive when
the cache changes again, restores accepted bytes, then simulates external
corruption of the stored object. Both existing and absent restore destinations
remain protected; the existing observation remains unchanged.

`check_mutations.py` changes only in-memory functions. The new test detects all
four mutations: archive/fetch check removal and archive/fetch check after write.
Its expected assertion failures appear in the log before `MUTATION REJECTED`.
Skipped tests or unrelated execution errors do not qualify as detection.

Commands run on 2026-11-15 from this worktree, with Rust 1.98.1 and boto3 1.43.100:

| Command | Result / evidence |
|---|---|
| `python3 -m unittest tools.tests.test_source_archive_commands.ArchiveCommands.test_cli_rejects_bad_cache_and_corrupt_store_through_archive_restore_lifecycle -v` | 1 passed, exit 0: [CLI lifecycle](lifecycle-test.log) |
| `python3 tools/evidence/audit6-archive-verify-before-put/check_mutations.py` | All four mutations rejected, exit 0: [mutations](mutations.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_source_archive*.py' -v` | 73 passed, no skips, exit 0: [archive tests](archive-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,610 run; 1,604 passed; 6 existing skips, exit 0: [full Python tests](python-tests.log) |
| `RUSTUP_TOOLCHAIN=1.98.1 cargo test --all --locked --offline` | 532 passed, 1 existing ignored; embedded Python suites 39 and 129 passed, exit 0: [workspace tests](workspace-tests.log) |
| `RUSTUP_TOOLCHAIN=1.98.1 cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4 passed, exit 0: [ontology runner tests](runner-tests.log) |
| `python3 -I tools/ci/check_product_purpose.py` | Exit 0: [product-purpose links](purpose-check.log) |
| `python3 tools/validation_check.py` | Exit 0: [validation metadata consistency](validation-check.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 118 checks passed, exit 0: [design bundle](spec-check.log) |
| Allowed paths, Python syntax, new Markdown links, whitespace | Passed, exit 0: [scope checks](scope-checks.log) |

The archive suite includes real `S3Store` with botocore Stubber: no requests for
mismatched uploads, forged/missing server checksums on fetched bytes, stream
closure, preserved prior restores, stopped later GETs, valid empty bytes and
CLI failure propagation into mocked budget settlement. Synthetic credentials
and responses are used; no production archive access or credentials are needed.

The six existing full-suite skips are five private-local-archive-dependent
tests (three also need `pdftotext`) and one old-botocore compatibility test that
does not apply to the installed version. All 73 archive regressions ran without
skips. The Rust workspace retains the existing ignored
`regenerate_declared_abox_fixture` test.

Product mapping: A1, Q7, L1, I6, M1, P02/P03. See the
[audit record](../../../docs/blueprint/audits/2026-11-15_archive_verify_before_put.md)
and its link in `09_제품목적_대응표.md`. This closes the local archive-tool finding;
it does not establish actual disclosure acquisition, R2 observation
reconciliation, digital twins, consumer UX or first-release completion.
