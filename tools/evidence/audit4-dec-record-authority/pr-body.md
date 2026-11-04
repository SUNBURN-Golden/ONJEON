Node `audit4-dec-record-authority`

Most DEC records document delegated decisions. They remain conditional development criteria within existing authority; changing gate definitions or higher-level decisions requires an ADR followed by BLUEPRINT §7 and related contract updates. Required owner approval and gate evidence remain separate requirements. Recording a DEC does not itself open a gate.

D-04 and D-12 record direct owner rulings; DEC-BUNDLE-STATUS part (1) also records a user decision. The decision note states that exception and directly cites DEC-O17 for the delegation and its six exclusions.

## Acceptance

- [x] Authority interpretation verified with repository tests and recorded local evidence.
- [ ] Corrected PR body applied and `rules-engine` confirmed green for the resulting head.

## Builder summary

Reproduce CI runs 41783150105, 41795070906 and 41802792915's missing trace handle, verify that adding this node ID fixes it, and retain the traceability guard. Regression tests cover the failed body and this replacement, including the PR_BODY environment entry point used by CI. The workflow now subscribes to PR edits as well as opened, synchronize and reopened events so a body correction can trigger a fresh check at the same head.

Validation commands, results, limitations, and logs: [evidence](tools/evidence/audit4-dec-record-authority/README.md).

The supervisor must publish the round 3 workflow change, apply this body to PR #417, and confirm the fresh `edited` event run receives this body and passes `rules-engine` at the resulting head. Record the run URL and full head SHA in the round 3 evidence. The latest supplied failure is run 41802792915 at 83837b547eeaab42434790c24eed557431182e11. Local verification does not establish a green remote CI run.

Refs #416
