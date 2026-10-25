Round 2 verification for `audit1-workflows-pin-actions-by-sha`.

Parent HEAD: `66764b64f81bd2f04a3f28987474bf5528b60245`. Source and complete-log hashes are in [manifest.json](manifest.json).

The prerequisite merge `b7e20f9` is an ancestor of this HEAD. Both checkouts in `ci.yml` have `persist-credentials: false`, and top-level permissions are exactly `contents: read`. All six action references already match the operator's exact supplied SHAs and comments. Both workflows are byte-identical to HEAD; this round edits neither workflow. See [baseline-verification.log](baseline-verification.log).

The stdlib guard now reads flow-style mappings, including quoted keys/values, multiple entries per line, and multiline flow mappings. It preserves the local-action exemption and skips comments and script strings. Regression tests inject tagged actions into both `.yml` and `.yaml` workflows and composite actions, require the repository guard to reject each file/ref, then replace the tag with a full SHA and require success. Restoring either the old block-only regex or `.yml`-only discovery makes the new tests fail: [guard-mutations.log](guard-mutations.log).

Commands and actual results on the final test source:

| Command | Exit | Result / complete evidence |
|---|---:|---|
| `python3 -m unittest discover -s tools/tests -p 'test_workflow*.py' -v` | 0 | 18 passed; [workflow-focused.log](workflow-focused.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1 | 479 run: 467 passed, 6 errors, 6 skipped; [python-tools-final.log](python-tools-final.log) |
| `CARGO_NET_OFFLINE=true cargo test --offline --locked --all --no-fail-fast` | 101 | All targets attempted: 386 passed, 1 failed, 1 ignored; embedded Python suites: 39/39 and 129/129 passed; [rust-tests-final.log](rust-tests-final.log) |
| `cargo fmt --all -- --check` | 0 | [rust-format.log](rust-format.log), empty because no formatting differences |
| `cargo clippy --offline --locked --all-targets -- -D warnings` | 0 | [rust-clippy.log](rust-clippy.log) |
| `python3 tools/vocab_check.py` | 0 | [vocabulary.log](vocabulary.log) |
| `python3 tools/validation_check.py` | 0 | [validation.log](validation.log) |
| `python3 tools/validation_check.py --selftest` | 0 | 38 mutations caught; [validation-selftest.log](validation-selftest.log) |
| `python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py docs/blueprint/proposals/온톨로지/검증/runner/target/debug/ontology-case-runner` | 0 | [ontology.log](ontology.log); runner built offline by the tools suite |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 0 | 44 mechanical checks and 72 existence checks passed; [design-specs.log](design-specs.log) |
| `python3 -I -m unittest discover -s tools/ci/tests -v` | 1 | Additional suite: 20 run, 16 passed, 2 failures, 2 errors; [python-ci.log](python-ci.log) |

Full-suite success is **not established** in this sandbox. The six tools-suite errors, the Rust `local_s3_wire_put_head_get_list_and_precondition` failure, and the two additional CI-suite errors all occur when creating localhost sockets: `PermissionError: [Errno 1] Operation not permitted`. The tools suite's six skips are five private-archive prerequisites and one obsolete-botocore compatibility case. The Rust ignored case is the fixture regeneration helper.

The additional CI suite's two assertions report the same three existing dependency-zone findings: `packages/ontology/Cargo.toml:15`, `packages/ontology/tests/common/mod.rs:350`, and `packages/ontology/tests/fixture_origin/main.rs:126`. These files, the checker, its tests/common code, and `infra/ci/deps.json` were checked byte-for-byte against HEAD and are unchanged. Resolving those architecture findings is outside this action-pinning change.

The first all-target Rust run also hit crates.io DNS failure in a nested Cargo probe. Re-running with `CARGO_NET_OFFLINE=true` propagated offline mode to subprocesses and passed that codegen suite; only the socket failure remains in the final Rust log. No test was disabled or changed to hide these failures.

GitHub was neither queried nor called, and no commit or push was made. The reported `no-ci-runs` condition still needs supervisor-provided CI evidence on a runner that permits localhost test servers. This report records local execution and does not claim a successful CI run.
