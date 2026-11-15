# Audit 6: source URL host allowlist

`audit6-verify-sources-url-allowlist` is resolved by admitting only HTTPS URLs
whose exact hosts appear in `data/registry/source_fetch_hosts.json`. Existing
same-origin redirect checks also reject movement to another registered host.
The baseline already rejected non-HTTPS URLs, including `file://`, and
HTTPS→HTTP redirects. Its remaining gap was arbitrary initial HTTPS hosts.

The explicit registry contains 68 hosts with local source references. A new
sample URL cannot register its own host. Missing or malformed registry data
fails before an opener is built. Tests cover hostname lookalikes, local and
metadata addresses, every redirect code, final URL rejection before reading,
no retries/writes on rejection, and successful HTTPS archiving. Loopback hosts
exist only in temporary test registries. No insurer, R2, or GitHub was contacted.

Baseline: `94c8b64cefb1ced5341d3e24e690915d085b3d5b`.
Commands, exit codes, environment overrides and final source hashes are in
[run-summary.json](run-summary.json). Cargo output and the ontology runner use
`target/audit6-verify-sources` inside this worktree.

| Command | Result / evidence |
|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_verify_sources*.py' -v` | Exit 0; 69 run, 66 passed, 3 existing archive skips: [focused tests](focused-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | Exit 0; 1,636 run, 1,630 passed, 6 existing skips: [full Python](python-tests.log) |
| `cargo +1.98.1 test --all --locked --offline` | Exit 0; 532 passed, 1 existing ignored; embedded Python suites 39 and 129 passed: [workspace tests](rust-tests.log) |
| `cargo +1.98.1 test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | Exit 0; 4 passed: [static checks](static-checks.log) |
| `python3 tools/evidence/audit6-verify-sources-url-allowlist/check_mutations.py` | Exit 0; baseline regressions and all three in-memory policy-removal mutants rejected by assertion failures, no errors/skips: [mutations](mutations.log) |
| Vocabulary, validation/self-test, blueprint counts/status, product purpose, design bundle, ontology, Rust format, whitespace | All exit 0: [checks](static-checks.log), [exit codes](static-results.json) |
| Allowed/protected paths, Python syntax, Markdown links, registry metadata | Passed: [scope checks](scope-checks.log) |

The initial focused run failed 15 tests/subtests because loopback hosts were
not registered. The tests now provide isolated temporary registries instead
of admitting loopback in production. The [initial log](initial-tests.log) is
preserved. The runner [build](runner-build.log) completed with exit 0 before
Python discovery. Five existing Python skips require private archived originals;
the sixth targets old botocore without conditional PUT support.

Product mapping: A1, Q7, L0/L1, I6, M1, P02/P03. See the
[audit record](../../../docs/blueprint/audits/2026-11-16_verify_sources_url_allowlist.md)
and its entry in `09_제품목적_대응표.md`. This is local collection-tool evidence;
actual disclosure acquisition, R2 observation reconciliation, product/contract
twins, consumer screens and first-release completion remain separate criteria.
