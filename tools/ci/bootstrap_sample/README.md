# bootstrap-sample-build (T-CT-07)

Follow-up integration test for T-CT-06's static `check_bootstrap.py`; the static checker is not a substitute for a real Cargo build.

## Commands

```sh
python3 -I tools/ci/bootstrap_sample/verify.py
bash tools/ci/bootstrap_sample/run.sh --task T-TW-01
python3 -I tools/ci/bootstrap_sample/prune.py --selftest
python3 -I -m unittest discover -s tools/ci/bootstrap_sample -p 'test_*.py' -v
python3 -I tools/ci/check_bootstrap.py
python3 -I tools/ci/check_leak.py
python3 -I tools/ci/check_skeleton.py
python3 -I -m unittest discover -s tools/ci/tests -v
```

`run.sh` supports `--repo DIR`, `--ref REF` and `--keep-tmp`. The default repository is the enclosing worktree, not the common Git directory. The default ref is `origin/main`, then `main`, then `HEAD`; no fetch or GitHub operation occurs. It resolves the ref once and reads tasks.json from that exact commit, never from dirty local files. All generated clones and reports live within this directory. Automatically created clones are cleaned on exit unless explicitly retained.

Each run creates a distinct report under `reports/`, including the target SHA, task graph and runner SHA-256 hashes, Rust/Cargo versions, keep set, phase outputs and verdict. Exit codes: 0 both phases passed; 1 setup/isolation/build/test failed; 2 invalid invocation or ref. Dependency caches may be warm, but each clone has its own fresh Cargo target directory.

## Isolation and verdict

- Keep the sample task's declared-dependency closure: its transitive `prereq_tasks` plus, transitively, the landed producers of the artifacts those tasks declare in `consumes`. A consumed `crate:` means the crate as it exists at the target ref, so every landed task that produced a path inside the crate's workspace member directory counts as one of its producers; a consumed `path:` is produced by any task with an overlapping produced glob. Producer candidates are restricted to merges actually landed on the target ref. For T-TW-01 this yields {T-CT-01, T-CT-02, T-CT-03, T-CT-04, T-CT-06, T-KN-01, T-TW-01, T-TW-02}: `crate:onjeon-contracts` reaches every landed producer under `packages/schemas` and `crate:onjeon-rules-engine` reaches T-TW-02 under `packages/rules-engine`.
- Phase A clones the target commit, peels first-parent task merges outside that set newest-first, repairs workspace membership, then runs `cargo build -p onjeon-twin-runtime` and `cargo test -p onjeon-twin-runtime`.
- Phase B uses a separate fresh clone, drops one landed task's outputs from outside the keep set, then runs the same commands. A passing B does not compensate for a failing A.
- A peel conflict or a re-added deleted file is fatal. Residual non-prerequisite lines must never produce a successful bootstrap verdict. Isolation failure prevents Cargo execution in that phase.
- Unknown tasks, missing prerequisites, cycles and ambiguous/invalid produced crate names fail. Missing option values and unsafe task IDs fail before report-path construction.
- When phase A fails, `run.sh` runs `prune.py diagnose`: it restores peeled merges inside the sample crate's Cargo dependency closure one trial build at a time and names the minimal set the keep set actually needs — the undeclared dependencies. Diagnosis changes nothing about the verdict; it turns an opaque compile error into the exact tasks.json edges (or code) that must be fixed upstream. Phase B failing needs no search: the single dropped task is itself the undeclared dependency.

The current isolation mechanism depends on first-parent PR merge attribution (`onjeon-T-XX-NN` in the subject). Untagged changes count as base. It does not establish provenance for squash/rebase histories or arbitrary untagged task outputs. The keep set is a produces/consumes reconstruction at merge granularity, not a proof that all tasks bootstrap, and a consumed crate is reconstructed as every landed merge that wrote inside its directory — merge granularity can keep more than a single consume strictly needs. Shared-file conflicts require explicit resolution rather than trusting a green build of a contaminated tree.

`verify.py` runs the commands sequentially, records every exit code in `reports/verification.log`, continues after a failing command to collect all evidence, and returns nonzero if any command fails. Do not run repository-wide scanners concurrently with temporary fixture creation inside this directory.

Latest fix-round verification (`reports/verification.log`): 18 bootstrap regression tests PASS; prune selftest PASS; shell syntax PASS; bootstrap static check PASS with 7 advisory paths; leak static check PASS; skeleton static check PASS (no live server probed). Real sample `run.sh --task T-TW-01`: PASS (phase A peels 9 non-dependency merges and builds/tests cleanly; phase B drops T-DT-01). Overall `verify.py` exit is still nonzero because of two pre-existing environment failures outside this task's allowed paths: `check_deps.py` reports 3 zone findings (`packages/ontology`, zone knowledge, depends on and imports `onjeon-rules-engine`, zone twin) and `tools/ci/tests` has the matching 2 unittest failures. The existing skeleton runtime-template tests exercise a local stub, not a deployed application.

