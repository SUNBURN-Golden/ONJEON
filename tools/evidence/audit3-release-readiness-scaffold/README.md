# Audit 3 release-readiness scaffold — fix round 1

Latest: [fix round 3](fix-round3/README.md) applies the evidence scaffold and
verifies its presence and initial counts. [Fix round 2](fix-round2/README.md)
addressed the checkpoint retry test timeout. Results below describe round 1 only.

The checker is implemented in `tools/release_readiness/check.py`; its input
contract and limits are in [README](../../release_readiness/README.md).
Regression tests are discovered by the existing Python CI step.

At round 1, the node's allowed paths omitted `docs/release-readiness/**`. Creation of the
required evidence directory awaited a requested path exception. The exact
[directory patch](evidence-scaffold.patch) was prepared and passed
`git apply --check`; it was not applied in round 1. The full finding remained
open then; round 3 applies that patch under the explicit follow-up request.

| Verification | Result / evidence |
|---|---|
| Readiness acceptance tests | 16 passed: [readiness-tests.log](readiness-tests.log) |
| Full Python project suite | Passed, with six environment-dependent skips: [python-tests.log](python-tests.log) |
| Cargo workspace tests | Passed: [cargo-tests.log](cargo-tests.log) |
| Cargo format and clippy | Passed: [format](cargo-format.log), [clippy](cargo-clippy.log) |
| Product-purpose registration, task/spec consistency | Passed: [product-purpose.log](product-purpose.log), [spec-check.log](spec-check.log) |
| Vocabulary, validation and tamper self-tests, blueprint counts | Passed: [vocabulary](vocabulary.log), [validation](validation.log), [self-test](validation-selftest.log), [counts](blueprint-counts.log) |
| Prescribed checker command without explicit purpose | Expected exit 1, 19 open purpose rows, 64 open features: [live-readiness.log](live-readiness.log) |
| Prescribed checker command with explicit purpose | Same expected result: [live-readiness-purpose.log](live-readiness-purpose.log) |
| Additional CI checker suite | 20 tests, two failures from three pre-existing ontology dependency findings: [ci-checker-tests.log](ci-checker-tests.log) |

The dependency checker, rules and all reported ontology source files match HEAD
byte for byte ([comparison and diagnostics](dependency-baseline.log)). This
change does not alter dependency policy or ontology implementation. The six
Python skips concern unavailable archived originals/reproduction inputs and an
old-botocore compatibility branch on the installed newer botocore.

The acceptance suite exercises all 19 rows individually by removing evidence
and execution logs and replacing each linked task's state. It also covers
feature evidence/log removal, missing named feature tests, multiple linked
tasks, all three post-merge states, invalid merge/cancelled states, absent
manifests/directories, empty artifacts, fixture declarations, failed executions,
malformed JSON and denominators, unknown IDs, duplicate JSON keys/test names,
unsupported exclusions (including partial-scope ADR-0018 and pending D-18),
and artifact paths outside the evidence directory. Positive cases use only
temporary synthetic artifacts. None of these regression logs are actual
product data, screen acceptance, participant-study or release evidence.

No commit, push, GitHub call, production access or secret access was performed.
