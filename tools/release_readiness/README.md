# Release readiness evidence scaffold

`check.py` implements the evidence-coverage portion of T-OP-08. It reads the
implementation task column for all P01–P19 in 09 and every item in
`tasks.json.feature_registry`. The manifest cannot reduce either denominator.
Both existing task commands check both sets; omitting `--purpose` selects the
canonical 09 document relative to the script, independent of the working directory.

```sh
python3 -I tools/release_readiness/check.py --registry docs/blueprint/proposals/설계검토_결과/tasks.json --evidence docs/release-readiness/evidence/
python3 -I tools/release_readiness/check.py --purpose docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md --registry docs/blueprint/proposals/설계검토_결과/tasks.json --evidence docs/release-readiness/evidence/ --json
python3 -I -m unittest discover -s tools/tests -p test_release_readiness.py -v
```

Text output identifies each item and its incomplete reasons and prints
`purpose-rows-all-closed` and `release-readiness-rejects-incomplete` counts.
`--json` reports the same results in `rows`, `features`, `rows_counts` and
`features_counts`. Exit codes: **0** all evidence coverage checks pass,
**1** incomplete, **2** invalid/unreadable contract or manifest. A missing
evidence directory or missing manifest reports every item open (exit 1).
Malformed input never produces passing counts. Tests run in the existing CI
`tools/tests` discovery step; CI does not require the unfinished product to pass
the live readiness gate.

## Product purpose progress

Run `python3 -I tools/release_readiness/progress.py`. CI appends the Markdown
report to its job summary in the advisory Product purpose progress step.
Open rows return exit 0. Input errors return exit 2 with a diagnostic, and CI
continues to the test steps.

The report derives linked tasks for P01–P19 from 09 and uses all
`tasks.json` task IDs for the overall denominator, including developer tools.
`merged_tasks.json` maps each observed task merge to its full Git commit SHA.
Update that file after verifying a task merge in the integration branch's
history. The report reads this snapshot directly and can run from a shallow
checkout. [Initial snapshot and verification](../../docs/blueprint/audits/2026-11-19_purpose_progress_ledger.md).

- **Tasks with evidence files** counts linked tasks that have at least one
  nonempty regular file under `evidence/<task-id>/`. This is visible before
  T-OP-08 reviews and references the artifacts in the shared manifest.
- **Row evidence files present** counts present, valid completion artifacts
  out of the row's registered evidence references in `readiness.json`.
  `0/0` means the row has no registered references.
- **Closed** requires every linked task in the merge inventory and a passing
  row under the evidence coverage rules below, including observed post-merge
  states and successful acceptance execution logs. T-OP-08 determines release
  readiness.

## Task evidence ownership

Every product task except the developer-tool tasks T-OP-00/T-OP-09 can write
its own `docs/release-readiness/evidence/<task-id>/**` artifacts and acceptance
logs. These paths are explicit in `tasks.json` permissions, outputs and conflict
locks. T-OP-08 retains its existing release-readiness directory grant and
aggregates reviewed artifacts into the shared `evidence/readiness.json`; other
tasks cannot edit that manifest or one another's evidence. References in the
manifest are relative to the evidence directory, e.g.
`T-DT-04/denominator-report.md` and `T-DT-04/acceptance.log`. Evidence may be
referenced by multiple purpose rows/features without copying it.

Path grants do not waive data, privacy, publication or release decision gates.
Developer-tool regressions remain outside product completion evidence. The
existing Python CI discovery runs `test_evidence_paths.py` against every live
product task using the daemon's actual R-01 scope predicate.

## Version 1 input

The evidence directory contains `readiness.json`, an explicit snapshot maintained
from observed task states and reviewed completion evidence. `tasks.json` remains
the task contract: its prose `evidence` fields and test registrations are never
treated as observed results. An empty manifest is:

```json
{"version": 1, "task_states": {}, "rows": {}, "features": {}}
```

Each key in `task_states` is a registered task ID with its observed state string.
All implementation tasks for an item must be `merged`, `audit_queued` or `done`,
matching `daemon_rules.post_merge_states` (guarded by a regression test). Missing,
unknown or pre-merge states, `cancelled`, and `merged_invalid_approval` leave
affected items open. Task definitions do not supply execution states.

`rows` is keyed by P01–P19; `features` is keyed by the feature registry IDs.
Missing entries stay open. An individual record has this shape (illustration
only; these files and outcomes are not supplied by the scaffold):

```json
{
  "environment": "release",
  "evidence": ["P01/denominator-report.md", "P01/screens.png"],
  "acceptance_tests": [
    {"name": "P01 actual-data acceptance", "log": "P01/acceptance.log", "exit_code": 0}
  ]
}
```

An item needs nonempty completion artifacts, nonempty acceptance execution logs,
and integer exit code 0 for every registered execution. For features, every name
in the contract's `acceptance_tests` must have a matching execution entry. Purpose
rows require at least one named acceptance execution; semantic coverage of the
row's full completion criteria remains a review responsibility. Duplicate test
names, fixture/test environments, missing or empty files, directories, absolute
paths, `..` and symlinks escaping the evidence directory fail closed. Artifact
paths are relative to that directory. JSON keys must be unique; unknown IDs and
record fields are errors. Logs are read as artifacts and never executed.

## Exclusions and limits

No current row or feature has an approved **whole-item** exclusion. Version 1
rejects every exclusion request (`excluded` other than false or a nonempty
`scope_decision`), including requests embedded in the feature registry. Its
`excluded` count is therefore zero. ADR-0018's narrower denominator, D-18's
publication gate, and P18's deferred automatic comparison do not remove their
rows. Supporting future whole-item exclusions requires a reviewed canonical
scope change and a checker update that verifies that authority; a manifest
cannot grant it.

This tool verifies supplied state strings, coverage metadata and local artifact
presence. It cannot authenticate their provenance, establish freshness, inspect
screen semantics, or prove that content came from actual data. `environment:
release` is a declaration subject to review, not an attestation. Positive tests
use synthetic temporary files solely to verify checker mechanics. Do not enter
those tests, daemon regression logs or this scaffold's verification logs as
product completion evidence. The scaffold neither completes T-OP-08's five-axis
audit nor approves deployment, data access, participant studies or release.
