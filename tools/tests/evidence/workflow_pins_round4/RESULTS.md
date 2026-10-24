Round 4 verification for `audit1-workflows-pin-actions-by-sha`.

Parent HEAD: `c4470a6aac886daf2011d65409c74f5aa3c82b61`. Source and complete-log SHA256 hashes are recorded in [manifest.json](manifest.json).

The pin guard now reads the complete inline action scalar before validating its ref. An attached `#mutable` remains part of the value; a comma remains part of a block-mapping value and separates entries only inside a flow collection. Whitespace-separated comments and quoted scalars are handled separately. Brackets in plain step names do not establish flow context for following action values.

Regressions cover SHA-shaped prefixes with hash, comma, and whitespace suffixes; quoted keys and values; real comments; single-line and multiline flow mappings; and brackets in step names. The repository guard also rejects both reviewer suffixes in temporary `.yml` and `.yaml` workflows and composite actions, then accepts replacement SHA pins. Running the final tests with the HEAD parser yields 26 failing subcases ([regressions-before.log](regressions-before.log)); the fixed parser passes all 23 workflow-focused tests ([workflow-focused.log](workflow-focused.log)). Direct checks retain both complete reviewer values in diagnostics ([guard-examples.log](guard-examples.log)).

Both workflows are byte-identical to HEAD. All six refs already exactly match the operator-supplied SHAs and comments: four checkouts and two artifact uploads ([baseline-verification.log](baseline-verification.log)). No protected file was edited, no GitHub lookup was made, and no commit or push was made.

| Command | Exit | Result / evidence |
|---|---:|---|
| `python3 -m unittest discover -s tools/tests -p 'test_workflow*.py' -v` | 0 | 23 passed; [workflow-focused.log](workflow-focused.log) |
| Full `tools/tests` discovery with the harness below | 1 | 484 run: 472 passed, 6 errors, 6 skipped; [python-tools.log](python-tools.log) |
| `cargo test --offline --locked --all --no-fail-fast` | 101 | 386 passed, 1 failed, 1 ignored; embedded Python suites: 39 and 129 passed; [rust-tests.log](rust-tests.log) |
| `python3 -I -m unittest discover -s tools/ci/tests -v` | 1 | 20 run: 16 passed, 2 failures, 2 errors; [python-ci.log](python-ci.log) |
| `cargo fmt --all -- --check` | 0 | [rust-format.log](rust-format.log) |
| `cargo clippy --offline --locked --all-targets -- -D warnings` | 0 | [rust-clippy.log](rust-clippy.log) |
| `python3 tools/vocab_check.py` | 0 | [vocabulary.log](vocabulary.log) |
| `python3 tools/validation_check.py` | 0 | [validation.log](validation.log) |
| `python3 tools/validation_check.py --selftest` | 0 | 38 mutations caught; [validation-selftest.log](validation-selftest.log) |
| `python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py target/round4-ontology/debug/ontology-case-runner` | 0 | [ontology.log](ontology.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 0 | [design-specs.log](design-specs.log) |

All Python commands use `PYTHONDONTWRITEBYTECODE=1`; Cargo and its subprocesses use `CARGO_NET_OFFLINE=true`. As in round 3, the full tools suite uses the following harness to build the ontology runner outside protected documentation paths. No tests are disabled:

```sh
PYTHONDONTWRITEBYTECODE=1 CARGO_NET_OFFLINE=true \
CARGO_TARGET_DIR="$PWD/target/round4-ontology" python3 - <<'PY'
import os
import pathlib
import sys
import unittest
suite = unittest.defaultTestLoader.discover('tools/tests')
sys.modules['test_ontology_runner_io_error'].RUNNER_BIN = (
    pathlib.Path(os.environ['CARGO_TARGET_DIR']) / 'debug/ontology-case-runner'
)
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
PY
```

Full-suite success is not established in this sandbox. The six tools-suite errors, Rust `local_s3_wire_put_head_get_list_and_precondition` failure, and two CI-suite errors reproduce round 3's localhost socket restriction (`Operation not permitted`). Skips cover five private-archive prerequisites and one obsolete-botocore compatibility case; the ignored Rust case regenerates fixtures.

The two CI assertion failures reproduce the existing dependency-zone findings in `packages/ontology/Cargo.toml:15`, `packages/ontology/tests/common/mod.rs:350`, and `packages/ontology/tests/fixture_origin/main.rs:126`. Those files, the checker, its tests, and its rules are byte-identical to HEAD ([baseline-verification.log](baseline-verification.log)). These failures are outside the pin-guard change; successful full-suite evidence still requires a runner with localhost sockets available and resolution of the existing dependency-zone findings.
