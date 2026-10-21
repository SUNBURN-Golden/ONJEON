Round 3 verification for `audit1-workflows-pin-actions-by-sha`.

Parent HEAD: `46428c6` (round 2). Source and complete-log SHA256 hashes are recorded in [manifest.json](manifest.json).

The blocking multiline bypass is fixed in `tools/tests/test_workflow_pins.py`. The guard inspects action headers before skipping block-scalar contents, so `uses: >-` and `uses: |` fail. It also recognizes empty `uses:` entries, rejecting values supplied on subsequent lines. These forms are explicitly unsupported even when their contents contain a pinned or local action; supported inline SHA references and local actions continue to pass. Comments, quoted script strings, and script block contents remain ignored.

Regression coverage includes literal/folded scalars, chomping and indentation indicators, quoted keys, empty/comment-only headers, next-line values, flow mappings, and action detection after a rejected scalar. Repository-guard tests inject these forms into temporary `.yml` and `.yaml` workflows and composite actions, require failure, then replace them with an inline full SHA and require success. With the new regressions and the original parser, 122 subcases fail: [regressions-before.log](regressions-before.log). With the fix, all 21 workflow-focused tests pass: [workflow-focused.log](workflow-focused.log). Direct in-memory checks of both reviewer examples also reject them: [guard-examples.log](guard-examples.log).

Both workflows remain byte-identical to HEAD. All six action lines match the operator-supplied SHAs and comments (four checkouts, two artifact uploads): [baseline-verification.log](baseline-verification.log). No workflow file was edited, no GitHub or network lookup was performed, and no commit or push was made.

Verification commands and actual results:

| Command | Exit | Result / complete evidence |
|---|---:|---|
| `python3 -m unittest discover -s tools/tests -p 'test_workflow*.py' -v` | 0 | 21 passed; [workflow-focused.log](workflow-focused.log) |
| Full `tools/tests` discovery, using the harness below | 1 | 482 run: 470 passed, 6 errors, 6 skipped; [python-tools.log](python-tools.log) |
| `CARGO_NET_OFFLINE=true cargo test --offline --locked --all --no-fail-fast` | 101 | All targets attempted: 386 passed, 1 failed, 1 ignored; embedded Python suites: 39/39 and 129/129 passed; [rust-tests.log](rust-tests.log) |
| `python3 -I -m unittest discover -s tools/ci/tests -v` | 1 | 20 run: 16 passed, 2 failures, 2 errors; [python-ci.log](python-ci.log) |
| `cargo fmt --all -- --check` | 0 | [rust-format.log](rust-format.log), empty because formatting matches |
| `cargo clippy --offline --locked --all-targets -- -D warnings` | 0 | [rust-clippy.log](rust-clippy.log) |
| `python3 tools/vocab_check.py` | 0 | [vocabulary.log](vocabulary.log) |
| `python3 tools/validation_check.py` | 0 | [validation.log](validation.log) |
| `python3 tools/validation_check.py --selftest` | 0 | 38 mutations caught; [validation-selftest.log](validation-selftest.log) |
| `python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py target/round3-ontology/debug/ontology-case-runner` | 0 | [ontology.log](ontology.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 0 | 44 mechanical and 72 existence checks passed; [design-specs.log](design-specs.log) |

All Python commands use `PYTHONDONTWRITEBYTECODE=1` to avoid cache writes under protected documentation paths. Cargo uses offline mode, including subprocesses. The full tools suite is run with this harness so the existing ontology runner test builds and executes under the allowed `target/` directory instead of writing under protected `docs/blueprint/proposals/`. No test is disabled or modified to suppress a failure:

```sh
PYTHONDONTWRITEBYTECODE=1 CARGO_NET_OFFLINE=true \
CARGO_TARGET_DIR="$PWD/target/round3-ontology" python3 - <<'PY'
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

Full-suite success is **not established** in this sandbox. The six tools-suite errors, the Rust `local_s3_wire_put_head_get_list_and_precondition` failure, and two CI-suite errors reproduce round 2's localhost socket restriction (`Operation not permitted`). The six tools-suite skips are five private-archive prerequisites and one obsolete-botocore compatibility case; the ignored Rust case is the fixture regeneration helper.

The two CI-suite assertion failures reproduce round 2's three existing dependency-zone findings at `packages/ontology/Cargo.toml:15`, `packages/ontology/tests/common/mod.rs:350`, and `packages/ontology/tests/fixture_origin/main.rs:126`. These source files, the dependency checker, its tests, and its rules are byte-identical to HEAD (see baseline verification). They are outside this action-pinning fix. Successful CI evidence still requires the supervisor's runner with localhost sockets available; this report claims only the local results above.
