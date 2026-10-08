//! Soundness of unknown propagation: hiding an input may make the result less
//! defined, but must never flip it to a different definite answer.
mod common;
use common::*;
use onjeon_rules_engine::Rule;
use serde_json::Value as J;

fn is_definite(observed: &J) -> bool {
    match observed["payout"]["kind"].as_str().unwrap() {
        "not_payable" => true,
        "payable" => observed["payout"]["amount"]["kind"] != "unknown",
        _ => false,
    }
}

#[test]
fn hiding_an_input_never_changes_a_definite_answer() {
    let rule = Rule::from_json(&rule_json()).unwrap();
    let mut checked = 0;
    for case in cases() {
        let full = observe(&rule, &case["inputs"]);
        if !is_definite(&full) {
            continue;
        }
        for name in case["inputs"].as_object().unwrap().keys() {
            let mut hidden = case["inputs"].clone();
            hidden[name] = J::Null;
            let obs = observe(&rule, &hidden);
            if is_definite(&obs) {
                assert_eq!(
                    obs["payout"], full["payout"],
                    "case {} hiding {name}: definite answer changed",
                    case["id"]
                );
            }
            checked += 1;
        }
    }
    assert!(
        checked >= 20,
        "soundness test must actually exercise many hidden-input combinations"
    );
}

#[test]
fn unknown_is_never_reported_as_zero_or_not_payable() {
    let rule = Rule::from_json(&rule_json()).unwrap();
    let r = rule.evaluate(&serde_json::json!({})).unwrap();
    assert_ne!(format!("{:?}", r.payout), "NotPayable");
    assert!(!r.missing_inputs.is_empty());
}
