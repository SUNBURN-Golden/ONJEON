# Release readiness evidence scaffold

`check.py` implements the evidence-coverage portion of T-OP-08. It reads the
implementation task column for all P01–P20 in 09 and every item in
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
Missing or malformed `tasks_state.json` produces an input error (exit 2).
Use `--tasks-state PATH` to read a different ledger. Tests run in the existing CI
`tools/tests` discovery step; CI does not require the unfinished product to pass
the live readiness gate.

## Product purpose progress

Run `python3 -I tools/release_readiness/progress.py`. CI appends the Markdown
report to its job summary in the advisory Product purpose progress step.
Open rows return exit 0. Input errors return exit 2 with a diagnostic, and CI
continues to the test steps.

The report derives linked tasks for P01–P20 from 09 and uses all
`tasks.json` task IDs for the overall denominator, including developer tools.
**Merged tasks** counts recorded merge SHAs from the same task ledger the
checker uses. This includes historical merges awaiting state or evidence review.
Both tools can run from a shallow checkout.

- **Tasks with evidence files** counts linked tasks that have at least one
  nonempty regular file under `evidence/<task-id>/`. This is visible before
  T-OP-08 reviews and references the artifacts in the shared manifest.
- **Row evidence files present** counts present, valid completion artifacts
  out of the row's registered evidence references in `readiness.json`.
  `0/0` means the row has no registered references.
- **Closed** uses the same evidence checks as the judge. Every linked task needs
  a qualifying ledger record, and the row needs release artifacts and successful
  acceptance execution logs. T-OP-08 determines release readiness.

## Task evidence ownership

Every task declares its own evidence path in `tasks.json` permissions, outputs
and conflict locks. Product tasks write their artifacts and acceptance logs to
`docs/release-readiness/evidence/<task-id>/`. T-OP-08 writes its audit reports and
acceptance logs to `docs/release-readiness/evidence/T-OP-08/`. Its aggregate
release-readiness grant lets it review the evidence and maintain the shared
`docs/release-readiness/evidence/readiness.json`. References in the manifest
are relative to the evidence directory, e.g.
`T-DT-04/denominator-report.md` and `T-DT-04/acceptance.log`. Evidence may be
referenced by multiple purpose rows/features without copying it.

Developer-tool tasks T-OP-00 and T-OP-09 write verification records under
`tools/evidence/<task-id>/` for the operational part of the final audit.
Path grants do not waive data, privacy, publication or release decision gates.
Python CI discovery runs `test_evidence_paths.py` against every registered task
using the daemon's R-01 scope predicate.

## Version 1 task ledger

The integration maintainer updates [docs/blueprint/progress/tasks_state.json](../../docs/blueprint/progress/tasks_state.json)
after verifying the task's merge on the integration branch and reviewing its
observed state and evidence reference. `tasks.json` supplies task IDs and
acceptance requirements. This example shows the ledger format with synthetic values.

```json
{
  "version": 1,
  "tasks": {
    "T-DT-04": {
      "state": "done",
      "merge_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "evidence_path": "T-DT-04/denominator-report.md"
    }
  }
}
```

Key each entry by a registered task ID. The three fields are required and accept
`null` for facts still unverified. A linked task qualifies when its observed
state is `merged`, `audit_queued` or `done`, its `merge_sha` is a full lowercase
Git SHA, and `evidence_path` resolves to a nonempty regular file inside the
evidence directory. The state set matches `daemon_rules.post_merge_states`.
An absent task entry, a nonqualifying state (including `merged_invalid_approval`),
an absent SHA or unusable evidence leaves affected rows and features open.
Duplicate keys, unknown task IDs and malformed records are input errors.

The initial ledger preserves 20 Git-verified merge SHAs from the advisory report.
Their approved states and evidence references are `null` pending review.
[Migration and verification](../../docs/blueprint/audits/2026-11-24_task_state_ledger.md).

## Version 1 evidence manifest

The evidence directory contains `readiness.json` for reviewed row and feature
completion evidence. An empty manifest is shown below. Existing version 1
manifests may still contain `task_states`. The reader validates that legacy field
for compatibility and uses the ledger as the sole source of task state.

```json
{"version": 1, "rows": {}, "features": {}}
```

`rows` is keyed by P01–P20; `features` is keyed by the feature registry IDs.
Missing entries stay open. An individual record has this shape (illustration
only; these files and outcomes are not supplied by the scaffold):

```json
{
  "environment": "release",
  "evidence": ["T-DT-04/denominator-report.md", "T-WB-01/screens.png"],
  "acceptance_tests": [
    {"name": "P01 actual-data acceptance", "log": "T-DT-04/acceptance.log", "exit_code": 0}
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

The checker verifies state strings, SHA format, coverage metadata and local
artifact presence. The integration maintainer verifies the SHA against Git and
the approval record. T-OP-08 reviews evidence provenance, freshness, actual-data
coverage and screen semantics. Positive tests use synthetic temporary files to
verify checker mechanics. Keep regression logs under `tools/evidence/` and use
reviewed actual-data, actual-screen and release artifacts for completion evidence.
