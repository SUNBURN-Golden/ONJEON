# Audit 6 runtime duplicate keys: proposed fix

The node's allowed paths exclude `packages/twin-runtime/**`. The runtime integration
is **prepared and verified in a disposable crate, but not applied to the runtime**.
A scope-extension request is pending. The execution-path finding remains open until
[proposed-runtime.patch](proposed-runtime.patch) is applied and checked in the worktree.
No `DECISION_REQUIRED.md` is created: this is an editing-scope constraint, not an
irreversible, money, legal, secrets or production decision.

The allowed rules-engine change exposes `strict_json::from_slice`. The proposed
runtime patch calls it before extracting `inputs_from_outside_dsl` and adds four
regressions from [runtime_tests.rs](runtime_tests.rs):

- Direct artifact loading rejects nested money duplicates, identical values,
  escaped keys, an unselected branch, repeated declaration fields and nested duration
  duplicates, in both DSL versions.
- Request execution rejects the same artifacts after a successful link and a clean
  release-integrity check, with `engine_calls == 0`, no filled inputs or result.
- The real `case-runner` process returns `load_error`, zero engine calls and no engine
  result for every duplicate artifact; a valid job still pays 1 KRW.
- Unique artifacts preserve their declarations, source, content hash and evaluation;
  trailing data and invalid UTF-8 still fail.

Run from the repository root:

```sh
python3 tools/evidence/audit6-engine-loader-tightening/fix-round1/verify_proposed_runtime.py
```

The script copies the runtime to a disposable crate in this worktree's `target/`,
resolves its own lockfile offline, then tests with `--locked --offline`. It checks
that the existing loader fails exactly three regressions (including the reviewer's
999999999-to-1 KRW example) and that the proposed patch passes all four. It never
edits the runtime source. The temporary crate and CLI artifacts are removed.

Evidence: [before-runtime.log](before-runtime.log),
[proposed-runtime.log](proposed-runtime.log), [verification.log](verification.log).
These are local proposal checks, not evidence that the current runtime is fixed.
