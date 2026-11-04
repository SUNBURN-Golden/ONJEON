Node `audit4-dec-record-authority`

Most DEC records document delegated decisions. They remain conditional development criteria within existing authority; changing gate definitions or higher-level decisions requires an ADR followed by BLUEPRINT §7 and related contract updates. Required owner approval and gate evidence remain separate requirements. Recording a DEC does not itself open a gate.

D-04 and D-12 record direct owner rulings; DEC-BUNDLE-STATUS part (1) also records a user decision. The decision note now states that exception and has a complete heading.

## Acceptance
- [x] Finding resolved with repository tests and recorded local evidence.

## Builder summary

Reproduce CI run 41783150105's missing trace handle, verify that adding this node ID fixes it, and retain the traceability guard. Regression tests cover the failed body and this replacement, including the PR_BODY environment entry point used by CI.

Validation commands, results, limitations, and logs: [evidence](tools/evidence/audit4-dec-record-authority/README.md).

The supervisor must apply this body and rerun GitHub CI. Local verification does not establish a green remote CI run.

Refs #416
