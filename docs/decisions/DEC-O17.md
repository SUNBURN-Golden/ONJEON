# Decision: Decision gate O17

**decided_by:** Delegated by 준태님 on 2026-10-15 14:44 KST; the rule was decided by the assistant (ONJEON), NOT personally decided by 준태님. The assistant set this default under that delegation.

**time:** 2026-10-15 14:44 KST (delegation); reversible.

**Delegation (quoted verbatim, 준태님, 2026-10-15 14:44 KST, 개발본부 그룹 채팅):**

> "다들 종료하지말고, 제품화때까지 열심히 개발하도록해라. 내 결정이 필요한건 전부 너네가 알아서 하렴."

The delegation excludes cost, hardware, mainnet, secret keys, production deployment and payment. This document records a conservative default for O17 only. It performs and authorizes no real-world action: no R2 lock is applied, no personal data goes to an external AI, nothing is spent, no mass collection is started, nothing is deployed to production, and no secret is handled. It does not access the real R2, tokens or billing.

**Gate (O17, owner: 데이터 운영 책임, due: before mass automatic collection starts):** the mass automatic collection gate. Its items are the ledger checkpoint, the bucket lock (O14), token reissue, the number of execution environments / concurrency / scheduled-run controls, the allowed scope and limits for collection jobs whose target keys cannot be fixed in advance, the method of reconciling ledger figures against the Cloudflare bill, and verifying the execution controls on the real R2.

**Decision:** Keep the conservative default from the gate row (`infra/r2/BUDGET.md` §6): one designated execution environment, concurrency 1, manual runs, and fixed-key jobs only. A collection job whose target keys cannot be fixed beforehand is not allowed. The following stay as preconditions to be met before mass automatic collection starts, and none of them is done or decided by this record:

- ledger checkpoint (summary)
- bucket lock (O14)
- token reissue
- a method for reconciling ledger figures against the Cloudflare bill
- verification of the execution controls on the real R2

No numeric limit is set for collection jobs whose keys cannot be fixed, because they are not allowed. Mass automatic collection is not turned on by this record.

**Options:**
- A (chosen): one designated execution environment, concurrency 1, manual runs, fixed-key jobs only (`infra/r2/BUDGET.md` §6); the checkpoint, O14 lock, token reissue, billing reconciliation and real-R2 verification remain preconditions for mass automatic collection.
- B (not chosen): more than one execution environment or concurrency above 1.
- C (not chosen): scheduled (automatic) runs now.
- D (not chosen): allow collection jobs whose target keys cannot be fixed in advance, with some scope and limit.

The gate row itself names only A as the default; B–D are the alternatives the gate row's items (environment count, concurrency, scheduled runs, unfixed-key jobs) leave open.

**Reasons:** The R2 has no hard spending cap, and the budget tool's own limits only hold under the §6 operating scope (`infra/r2/BUDGET.md` §1, §5). Several environments running at once can exceed the entry limit, the last ledger record can be deleted without detection until O14 is applied, the ledger is not the Cloudflare bill, and the current execution controls were verified only against an S3 stub server, not the real R2. With more than 100 ledger records the run stops, so the ledger needs a checkpoint design before bulk collection. A conservative default keeps spending predictable while development continues, and it is reversible.

**Scope:** The R2 raw-source collection operating scope described in `infra/r2/BUDGET.md` §6 and the O17 gate row. It changes no code, no `infra/r2/budget_policy.json`, no jobs and no data. It sets no new numbers.

**Consequence:** Collection stays at one designated environment, concurrency 1, manual runs, fixed-key jobs. Mass automatic collection stays off. The O17 gate remains open for anything beyond that default. Mass automatic collection stays blocked until the preconditions above are satisfied and the default is revisited.

**Revisit if:** O14 (the bucket lock) has been applied; or a request to scale up collection is made (more environments, concurrency above 1, scheduled runs, or jobs whose keys cannot be fixed beforehand); or 준태님 decides O17 directly or withdraws this.