## Regression coverage

`test_bootstrap_sample.py` is fixture_only. It exercises graph validation, fail-closed peeling, argument handling, `--except` exemption, dependency-closure and suspect computation, consumes-driven keep-set expansion (crate member-dir, path-glob and transitive producer edges), automatic diagnosis of an undeclared dependency in a real Cargo fixture, successful real Cargo compilation/testing in isolated fixture clones, pinned committed task metadata despite a dirty worktree, Cargo failure propagation, report creation and cleanup. Fixture Git history is confined to temporary repositories; no project commit is created.

## Current evidence and PR handoff

- Task: T-CT-07. Author role: implementation agent; execution path: CLI in this worktree. No independent reviewer participated in this execution. Raw model identifiers, secrets and insurance source excerpts are not recorded.
- Target main SHA: `c9157294e068f779fc82a0666ffcb0f2f162de23` (the ref resolved at run time; earlier rounds targeted `cbdc0f8f8ec20f513d356d0c25193cbd38202ad5`). Runner hashes in the report identify uncommitted implementation bytes separately from the target commit; they are not a substitute for a committed review target.
- A·Q·L·I·M: A1/A2/A5; Q1/Q2/Q5/Q7; L6 and cross-layer contracts; I10/I11/I18; M1/M2 prerequisite infrastructure. This task changes no consumer UI, calculation semantics, schema, personal data or release policy.
- Requirements: R03 (version linkage), R16 (deterministic calculation), R17 (explainable calculation) supported indirectly by reproducible runtime tests; R23 (personal-data minimization) supported only by existing static leak guards, not runtime privacy validation. The task's design-review note “R03” is separate from product requirement R03.
- Design: existing implementation contract, not a new decision; ADR-0003/ADR-0011/ADR-0012 apply. Synthetic tests are not actual insurance-data validation or release approval.
- Preliminary real execution: `reports/bootstrap-sample-build_T-TW-01_cbdc0f8f8ec2.log` used the inherited permissive draft. Phase A attempted Cargo and failed with E0658 in ontology (`str_as_str`); Phase B passed runtime tests. The overall verdict was FAIL. Its WARN entries mean it is diagnostic evidence, not clean isolation evidence.
- Fix-round execution: see `reports/verification.log` and its uniquely suffixed target-SHA report. Workspace members are peeled by entry, independently of unrelated manifest settings; genuine setting conflicts remain fatal. A single lowercase follow-up suffix (such as T-OP-00b) maps to the parent task. Regression tests cover later members/settings, conflicting settings, follow-up peeling, invalid suffix boundaries, and consumes-driven keep-set expansion.
- Earlier finding, now explained by declared edges: on target `cbdc0f8f8ec2…` a `prereq_tasks`-only keep set ({T-CT-01, T-KN-01}) could not compile — `packages/ontology/src/check.rs` calls `ORIGIN_FIXTURE.as_str()`, which requires the `AssertionOrigin` API merge T-CT-02 regenerated into `packages/schemas`, and `packages/twin-runtime/src/harness.rs` reads `EvaluationResult.contract_effect`, added under `packages/rules-engine/src/**` by T-TW-02. Neither task sits behind a `prereq_tasks` edge, but both sit behind declared `consumes` edges: T-KN-01 consumes `crate:onjeon-contracts` (member dir `packages/schemas`, which T-CT-02 wrote into) and T-TW-01 consumes `crate:onjeon-rules-engine` (member dir `packages/rules-engine`, which T-TW-02 wrote into). The keep set therefore follows `consumes` to landed producers. A `prereq_tasks`-only reading of tasks.json still cannot build this sample; teams wanting that stricter reading should add the missing prerequisite edges upstream — `docs/blueprint/proposals/설계검토_결과/tasks.json` is outside this task's allowed paths.
- Independent cross-family review pinned to the final implementation SHA remains the supervisor's responsibility after committing. Self-tests and this author's inspection are not independent review. No review result or final implementation SHA is fabricated here.
- Only `tools/ci/bootstrap_sample/**` is changed. Product-level completion evidence in `09_제품목적_대응표` is not claimed or edited.

No blocker remains for this task: the keep set is derived entirely from declared tasks.json edges (`prereq_tasks`, `produces`, `consumes`) restricted to merges landed on the target ref, so the PASS rests on declared dependencies only — nothing outside `tools/ci/bootstrap_sample/**` was patched to obtain it.
