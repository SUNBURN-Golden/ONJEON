Node `audit4-dec-record-authority`

Most `DEC-*` records document delegated or provisional development decisions. They remain conditional development criteria within existing design/delegation scope; changing gate definitions or higher-level decisions requires an ADR followed by BLUEPRINT §7 and related contract updates. Required owner approval and gate evidence remain separate requirements. Recording a DEC does not itself open a gate.

The decision note classifies every record by recorded time. D-04 and D-12 are direct owner rulings; DEC-BUNDLE-STATUS part (1) records the 2026-10-13 user decision and DEC-D-08 confirms the 2026-10-12 owner decision. D-02, O12, O04, D-08, D-07 and D-16 were recorded by the autoloop before DEC-O17's 2026-10-15 14:44 delegation, so that delegation is not retroactive; they are provisional development criteria inside existing design scope, not owner confirmations. DEC-O04 is condition satisfaction for the existing O04 gate, not a gate-definition change: `compare_price` still needs the I7/I8/K13/bundle tests and registration before it is enabled, and the record alone releases nothing.

## Acceptance

- [x] Authority interpretation, pre-delegation classification and O04 condition-satisfaction reading verified with repository tests and recorded local evidence.
- [ ] Corrected PR body applied and `rules-engine` confirmed green for the resulting head.

## Builder summary

Reproduce the missing trace handle from CI runs 41783150105, 41795070906 and 41802792915, then verify that this body (which names the node) passes the unchanged guard. Regressions cover the failed fixture and this replacement through CI's `PR_BODY` environment entry point. The workflow keeps `opened`, `synchronize`, `reopened` and `edited`, and gates the heavy steps off for `edited` events so a body correction refreshes only the traceability verdict at the same commit.

Validation commands, results, limitations, and logs: [evidence](tools/evidence/audit4-dec-record-authority/README.md).

The supervisor must publish this round, apply this body to PR #417, and confirm a fresh `edited` run receives this body and passes `rules-engine` at the resulting head. Record the run URL and full head SHA in the round 4 evidence. The latest supplied failure is run 41802792915 at 83837b547eeaab42434790c24eed557431182e11; the reviewed branch head was fb7a400. Local verification does not establish a green remote CI run.

Refs #416
