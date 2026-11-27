# Scenario calculation adapter

`create_scenario` and `evaluate_coverage` accept the generated public and personal request types. Supply the selected coverage and a release-pinned scenario context. The adapter prepares request facts, runs the twin runtime, and returns a generated `ScenarioResult`. HTTP routing, authentication, coverage selection and release metadata come from the caller.

For an event list, an explicit empty assumption or user confirmation means no events in the scope being evaluated. Supply server-verified facts only after confirming the entire scope for the coverage and event window. A bare empty list in the ordinary facts map means unknown. The precedence is assumptions, ordinary facts, user-confirmed facts, then server-verified facts, with later values taking priority.

An amount calculation issue sets the display status to `hold`. The adapter builds the explanation from `CalculationIssueCode::screen_ko()` when the vocabulary supplies a screen label.

Run the service tests from the repository root.

```sh
cargo test --manifest-path services/scenario-api/Cargo.toml --locked --offline --target-dir target/scenario-api
```
