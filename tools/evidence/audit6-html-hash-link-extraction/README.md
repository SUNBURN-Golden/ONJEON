# Audit 6: HTML hash link extraction

The reported regex defects are already resolved in the baseline commit
`96a1fa44273aed8be9b6fa585334d80f4328e628`. Production uses `HTMLParser`:
it preserves every nonempty `onclick`, parses quoted/unquoted attributes, and
matches attribute names exactly. Production code and `html-visible-text-v3`
remain unchanged; existing hashes and archived observations were not rewritten.

This node adds three hash regressions and one CLI regression for the exact
`fnDown('x.pdf')`, `href=x.pdf` and `data-href` shadowing findings. The hash tests
cover handler quoting/entities, links/buttons/inputs, both attribute orders and
all three href quoting styles. The CLI test uses real baseline byte hashes and
checks `unchanged_bytes`, filename-only `changed`, and decoy-only
`bytes_changed_content_same`, including both byte hashes and saved response bytes.

[Mutation checks](check_link_mutations.py) remove `fnDown` handlers, remove
unquoted hrefs, or promote the first `data-href` to the real link. Each mutant
must fail its hash test and the CLI test with assertions (no errors or skips).
All six checks rejected their assigned mutant: [mutation log](link-mutations.log).
Mutations apply only in memory; production files are never rewritten.

Commands ran on 2026-11-15 with Rust 1.98.1, an isolated Cargo target directory
inside this worktree, and a runner built before Python discovery. Exact argv,
environment overrides and exit codes are in [run summary](run-summary.json).

| Command | Result / evidence |
|---|---|
| `python3 -m unittest discover -s tools/tests -p test_html_content_hash.py -v` | 28 run, 26 passed, 2 existing archive skips, exit 0: [hash tests](hash-tests.log) |
| `python3 -m unittest discover -s tools/tests -p test_verify_sources.py -v` | 39 run, 36 passed, 3 existing archive skips, exit 0: [CLI/detect tests](detect-tests.log) |
| `python3 tools/evidence/audit6-html-hash-link-extraction/check_link_mutations.py` | Six mutation/test pairs rejected, exit 0: [mutations](link-mutations.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,616 run, 1,610 passed, 6 existing skips, exit 0: [full Python tests](python-tests.log) |
| `cargo +1.98.1 test --all --locked --offline` | 532 passed, 1 existing ignored; embedded Python suites 39 and 129 passed, exit 0: [workspace tests](rust-tests.log) |
| `cargo +1.98.1 test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4 passed, exit 0: [runner tests](runner-tests.log) |
| Vocabulary, validation/self-test, product-purpose and design bundle checks, whitespace | All exit 0: [static checks](static-checks.log), [exit codes](static-results.json) |
| `cargo +1.98.1 fmt --all -- --check` | Exit 0: [format](format-check.log) |
| Allowed/protected paths, Python syntax, local Markdown links and unchanged production module | Passed: [scope checks](scope-checks.log) |

Five existing Python skips require private archived originals (three also
require `pdftotext`). The sixth targets old botocore versions without
conditional PUT support. All four new regressions ran without skips.

Runner preparation: `CARGO_TARGET_DIR="$PWD/target/audit6-html-hash" cargo +1.98.1 build --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline`
completed with exit 0 ([build log](runner-build.log)). The run-summary environment
overrides apply to every command in that summary.

Product mapping: A1, Q7, L1, I6, M1, P02/P03. See the
[audit record](../../../docs/blueprint/audits/2026-11-15_html_hash_link_extraction.md)
and its entry in `09_제품목적_대응표.md`. Synthetic HTML, mocked fetches and
temporary local files provide tool regression evidence. Actual disclosure
acquisition, change propagation, product twins, consumer screens and first-release
completion remain separate requirements.
