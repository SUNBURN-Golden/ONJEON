# Audit 3 release-readiness scaffold — fix round 3

The required evidence directory now contains an actual [README](../../../../docs/release-readiness/evidence/README.md)
and empty version 1 [manifest](../../../../docs/release-readiness/evidence/readiness.json).
The round 1 patch has been applied. This round's explicit request to create
these two files resolves the earlier path-exception wait for this narrow addition.
The existing checker needed no implementation changes.

The new repository regression checks the real files' presence and the initial
empty manifest, then runs both prescribed CLI forms against that directory.
This catches the original omission: missing evidence also returns open counts,
so checking only those counts would not prove the scaffold exists.

| Verification | Result / evidence |
|---|---|
| Scaffold files, manifest and documentation link | Present and valid: [log](scaffold-presence.log) |
| Readiness regression suite | 17 passed: [log](readiness-tests.log) |
| Full Python suite | Passed, 1,313 run, 6 skipped (164.337s): [log](python-tests.log) |
| Rust workspace tests, `cargo test --all` | Passed: [log](cargo-tests.log) |
| Product-purpose registrations | Passed: [log](product-purpose.log) |
| Design bundle specification | 45/45 machine checks, 72/72 presence checks passed: [log](spec-check.log) |
| Prescribed default-purpose command | Expected exit 1: [log](live-readiness.log) |
| Prescribed explicit-purpose JSON command | Expected exit 1: [log](live-readiness-purpose.log) |

Commands are documented in the [checker contract](../../../release_readiness/README.md).
The full Python command is `python3 -m unittest discover -s tools/tests -v`.
Both live commands report **19 open purpose rows and 64 open features, with
zero closed and zero excluded**. The manifest contains no observed task states
or completion records. These verification logs are development evidence;
they neither close product rows nor complete T-OP-08 or approve release.

The six Python skips concern unavailable archived originals/reproduction inputs
and the old-botocore compatibility branch on the installed newer version.

All work was performed in this worktree. No commit, push or GitHub call was
made; the supervisor remains responsible for committing the new files.
