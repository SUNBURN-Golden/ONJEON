# Audit 6: evidence write paths for every product task

Finding: 09 §0 required completion artifacts under
`docs/release-readiness/evidence/`, while only T-OP-08 could write there.
The daemon's actual R-01 predicate accepted artifact/log paths for **1/62**
product tasks before this change and **62/62** afterward
([contract comparison](contract-change.log)).

The 61 preceding product tasks now declare
`docs/release-readiness/evidence/<task-id>/**` in `allowed_paths`, `produces`
and `conflict_paths`. T-OP-08 retains its existing aggregate permissions and
gets a release-readiness conflict lock. It reviews task artifacts and maintains
the shared `readiness.json`. Other tasks cannot write that manifest or another
task's evidence. The two developer-tool tasks T-OP-00/T-OP-09 are unchanged.
Decision gates and acceptance criteria are unchanged for all 64 tasks.

09 §0, tasks.json's field definition, the corresponding generated tables in
03, and the readiness tool README describe the same artifact/manifest workflow.
No evidence directory or live readiness manifest is modified by this node.

| Verification (run from repository root) | Result | Evidence |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p test_evidence_paths.py -v` | 5 passed | [log](evidence-paths.log) |
| `python3 -m unittest discover -s tools/tests -p test_audit5_confirm_agent_made_decisions.py -v` | 22 passed | [log](decision-regressions.log) |
| `python3 -I tools/ci/check_product_purpose.py` | Passed | [log](product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 46/46 mechanical, 72/72 presence checks | [log](spec-check.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,684 run, passed with 6 environment-dependent skips | [log](python-tests.log) |
| `cargo test --all --locked --offline` | 532 passed, 1 ignored | [log](cargo-tests.log) |
| `cargo test --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml` | 4 passed | [log](ontology-tests.log) |
| `python3 -I tools/release_readiness/check.py --registry docs/blueprint/proposals/설계검토_결과/tasks.json --evidence docs/release-readiness/evidence/ --json` | Expected exit 1: 19 purpose rows and 64 features open | [log](release-readiness.log) |

The new tests exercise every product task through the daemon's actual scope
predicate, removal of each new grant, forbidden-first enforcement, sibling and
manifest isolation, conflict locks, and table consistency. A temporary synthetic
manifest references task-owned artifacts across the live P01–P19 and 64-feature
denominators; the existing readiness checker accepts it and reopens P01 when
its artifact is removed. All positive artifacts are temporary synthetic inputs.

The first full Python run found one stale expectation that T-UX-01 had exactly
one allowed path ([initial run](python-tests-before-expectation-update.log)).
That regression now checks both its existing UX preregistration grant and its
new evidence grant, while retaining its preregistration and decision assertions.
The final full-suite result is recorded separately above.

The Python skips concern two unavailable archived-original inputs, three local
archive/pdftotext reproduction inputs, and the old-botocore compatibility branch
on the installed newer version. The ignored Rust test regenerates a declared
A-box fixture and is excluded by the existing suite.

This is local evidence that the write-path finding is resolved. These logs do
not establish actual data acquisition, product/contract twin correctness,
consumer screen acceptance, participant-study results, P01–P19 completion,
T-OP-08 completion, or first-release readiness. No commit, push, GitHub call,
secret access or production access was performed.

## Fix round 1: merge with origin/main (7abea57), both intents kept

The merge conflicted only in `03_작업명세.md` §7: this branch had added
`path:docs/release-readiness/evidence/<task-id>/**` produces grants to every
row, while main added `no-composite-score` to T-AP-09's completion criteria
and required test IDs. Resolution keeps the evidence grants and applies
main's T-AP-09 change on top
([resolution delta](merge-main-round1/conflict-resolution.log)).
`tasks.json` and `09_제품목적_대응표.md` auto-merged; both intents are verified
present in all three files, including main's P06→T-KN-04 owner link, the
T-AP-09 `no-composite-score` test command, and this branch's §0 evidence-path
bullet and per-task grants
([intent verification](merge-main-round1/merge-intents.log)).

Re-run on the merged tree (logs in `merge-main-round1/`):

| Verification | Result | Evidence |
|---|---|---|
| `python3 -I tools/ci/check_product_purpose.py` (+ `--selftest`) | Passed; 5 selftest violations caught | [log](merge-main-round1/product-purpose.log) |
| `python3 -I -m unittest discover -s tools/tests -p test_product_purpose.py -v` | 20 passed (incl. 03↔tasks.json agreement and P06/P17 owners) | [log](merge-main-round1/product-purpose-tests.log) |
| `python3 -I -m unittest discover -s tools/tests -p test_evidence_paths.py -v` | 5 passed | [log](merge-main-round1/evidence-paths.log) |
| `python3 -I -m unittest discover -s tools/tests -p test_audit5_confirm_agent_made_decisions.py -v` | 22 passed | [log](merge-main-round1/decision-regressions.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 46/46 mechanical, 72/72 presence | [log](merge-main-round1/spec-check.log) |
| `python3 -I -m unittest discover -s tools/tests -v` | 1,687 run, OK (72 environment skips) | [log](merge-main-round1/python-tests.log) |
| `cargo test --all --locked --offline` | 532 passed, 0 failed, 1 ignored | [log](merge-main-round1/cargo-tests.log) |
| ontology runner `cargo test --locked --offline` | 4 passed | [log](merge-main-round1/ontology-tests.log) |
| `tools/release_readiness/check.py --json` | Expected exit 1: 19 purpose rows, 64 features open | [log](merge-main-round1/release-readiness.log) |
| vocab/validation(+selftest)/blueprint status·counts/registry/leak(+selftest)/skeleton/bootstrap, `git diff --check` | All exit 0 | [log](merge-main-round1/checks.log) |

Honest limits of this round:

- `python3 -I -m unittest discover -s tools/ci/tests -v` reports 20 run,
  2 failures ([log](merge-main-round1/ci-tests.log)). Both are pre-existing
  `check_deps` findings on `packages/ontology`'s test-only dev-dependency on
  `onjeon-rules-engine` (no `dependency_exceptions` entry in
  `infra/ci/deps.json`). The failing inputs are byte-identical on both merge
  parents and untouched by this resolution, and `ci.yml` does not wire
  `tools/ci/tests` ([proof](merge-main-round1/ci-tests-preexisting.log)).
  The zone-rule fix belongs to the T-CT-06/T-KN-02 rule owners; this node
  does not change zone policy.
- The 72 Python skips are environment-dependent: 67 need boto3/botocore
  (not installed in this round's environment; the round-0 environment had
  them, hence 6 skips then), 3 need local archive/pdftotext inputs, 2 need
  `ONJEON_ARCHIVE_RAW`. Every executed test passed.
- `tools/ci/README.md` said check_bootstrap prints "7 today" advisory path
  notes including T-CT-05; the merge base already printed 6 without T-CT-05
  (verified with `--tasks` on the base tasks.json). Corrected to 6
  (T-OP-00, T-AP-03, T-AP-05, T-OP-05).

The merge is left staged for the supervisor to commit; this node performed
no commit, push or GitHub call.
