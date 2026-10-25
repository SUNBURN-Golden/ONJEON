Round 5 verification for `audit1-workflows-pin-actions-by-sha`.

The pin guard now tracks the block scalar mapping key's column instead of the sequence dash's column. A sibling `uses:` after a multiline step name is therefore checked, while action-like text inside the name remains ignored.

Regression coverage includes literal and folded names (`|` and `>-` included), chomping and indentation indicators, quoted keys, and different spacing before the key. Tagged sibling actions fail; pinned and local sibling actions pass. The repository guard also rejects both reviewer examples in temporary `.yml` and `.yaml` workflows and composite actions. The new tests with the original parser produced 68 failing subcases ([regressions-before.log](regressions-before.log)); the fixed parser passes all 24 workflow-focused tests ([workflow-focused.log](workflow-focused.log)). Direct checks of both reviewer examples return the tagged ref ([guard-examples.log](guard-examples.log)).

Both workflows are byte-identical to HEAD. All six refs already exactly match the operator-supplied SHAs and comments: four checkouts and two artifact uploads ([baseline-verification.log](baseline-verification.log)). No protected file was edited, no upstream lookup was made, and no commit or push was made. Parent HEAD and source/log hashes are recorded in [manifest.json](manifest.json).

| Command | Exit | Result / evidence |
|---|---:|---|
| `python3 -m unittest discover -s tools/tests -p 'test_workflow*.py' -v` | 0 | 24 passed; [workflow-focused.log](workflow-focused.log) |
| Full `tools/tests` discovery with the harness below | 1 | 485 run: 473 passed, 6 errors, 6 skipped; [python-tools.log](python-tools.log) |
| `cargo test --offline --locked --all --no-fail-fast` | 101 | 386 passed, 1 failed, 1 ignored; embedded Python suites: 39 and 129 passed; [rust-tests.log](rust-tests.log) |
| `python3 -I -m unittest discover -s tools/ci/tests -v` | 1 | 20 run: 16 passed, 2 failures, 2 errors; [python-ci.log](python-ci.log) |
| `cargo fmt --all -- --check` | 0 | [rust-format.log](rust-format.log) |
| `cargo clippy --offline --locked --all-targets -- -D warnings` | 0 | [rust-clippy.log](rust-clippy.log) |
| `python3 tools/vocab_check.py` | 0 | [vocabulary.log](vocabulary.log) |
| `python3 tools/validation_check.py` | 0 | [validation.log](validation.log) |
| `python3 tools/validation_check.py --selftest` | 0 | 38 mutations caught; [validation-selftest.log](validation-selftest.log) |
| `cargo build --offline --locked --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir target/round5-ontology` | 0 | [ontology-build.log](ontology-build.log) |
| `python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py target/round5-ontology/debug/ontology-case-runner` | 0 | [ontology.log](ontology.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 0 | [design-specs.log](design-specs.log) |

All Python commands use `PYTHONDONTWRITEBYTECODE=1`; Cargo and its subprocesses use `CARGO_NET_OFFLINE=true`. The full tools suite uses this harness to build the existing ontology runner outside protected documentation paths. No tests are disabled:

```sh
PYTHONDONTWRITEBYTECODE=1 CARGO_NET_OFFLINE=true \
CARGO_TARGET_DIR="$PWD/target/round5-ontology" python3 - <<'PY'
import os
import pathlib
import sys
import unittest
suite = unittest.defaultTestLoader.discover('tools/tests')
sys.modules['test_ontology_runner_io_error'].RUNNER_BIN = (
    pathlib.Path(os.environ['CARGO_TARGET_DIR']) / 'debug/ontology-case-runner'
)
with open('tools/tests/evidence/workflow_pins_round5/python-tools.log', 'w') as log:
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
PY
```

Full-suite success is not established in this sandbox. The six tools-suite errors, Rust `local_s3_wire_put_head_get_list_and_precondition` failure, and two CI-suite errors reproduce round 4's localhost socket restriction (`Operation not permitted`). Skips cover five private-archive prerequisites and one obsolete-botocore compatibility case; the ignored Rust case regenerates fixtures.

The two CI assertion failures reproduce the existing dependency-zone findings in `packages/ontology/Cargo.toml:15`, `packages/ontology/tests/common/mod.rs:350`, and `packages/ontology/tests/fixture_origin/main.rs:126`. Those files, the checker, its tests, and its rules are byte-identical to HEAD ([baseline-verification.log](baseline-verification.log)). These failures are outside the pin-guard change; successful full-suite evidence still requires a runner with localhost sockets available and resolution of the existing dependency-zone findings.
