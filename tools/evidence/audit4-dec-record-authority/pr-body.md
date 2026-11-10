Node `audit4-dec-record-authority`

Most `DEC-*` records document delegated, separately delegated or provisional development decisions. They remain conditional development criteria within existing design/delegation scope; changing gate definitions or higher-level decisions requires an ADR followed by BLUEPRINT §7 and related contract updates. Required owner approval and gate evidence remain separate requirements. Recording a DEC does not itself open a gate.

The decision note classifies every `DEC-*.md` record and every amendment/addendum by recorded time. D-04 and D-12 are direct owner rulings; DEC-BUNDLE-STATUS part (1) records the 2026-10-13 user decision and D-08 confirms the 2026-10-12 owner decision. DEC-CANON-T-CT-02 is a separate 2026-10-13 16:58 KST delegation scoped to that canon change. D-02, O12, O04, D-08, D-07 and D-16 were recorded by the autoloop before DEC-O17's 2026-10-15 14:44 delegation, so that delegation is not retroactive; they are provisional development criteria inside existing design scope, not owner confirmations. D-03, D-06, D-14, D-17, D-18, O02, O14, O17 and DEC-BUNDLE-STATUS part (2) are delegated records under the 2026-10-15 delegation. D-16's 2026-10-26 U7 amendment and O17's 2026-10-26 addendum are post-delegation delegated records; DEC-BUNDLE-STATUS's 2026-10-29 partial replacement was performed by ADR-0019. DEC-O04 is condition satisfaction for the existing O04 gate, not a gate-definition change: `compare_price` still needs the I7/I8/K13/bundle tests and registration before it is enabled, and the record alone releases nothing. The O12 and D-08 "registering lifts" sentences are the existing registration procedures subject to their remaining conditions and evidence, not self-executing gate releases or gate-definition changes.

## Acceptance

- [x] Authority interpretation, complete pre/post-delegation classification, amendment classification and O04/O12/D-08 condition-satisfaction readings verified with repository tests and recorded local evidence.
- [ ] Corrected PR body applied and both `pr-traceability` and a full `rules-engine` run confirmed green for the resulting head.

## Builder summary

The decision note's authority table now classifies all 18 `DEC-*.md` records, including the earlier 2026-10-13 16:58 KST delegation recorded in DEC-CANON-T-CT-02 and the post-delegation D-16 amendment. Regressions iterate every `DEC-*.md` file and discover amendment/addendum timestamps in the source records, so an omission fails.

The traceability guard now runs in its own `pr-traceability` workflow. `ci.yml` no longer listens to `edited` and contains no `github.event.action` gating, so a body correction re-runs only the guard and cannot replace a failed or not-yet-run `rules-engine` test job with success. The code push runs the full suite.

Validation commands, results, limitations, and logs: [evidence](tools/evidence/audit4-dec-record-authority/README.md).

The supervisor must publish this round, apply this body to PR #417, confirm `pr-traceability` succeeds at the head, and confirm a full `rules-engine` run on that head. Record both run URLs and the full head SHA in the round 5 evidence. The latest supplied failure is run 41802792915 at 83837b547eeaab42434790c24eed557431182e11; the reviewed branch head was fc6bd92a7872972787252415034e0c0e041d1283. Local verification does not establish a green remote CI run.

Refs #416
