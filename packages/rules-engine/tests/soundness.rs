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

/// Hide each input of `inputs` in turn; return how many hidden variants were checked and
/// every variant whose definite answer differs from the fully-known one.
fn hide_each_input(observe: &dyn Fn(&J) -> J, id: &str, inputs: &J) -> (usize, Vec<String>) {
    let full = observe(inputs);
    let mut checked = 0;
    let mut flips = Vec::new();
    if !is_definite(&full) {
        return (checked, flips);
    }
    for name in inputs.as_object().unwrap().keys() {
        let mut hidden = inputs.clone();
        hidden[name] = J::Null;
        let obs = observe(&hidden);
        if is_definite(&obs) && obs["payout"] != full["payout"] {
            flips.push(format!(
                "case {id} hiding {name}: {} became {}",
                full["payout"], obs["payout"]
            ));
        }
        checked += 1;
    }
    (checked, flips)
}

#[test]
fn hiding_an_input_never_changes_a_definite_answer_on_real_rules() {
    // I1 on the real-clause rules: the same invariant as the synthetic fixture above.
    let rules = real_rules();
    let mut checked = 0;
    let mut rules_exercised = std::collections::BTreeSet::new();
    let mut flips = Vec::new();
    for (case, rule_id, inputs) in real_cases() {
        let rule = &rules[&rule_id];
        let (n, f) = hide_each_input(&|i| observe(rule, i), case["id"].as_str().unwrap(), &inputs);
        if n > 0 {
            rules_exercised.insert(rule_id);
        }
        checked += n;
        flips.extend(f);
    }
    assert!(flips.is_empty(), "{}", flips.join("\n"));
    assert_eq!(
        rules_exercised.len(),
        rules.len(),
        "every real rule needs a definite case to hide inputs from; exercised {rules_exercised:?}"
    );
    assert!(
        checked >= 200,
        "expected many hidden-input combinations on real rules, ran {checked}"
    );
}

#[test]
fn hide_check_catches_unknown_treated_as_false_on_real_rules() {
    // Negative control: an evaluator that turns a hidden input into `false`/`0` instead of
    // unknown (the bug I1 forbids) must be flagged by the same checker, or the real-rule
    // test above proves nothing.
    let rules = real_rules();
    let mut flips = Vec::new();
    for (case, rule_id, inputs) in real_cases() {
        let rule = &rules[&rule_id];
        let broken = |i: &J| {
            let mut i = i.clone();
            for (name, v) in i.as_object_mut().unwrap() {
                if v.is_null() {
                    match rule.source_json()["inputs"][name].as_str() {
                        Some("bool") => *v = J::Bool(false),
                        Some("int" | "money_krw") => *v = J::from(0),
                        _ => {}
                    }
                }
            }
            observe(rule, &i)
        };
        flips.extend(hide_each_input(&broken, case["id"].as_str().unwrap(), &inputs).1);
    }
    assert!(
        !flips.is_empty(),
        "the checker must detect an unknown-as-false evaluator"
    );
}

#[test]
fn unknown_is_never_reported_as_zero_or_not_payable() {
    let rule = Rule::from_json(&rule_json()).unwrap();
    let r = rule.evaluate(&serde_json::json!({})).unwrap();
    assert_ne!(format!("{:?}", r.payout), "NotPayable");
    assert!(!r.missing_inputs.is_empty());
}

#[test]
fn hiding_an_irrelevant_failing_input_preserves_a_decisive_all_any_answer() {
    // Audit 2: even a valid input can fail inside a child expression. Replacing that
    // input with unknown must preserve the independent decisive child's answer.
    for (op, decisive) in [("all", false), ("any", true)] {
        for error_first in [false, true] {
            let bad = serde_json::json!({"eq": [
                {"date_add": ["d", {"value": 1, "unit": "day"}]}, "d"
            ]});
            let mut children = vec![serde_json::json!("gate"), bad];
            if error_first {
                children.reverse();
            }
            let rule = Rule::from_json(&serde_json::json!({
                "rule_id": "soundness-all-any-errors", "rule_version": "1",
                "schema_version": "rule-0.1", "calendar": "Asia/Seoul",
                "publication_state": "fixture_only", "evidence_refs": [],
                "inputs": {"gate": "bool", "d": "date"},
                "eligibility": {op: children}, "amount": {"krw": 100},
                "unknown_policy": "use_three_valued_logic_never_default_to_zero"
            }))
            .unwrap();
            let full = observe(
                &rule,
                &serde_json::json!({"gate": decisive, "d": "2199-12-31"}),
            );
            assert!(is_definite(&full));
            for hidden in [
                serde_json::json!({"gate": decisive}),
                serde_json::json!({"gate": decisive, "d": null}),
            ] {
                assert_eq!(observe(&rule, &hidden), full);
            }
            // Hiding the deciding input too must lose the decision, never invent one.
            let both_hidden = observe(&rule, &serde_json::json!({}));
            assert!(!is_definite(&both_hidden));
            assert_eq!(both_hidden["eligibility"], "unknown");
            assert_eq!(
                both_hidden["missing_inputs"],
                serde_json::json!(["d", "gate"])
            );
        }
    }
}
