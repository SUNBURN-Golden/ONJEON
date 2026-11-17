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
