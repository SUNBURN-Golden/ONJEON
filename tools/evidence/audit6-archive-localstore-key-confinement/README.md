# Audit 6: LocalStore key confinement and sample SHA-256

Base: `036644dcb4924edef10a5ce170620ac57b4e1c8a`, plus this node's changes.
Run date: 2026-11-15. Rust 1.98.1; boto3 1.43.100.

The base already contains canonical relative-key checks, resolved-path containment
and shared validation of exactly 64 ASCII hex characters in each sample row and
object-key construction. This change explicitly rejects non-string store keys
with `UnsafeStoreKey` and adds three regressions:

- Seven invalid key types across all four LocalStore operations leave storage empty.
- An external symlink targeting a sibling whose name starts with the root name
  cannot pass containment checks or change external bytes.
- A real temporary CSV contains a 64-character traversal digest whose former
  object-key layout resolves to an external sentinel. Fetch fails before any
  `Path.read_bytes` call, both normally and with the shared hash validator bypassed.
  The previous restored file, sentinel and empty archive remain unchanged.

The [audit record](../../../docs/blueprint/audits/2026-11-15_archive_localstore_key_confinement.md)
is linked from BLUEPRINT and the P02/P03 local evidence section in the product
purpose table. This is local archive-tool finding evidence; it does not close
P02/P03, actual collection, R2 reconciliation, twins, consumer UX or first release.
The tool assumes a trusted local workspace; hostile concurrent replacement of
filesystem paths is outside its existing confinement contract.

| Command | Result / evidence |
|---|---|
| `python3 -m unittest discover -s tools/tests -v` | 1,614 run, 1,608 passed, 6 existing skips, exit 0: [full Python log](python-tests.log) |
| `cargo test --all --locked --offline` | 532 passed, 1 existing ignored; embedded Python suites 39 and 129 passed, exit 0: [workspace log](rust-tests.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4 passed, exit 0: [runner log](runner-tests.log) |
| `python3 tools/evidence/audit6-archive-localstore-key-confinement/check_key_mutations.py` | All three removed key guards detected, exit 0: [key mutations](key-mutations.log) |
| `python3 tools/evidence/audit5-samples-sha256-format-check/check_hash_mutations.py` | Row-guard removal and length-only validation detected by every selected test, exit 0: [hash mutations](hash-mutations.log) |
| Validation, 40 validation self-test mutations, vocabulary, blueprint counts/status, product-purpose tests, spec check, whitespace | All passed, exit 0 per command: [static checks](static-checks.log) |

Mutation scripts alter functions only in memory. Expected unittest failure output
in those two logs demonstrates detection and is followed by `MUTATION REJECTED`.
Production sources on disk are unchanged by these experiments. The full Python
log includes all 15 LocalStore path tests and 8 sample metadata tests.

Five existing skips require local archived originals (three also require
`pdftotext`); one old-botocore refusal test does not apply to the installed
version supporting conditional PUT. All path and metadata tests ran without skips.

[Manifest](manifest.json) records command exit codes and source/evidence SHA-256
hashes. Tests use temporary files, synthetic bytes and local stubs. No GitHub,
credentials, remote archive requests, commits, pushes or deployments were used.
