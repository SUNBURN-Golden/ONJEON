# Decision: Status of the 설계검토_결과 bundle (execution basis vs canon)

**decided_by:** Two parts with different sources. (1) The execution/completion basis was decided by the user on 2026-10-13 (그록봇 가동 결정 and 진행 지시, recorded in [그록봇_인계/README.md](../blueprint/proposals/설계검토_결과/그록봇_인계/README.md) line 3 and §8). (2) Keeping the bundle out of canon, and splitting the two statuses in the bundle's wording, was decided by the assistant (ONJEON autoloop) under the 2026-10-15 delegation recorded in [DEC-O17](DEC-O17.md). The user did NOT personally decide part (2).

**time:** 2026-10-26 KST; reversible.

**Question (Audit 1 finding `audit1-bundle-canonical-status`):** `설계검토_결과/README.md:10` said the bundle "is not an adopted canon, correction judgment awaits independent re-review", while `그록봇_인계/README.md:3` says the user decided to run on it and 09 is the top criterion. Is the bundle canonical (then drop the disclaimer), or not (then 09 cannot be the completion criterion)?

**2026-10-29 부분 대체:** [ADR-0019](ADR-0019-제품-완료와-작업-계약-한정-채택.md)가 아래 2번의 정본 미채택 판단 중 09·tasks.json의 역할만 대체한다. 두 파일은 이제 BLUEPRINT 하위의 제품 완료 증거·데몬 작업 소스 및 개별 수락 계약이다. 상위 계약이 우선하며 묶음 전체·온톨로지·daemon_rules.json·common_done_criteria는 이번 정본 채택 대상이 아니다. 아래는 2026-10-26 결정 이력이며 현재 상태는 ADR-0019·BLUEPRINT §0.1·§9·§13을 따른다.

**Decision (2026-10-26 historical):** The word '채택' (adopted) covered two different statuses. They are now stated separately:

1. **Execution and completion basis: adopted.** By the user decision of 2026-10-13, [09_제품목적_대응표](../blueprint/proposals/설계검토_결과/09_제품목적_대응표.md) (P01~P19), `tasks.json` (tasks, done_criteria, required_test_ids) and `daemon_rules.json` are the binding basis for running tasks and judging completion. 09 stays the top completion criterion. This matches [BLUEPRINT §11](../BLUEPRINT.md), which already judges first-release completion by 09 P01~P19 and the T-OP-08 gate. Revisions after 12c1726 are handed over without waiting for a bundle-wide re-review (진행 지시 2026-10-13); review happens per PR.
2. **Canon: not adopted.** The bundle is not part of BLUEPRINT, DECISIONS or the ontology canon. Its canon proposals (U-01~U-04, onto-0.2 objects, the A-01 wording, the judgment-criteria area; README §5) reach canon only through the D-21 path (a new ADR) with an independent reviewer outside the authoring model family on that PR. Where the bundle and canon differ, canon wins until such an ADR lands.

Unchanged and separate: `_common_done_criteria_status=non_binding_until_adopted` (README §0.1). That concerns the PR template, not this question.

**Options:**
- A (not chosen): declare the whole bundle canon and drop the disclaimer. This would bypass the D-21 ADR path and the outside-family review for real canon changes.
- B (not chosen): declare it not adopted in any sense and stop using 09 as the completion criterion. This contradicts the recorded user decision of 2026-10-13 and BLUEPRINT §11, and leaves T-OP-08 `purpose-rows-all-closed` without a basis.
- C (chosen): two statuses, stated separately in the bundle README, `tasks.json`/`daemon_rules.json` `_status` and the 그록봇 README, enforced by `tools/tests/test_pr_policy.py`.

**Scope:** Wording of the bundle's status lines and this record. It changes no task, criterion, gate, code or canon document content. It does not approve deploying the daemon, any data access, or any merge.

**Revisit if:** the user says the bundle is canon; or an outside-family independent review of the bundle concludes (then fold its canon proposals in by ADR, or record what it rejects); or the user withdraws the 2026-10-13 decision.
