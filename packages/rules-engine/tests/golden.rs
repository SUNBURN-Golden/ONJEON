mod common;
use common::*;
use onjeon_rules_engine::Rule;

#[test]
fn golden_table_matches_expert_expectations() {
    let rule = Rule::from_json(&rule_json()).expect("fixture rule loads");
    let mut failures = Vec::new();
    for case in cases() {
        let observed = observe(&rule, &case["inputs"]);
        if observed != case["expect"] {
            failures.push(format!(
                "{}: expected {} but got {}",
                case["id"], case["expect"], observed
            ));
        }
    }
    assert!(
        failures.is_empty(),
        "golden failures:\n{}",
        failures.join("\n")
    );
}

#[test]
fn same_input_gives_byte_identical_output() {
    let rule = Rule::from_json(&rule_json()).unwrap();
    for case in cases() {
        let a = serde_json::to_string(&rule.evaluate(&case["inputs"]).unwrap()).unwrap();
        let b = serde_json::to_string(&rule.evaluate(&case["inputs"]).unwrap()).unwrap();
        assert_eq!(a, b, "result must be reproducible for {}", case["id"]);
    }
}

#[test]
fn trace_records_every_evaluated_node_and_hash_changes_with_input() {
    let rule = Rule::from_json(&rule_json()).unwrap();
    let r1 = rule.evaluate(&serde_json::json!({"elapsed_calendar_days": 0, "target_event": true, "excluded_X": false, "already_paid": false, "insured_amount_krw": 10000000})).unwrap();
    assert!(r1
        .trace
        .iter()
        .any(|t| t.path == "eligibility" && t.op == "all"));
    assert!(r1
        .trace
        .iter()
        .any(|t| t.op == "multiply_rate" && t.result == "5000000 KRW"));
    assert_eq!(r1.input_snapshot_hash.len(), 64);
    let r2 = rule.evaluate(&serde_json::json!({"elapsed_calendar_days": 1, "target_event": true, "excluded_X": false, "already_paid": false, "insured_amount_krw": 10000000})).unwrap();
    assert_ne!(r1.input_snapshot_hash, r2.input_snapshot_hash);
}
