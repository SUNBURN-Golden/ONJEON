# tools/ci: zone, leak and skeleton checks (T-CT-06)

Static checkers and their rule file. Rules: `infra/ci/deps.json`. Skeleton flags: `packages/schemas/feature_flags.json`. Sources: 01_code_design section 2 (allowed dependencies, O15), 02_implementation_contract 7.1, Part 3 sections 52.3 and 58, invariants I10 and I11.

## Commands

```text
python3 -I tools/ci/check_deps.py              # zone dependencies, provider-SDK rule (manifests and imports)
python3 -I tools/ci/check_leak.py              # I10, I11, 52.3
python3 -I tools/ci/check_leak.py --selftest   # one planted violation per rule, each must fail for its own rule id
python3 -I tools/ci/check_skeleton.py          # flags off, no exposure in app code or config (static)
python3 -I tools/ci/check_skeleton.py --base-url http://HOST:PORT   # also probe inactive routes on a running server
python3 -I tools/ci/check_bootstrap.py         # bootstrap-clean-main (tasks.json only; builds nothing)
python3 -I tools/ci/check_product_purpose.py   # 09 P01..P19 task links and nine product-purpose test IDs on assigned tasks
python3 -I tools/blueprint_status.py          # §11 date/index matches every ADR/DEC path and content
python3 -I tools/blueprint_counts.py          # §11 engine test/doctest, real-clause, mutation and vocabulary counts
python3 -I -m unittest discover -s tools/tests -p test_product_purpose.py -v
python3 -I tools/ci/check_<name>.py --selftest # every checker has one
python3 -I -m unittest discover -s tools/ci/tests
```

Exit codes: 0 clean, 1 findings, 2 usage or unreadable input. Every finding has a rule id (`DEP-ZONE`, `LEAK-I11-LOG`, ...). A selftest case passes only when its planted violation yields the intended id, so a check cannot pass for the wrong reason.

## What each one proves, and does not

| Check | Proves | Does not prove |
|---|---|---|
| `check_deps` | Cargo, package.json, pubspec, pyproject and requirements manifests, and Rust/TS/Dart imports, stay inside the zone table; provider SDKs appear only under `services/ai-gateway`. Default deny: a `Cargo.toml`, `package.json` or `pubspec.yaml` in no zone fails (pyproject and requirements files are checked for provider SDKs only). The provider-SDK list is an explicit list, not exhaustive; extend `infra/ci/deps.json` when a new SDK appears | DB role grants, credential separation (personal has no R2 token), the `krw` arithmetic lint, "knowledge reads data stores only, not code". Python imports are checked for provider SDKs only. A dev-dependency exception (`dependency_exceptions`) lets that package import the target anywhere in the package, not only in test code |
| `check_leak` | Textual hits: ad/commission fields in sort/rank/recommend context; sensitivity labels in public serializers, analytics/crash code, agent modules, the AI gateway; log/print calls naming a label or private field; analytics event calls with literal fields outside the allowed list | Data flow. camelCase and PascalCase identifiers are matched through a snake_case form, but other renamings (aliases, abbreviations) are not. A sensitive value passed through an untyped variable is invisible. Multi-line log calls are matched on the first line only. The runtime leak tests of T-PS-04 are the other half |
| `check_skeleton` | Every skeleton flag defaults to false and names a gate; no config switches one on; app code does not reference a skeleton flag or route; with `--base-url`, inactive routes answer 404/501 | Without `--base-url` it says nothing about any server. No server or screen exists yet, so today this guards the file and the tree only |
| `check_bootstrap` | The task graph is self-consistent (spec_check G1, G2, G31): tests and criteria name only crates, task IDs and paths that the repo or a prerequisite provides | That anything builds. The real sample build is T-CT-07. Test-command paths outside a task's allowed_paths (7 today in tasks.json: T-OP-00, T-CT-05, T-AP-03, T-AP-05, T-OP-05) are printed as advisory; `--strict-paths` fails on them |
| `check_product_purpose` | All nine product-purpose test IDs from 09 §6 are in `required_test_ids` on every assigned task (§6 and P16), with `PURPOSE-OWNER` reporting the task and missing ID; every P01..P19 implementation task exists in tasks.json. Missing, duplicate or malformed rows fail closed | That registered tests execute or any product-purpose row has completion evidence |

## Rule file notes

