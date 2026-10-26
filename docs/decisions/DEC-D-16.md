# Decision: Decision gate D-16

Decided by Fable 5.1 (ONJEON autoloop, 2026-10-15 10:34 KST); amended 2026-10-26 by audit1-ux-layer-zero-code to add U7; reversible.

**Decision:** Adopt the D-16 recommendation and fill in the numbers.

1) Seven tasks. Five come from CONSUMER_FLOW_SPEC §7 and 화면 설계서 §12-6: U1 tell budget from premium within 5s; U2 explain what each of two plans gains and loses within 30s; U3 find the public-vs-personal condition difference unaided; U4 do not misread a no-price product as 'excluded for being expensive'; U5 reach the source text in 2 taps or fewer. The sixth is U6, tell a computed result from '확인 필요' in a same-situation comparison. The seventh is U7, check a planner's explanation against the source: given one sales-style sentence about the virtual contract, the participant uses 증거 보기, comparison or '확인할 조건' to find the clause and says whether the sentence matches it (09_제품목적_대응표 P18). Two other §7 items are design properties checked by automated UI tests, not tasks: raising the budget does not force more coverage, and family-history/DNA data stays out of ads and planner data.

2) Sample. Round 1 is 8–12 participants and is for finding problems only. It is not statistical proof and cannot support an '이해됨' claim. After fixes, a confirmation round of 12 or more fresh participants is run, and the confirmation round alone supports '이해됨' and release gate 9. Participants are non-experts and use virtual contracts only, with no personal contract, health or family data (제3부 §51.5).

3) Acceptance, judged per task and never averaged. U1, U2, U3 and U5 need 80% or more (10 of 12). U4, U6 and U7 need 90% or more (11 of 12), because misreading them hurts the consumer. Any task fails if 3 or more participants repeat the same misunderstanding. A failed task is fixed and retested with new participants. Misunderstanding rate is recorded per task as the core metric.

4) Freeze before the test. Before the first session, commit docs/ux-tests/PREREG.md with the task wording, the virtual contract, the pass/misunderstanding scoring table, the thresholds and the participant criteria. Changing any of them after the test starts voids that round. Changing the criteria later needs a new decision record.

5) Reporting. Report as 'k of n', and state the small sample and virtual-contract-only limits. Do not claim user validation before the confirmation round.

The 80%/90% thresholds, the 3-person repeat rule and the 12-person confirmation round are my proposed values, with no basis elsewhere in the repo. The decision is made by the agent on the owner's behalf, and the owner can override it before the test starts.

**Why:** The repo fixes the criteria (5s, 30s, 2 taps, misunderstanding rate) in CONSUMER_FLOW_SPEC §7, 화면 설계서 §12-6, 제3부 §51.5 and Masterplan v0.3, and says 8–12 people is for problem discovery, not proof. It sets no pass numbers, so release gate 9 cannot be judged. Axis 4 of the implementation plan forbids reporting '이해됨' without thresholds fixed beforehand. U7 was added on 2026-10-26 because 09 P18 makes passing an 'explanation versus source' task the completion evidence for the product's purpose, and U1-U6 had no such task; T-UX-01 cannot add it itself because it may not edit docs/decisions/**. U6 is added because the 시안 비교 comparison and T-AP-07 depend on consumers not reading '확인 필요' as a computed amount or as 'no coverage'. With 12 participants, 90% means at most one misunderstanding. The thresholds are a minimum bar before launch, not statistical proof. The test has not been run, so nothing here says the screens are understood.

**Options:** ['A (chosen): seven tasks (U7 added 2026-10-26), round 1 of 8–12 for problem discovery plus a confirmation round of 12 or more, thresholds frozen in PREREG before the test', "B: five tasks and a single 8–12 person round that decides pass/fail. This drops the 'computed vs 확인 필요' task and reports '이해됨' from a tiny sample", 'C: large statistically powered sample of dozens to hundreds. This is too costly for a pre-launch virtual-contract test and out of proportion to its purpose', 'D: set the thresholds after seeing results. This is forbidden by implementation plan axis 4 and amounts to fitting the criteria to the outcome']

**Revisit if:** The owner changes the thresholds or sample size; round 1 shows a task was badly designed; the target user group changes; an external review or regulator asks for a larger sample; or the screen flow changes so the task wording no longer fits.
