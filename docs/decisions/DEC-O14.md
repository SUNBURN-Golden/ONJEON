# Decision: Decision gate O14

**decided_by:** Delegated by 준태님 on 2026-10-15 14:44 KST; the rule was decided by the assistant (ONJEON) under that delegation. This is NOT a decision personally made by 준태님.

**time:** 2026-10-15 (delegation 14:44 KST)

**Delegation (verbatim):**

> "다들 종료하지말고, 제품화때까지 열심히 개발하도록해라. 내 결정이 필요한건 전부 너네가 알아서 하렴." — 준태님, 2026-10-15 14:44 KST (개발본부 그룹 채팅)

Delegation limits: cost, hardware, mainnet, secret keys, production deploys and payments are excluded from the delegation.

**This is a record only.** It performs and authorizes no real-world action: no R2 bucket lock is applied, no token or bucket is touched, no personal data goes to an external AI, nothing is spent, no mass collection is started, no production deploy is made and no secret is handled. Applying a lock is a separate execution step that needs 준태님's approval, and the rule "do not apply before approval" stays in force.

**Decision (O14, R2 bucket lock rule):** Take the conservative default: the tool's conditional writes (`If-None-Match: *`) + no delete command in the tool + a separate copy. Indefinite locks are forbidden. The concrete values for target prefixes, period, release authority, handling of wrongly uploaded objects, and protection of the tail record under `ledger/` in the ledger bucket (ADR-0017) follow the draft `infra/r2/README.md` §4 as written. Where §4 gives no value, the item is recorded as "미정 — 적용 전에 정해야 함" and no value is invented.

| Item | Value recorded | Source |
|---|---|---|
| Target prefixes (raw bucket `onjeon-raw-sources`) | `objects/`, `observations/` | README §4 |
| Target prefixes (derived bucket `onjeon-derived-sources`) | Not locked, or locked only briefly (the README does not choose between the two) | README §4 |
| Period | 미정 — 적용 전에 정해야 함. §4 gives only the form "a period lock (e.g. N days after object creation)"; N and its rationale are subject to approval. No value is set here. | README §4 |
| Release authority | Rule changes only by an Admin-permission token or the dashboard account. Collection and verification tokens never get Admin permission. Managing the dashboard account is the release authority. | README §4, §3 item 2 |
| Wrongly uploaded objects | Within the lock period they cannot be deleted either. Personal-data inclusion is blocked first at the collection stage (personal contract, health, family history and DNA material are not put in these buckets). The concrete handling procedure for an object that is already locked is 미정 — 적용 전에 정해야 함. `verify-copy` reports keys outside the pinned list and exits 1. | README §1, §4, §5 |
| Ledger bucket `onjeon-budget-ledger`, `ledger/` tail-record deletion (ADR-0017) | 미정 — 적용 전에 정해야 함. §4 does not list a ledger-bucket lock row; the gate row only says it is included. ADR-0017 states the tool cannot detect deletion of the ledger tail record and that the O14 lock is meant to cover it. Prefix, period and release authority for it are not set here. | README §4 (no row), ADR-0017 |

**Options considered (from the gate row text):**

- A (chosen): the tool's conditional writes + no delete command + a separate copy; no indefinite lock; no application before approval (draft `infra/r2/README.md` §4).
- B (rejected): an indefinite lock. Forbidden by the gate row.
- C (rejected): applying the bucket lock now, before approval. Forbidden by the gate row; applying it is a separate execution step needing 준태님's approval.

**Reasons:** R2 has no versioning and no Object Lock, so a bucket lock is the only storage-side way to stop overwrites and deletes. Until it is applied and approved, the repo relies on what already exists: every tool write is `If-None-Match: *` (an existing key with different bytes stops with `Conflict`), the tool has no delete command, and a separate copy covers what the tool cannot prevent. Tokens are still treated as able to delete (README §2, §6). An indefinite lock would make a wrongly uploaded object impossible to remove, so it is excluded. The README leaves the period and the ledger-bucket row open, and filling them without a basis would invent values, so they stay unset.

**Scope:** The O14 gate only: the default rule for the future bucket lock on `onjeon-raw-sources`, `onjeon-derived-sources` and the `ledger/` prefix of `onjeon-budget-ledger`. It does not change `infra/r2/README.md`, `infra/r2/budget_policy.json` or any job file, and it does not decide cost, hardware, mainnet, secrets, production deploys or payments.

**Consequence:** O14's default is fixed as conservative. The README §4 draft stays the source of the concrete values; this record adds none. The lock stays unapplied. Before any lock is applied, the unset items (period N and its rationale, the wrongly-uploaded-object procedure, the ledger-bucket prefix/period/release authority, and the derived-bucket choice) must be set, and 준태님 must approve the application. Until then the existing mitigations above are all that protect the buckets, and objects must be treated as deletable.

**Revisit if:** Right before a lock is applied, or when README §4 is revised.