- `leak.i11.sensitive_labels` must contain every non-public code of the `sensitivity` axis in `packages/schemas/vocabulary.json`; a new code there fails `LEAK-VOCAB-DRIFT` until it is added.
- `leak.analytics.allowed_fields` is empty: there is no analytics event schema yet, so any literal field key in an event call fails. The task that defines the event schema fills it.
- `allow` entries (`leak.i10.allow`, `leak.i11.allow`) need `rule`, `path`, `reason`; an entry without a reason fails `LEAK-RULES`. Prefer an allow entry with a reason over loosening a pattern.
- `dependency_exceptions` currently holds one: `onjeon-contracts` dev-depends on `onjeon-rules-engine` for the round-trip test (T-CT-01). An unused exception is reported as a warning.
- `api` may depend on `onjeon-personal-client` and `personal` on `onjeon-docproc-personal`. Those crate names are placeholders for the personal-client and personal-deployment crates (01 section 2); rename them in `deps.json` when the crates exist.
- `inactive_response.statuses` ([404, 501]) in the flags file is a choice of this task, not a documented decision: the task that registers the routes may narrow it.

## Skeleton non-exposure test template

`templates/test_skeleton_unexposed.py.tmpl` is copied into the api/web/mobile task that registers routes or screens. It fails (never skips) when the server URL or the UI route list is not supplied. It is exercised against a local stub server in `tests/test_ci_checkers.py`, green and red, but no real app route exists yet.

## CI wiring

`ci.yml` runs `tools/blueprint_counts.py` after the Rust tests. It compares the
generated §11 inventory with Cargo's registered tests for `onjeon-rules-engine`
(unit/integration tests and doctests separately), real-clause rule JSON files
(excluding case tables), `validation_check.mutations()` and canonical vocabulary
axes. Ignored tests count as registered; this check does not claim they passed.
After changing those sources, run `python3 -I tools/blueprint_counts.py --write`
and review the diff. Only the marked counts block changes; historical test and
R2 observations remain dated evidence. The existing Python discovery step runs
`test_blueprint_counts.py`, including stale numbers, source additions, malformed
listings, missing/duplicate/misplaced blocks, read-only checks and explicit writes.
[Audit 2 evidence](../../docs/blueprint/audits/2026-10-27_blueprint_11_counts.md).

R2 workflow credential scope is guarded by `tools/tests/test_workflow_secret_scope.py`,
discovered by the existing Python unit-test step. The endpoint, verifier credentials
and ledger credentials must appear only in the step-level `env` of the two archive
consumers in `sources.yml`. Mutations cover workflow/job scope, installer/action/other-job
exposure and missing, duplicate or incorrect bindings. This stdlib contract test expects
the current block-style step/env layout; it is not a general YAML parser. Existing
`test_workflow_pins.py` and `test_workflow_check.py` guard full action SHAs and `ci.yml`'s
read-only token permissions. [Audit 2 evidence](../../docs/blueprint/audits/2026-10-26_ci_secrets_step_scope.md).

`ci.yml` also runs `python3 tools/workflow_check.py` and the action-pin test file
immediately after checkout, before installing dependencies or building Rust.
`test_ci_workflow_security.py` executes that declared shell block in temporary
repository copies: the current workflows pass, while missing/write permissions
and a tag, branch or short SHA substituted for each CI action fail. These are
offline checks; they do not verify upstream tag-to-commit provenance or execute
GitHub Actions. [Audit 3 evidence](../../docs/blueprint/audits/2026-10-28_ci_permissions_and_pins.md).

The §11 decision-index guard runs through `tools/tests/test_blueprint_status.py`
in the existing Python unit-test CI step. On every ADR/DEC addition, edit,
removal or rename, review the affected §11 status/gate rows, then run
`python3 -I tools/blueprint_status.py --write`. This stamps §11 with the current
UTC date and regenerates only its full file index and content digest. Status
rows still need review; index freshness does not approve gates or prove a
milestone or a product-purpose row complete. No record change means an older
snapshot date remains valid. [Audit 1 evidence](../../docs/blueprint/audits/2026-10-26_blueprint_s11_refresh.md).

The product-purpose guard runs through `tools/tests/test_product_purpose.py`, discovered by the existing `python3 -m unittest discover -s tools/tests -v` CI step. It checks the live bundle and exercises missing IDs, missing assigned owners and dangling row tasks using temporary inputs. A test ID registered elsewhere cannot replace a required owner. The live UX matrix also checks that the test descriptions exist and that 03's IDs and completion criteria match tasks.json. The `spec_check.py` G12 list remains unchanged; this companion supplies the omitted checks without workflow changes. [Audit 3 evidence](../../docs/blueprint/audits/2026-10-29_tasks_purpose_test_ids.md).

Local verification and environment limits: [Audit 1 product-purpose evidence](evidence/audit1-product-purpose.md).

The other checker commands and `tools/ci/tests` are not wired here. `.github/workflows/**` is the implementer's; add those commands to `ci.yml`.
