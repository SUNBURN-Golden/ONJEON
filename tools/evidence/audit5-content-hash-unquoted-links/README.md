# Audit 5: unquoted href and fileDown targets

The reported `LINK_RE` defect was already fixed by Audit 2 in this worktree's
base. The production v3 `HTMLParser` implementation and rule name are retained.
This node adds three regressions for the exact reported forms, real baseline
byte hashes, CLI JSON classification and downloaded-byte preservation.

The hash tests cover `fileDown('x.pdf')` on links/buttons with quoted, unquoted,
uppercase, return-statement and entity-encoded attributes. An unquoted link
keeps its filename, document ID and fragment while ignoring session-only
changes. The CLI test checks unchanged bytes and filename-only changes for
unquoted href and link/button `fileDown` handlers. Existing tests also check
`bytes_changed_content_same` for session-only changes and reject comparisons
against older hash rules.

Commands run on 2026-11-10 in this worktree with Rust 1.98.1:

| Command | Result / evidence |
|---|---|
| `python3 -m unittest discover -s tools/tests -p test_html_content_hash.py -v` | 25 run, 23 passed, 2 existing archive skips, exit 0: [hash tests](hash-tests.log) |
| `python3 -m unittest discover -s tools/tests -p test_verify_sources.py -v` | 37 run, 34 passed, 3 existing archive skips, exit 0: [CLI/detect tests](detect-tests.log) |
| `python3 tools/evidence/audit5-content-hash-unquoted-links/check_link_mutations.py` | Both mutants rejected by each assigned hash/CLI test, exit 0: [mutation log](link-mutations.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,418 run, 1,412 passed, 6 existing skips, exit 0: [full Python tests](python-tests.log) |
| `cargo +1.98.1 test --all --locked --offline` | 513 passed, 1 existing ignored; embedded Python suites 39 and 129 passed, exit 0: [workspace tests](rust-tests.log) |
| `cargo +1.98.1 test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4 passed, exit 0: [runner tests](runner-tests.log) |
| Vocabulary, validation/self-test, product-purpose links, design bundle, blueprint counts, format, lint, whitespace | All passed; exact commands and exit codes: [static checks](static-checks.log), [results](static-results.json) |
| Allowed/protected paths, Python syntax, local Markdown links, unchanged production module | Passed: [scope checks](scope-checks.log) |

Five existing full-suite skips require private archived originals (three also
require `pdftotext`). The sixth targets old botocore versions without
conditional PUT support. All three new regressions ran without skips.
The [run summary](run-summary.json) records the base commit, successful command
exit codes, and source/log SHA-256 hashes.

The [mutation script](check_link_mutations.py) removes unquoted href or onclick
attributes only in memory. Its expected assertion failures are followed by four
`MUTATION REJECTED` messages; it succeeds only if every selected test catches
its mutation without errors or skips. The production file is never rewritten.

The ontology runner was built before Python discovery with
`cargo +1.98.1 build --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir docs/blueprint/proposals/온톨로지/검증/runner/target --locked --offline`
([build log](runner-build.log)).

Product mapping: A1, Q7, L1, I6, M1, P02/P03. See the
[audit record](../../../docs/blueprint/audits/2026-11-10_content_hash_unquoted_links.md)
and its entry in `09_제품목적_대응표.md`. Synthetic HTML, mocked fetches and
temporary local files were used. This is local change-detection regression
evidence, not actual disclosure acquisition, change propagation, consumer UX
or first-release completion evidence.
