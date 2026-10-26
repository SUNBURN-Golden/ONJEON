//! Soundness of unknown propagation: hiding an input may make the result less
//! defined, but must never flip it to a different definite answer.
mod common;
use common::*;
use onjeon_rules_engine::{AmountOut, EvalError, Payout, Rule, Tri};
use serde_json::{json, Value as J};

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

fn conditional_amount_rule(amount: J) -> Rule {
    let mut source = rule_json();
    source["inputs"] = json!({"flag": "bool", "amt": "money_krw", "date": "date"});
    source["eligibility"] = json!("flag");
    source["amount"] = amount;
    Rule::from_json(&source).unwrap()
}

#[test]
fn hiding_eligibility_keeps_an_overflowing_amount_undetermined() {
    let rule = conditional_amount_rule(json!({"add": ["amt", {"krw": 1}]}));
    let full = json!({"flag": false, "amt": i64::MAX});
    assert_eq!(rule.evaluate(&full).unwrap().payout, Payout::NotPayable);
    let (checked, flips) = hide_each_input(&|i| observe(&rule, i), "amount-overflow", &full);
    assert_eq!(checked, 2);
    assert!(flips.is_empty(), "{flips:?}");

    for hidden in [
        json!({"amt": i64::MAX}),
        json!({"flag": null, "amt": i64::MAX}),
    ] {
        let result = rule.evaluate(&hidden).unwrap();
        assert_eq!(result.eligibility, Tri::Unknown);
        assert_eq!(
            result.payout,
            Payout::Undetermined {
                conditional_amount: AmountOut::Unknown
            }
        );
        assert_eq!(result.missing_inputs, vec!["flag"]);
        let error = result
            .trace
            .iter()
            .find(|entry| entry.path == "amount")
            .unwrap();
        assert_eq!(error.op, "add");
        assert_eq!(error.result, "error: arithmetic overflow at amount");
        assert!(!result
            .trace
            .iter()
            .any(|entry| entry.path.starts_with("amount.")));
        assert_eq!(result, rule.evaluate(&hidden).unwrap());
    }

    assert!(matches!(
        rule.evaluate(&json!({"flag": true, "amt": i64::MAX})),
        Err(EvalError::Overflow { path }) if path == "amount"
    ));
}

#[test]
fn unknown_eligibility_preserves_successful_conditional_amounts_and_blockers() {
    let rule = conditional_amount_rule(json!({"add": ["amt", {"krw": 1}]}));
    for (inputs, conditional_amount, missing) in [
        (
            json!({"amt": 10}),
            AmountOut::Exact { krw: 11 },
            vec!["flag"],
        ),
        (json!({}), AmountOut::Unknown, vec!["amt", "flag"]),
    ] {
        let result = rule.evaluate(&inputs).unwrap();
        assert_eq!(result.eligibility, Tri::Unknown);
        assert_eq!(result.payout, Payout::Undetermined { conditional_amount });
        assert_eq!(result.missing_inputs, missing);
        assert!(!result
            .trace
            .iter()
            .any(|entry| entry.result.starts_with("error:")));
    }
}

#[test]
fn unknown_eligibility_also_absorbs_amount_date_and_runtime_type_errors() {
    let range = json!({"multiply_rate": ["amt", "0.5", {"rounding": "unspecified", "unit": 10}]});
    for (condition, expected_error) in [
        (
            json!({"eq": [{"date_add": ["date", {"value": 1, "unit": "day"}]}, "date"]}),
            EvalError::DateOutOfRange {
                path: "amount.if.eq[0]".into(),
            },
        ),
        (
            json!({"lt": [range, {"krw": 1}]}),
            EvalError::Type {
                path: "amount.if".into(),
                message: "cannot compare money_range with money".into(),
            },
        ),
    ] {
        let rule = conditional_amount_rule(
            json!({"if": condition, "then": {"krw": 1}, "else": {"krw": 2}}),
        );
        let mut inputs = json!({"amt": 5, "date": "2199-12-31"});
        let result = rule.evaluate(&inputs).unwrap();
        assert_eq!(
            result.payout,
            Payout::Undetermined {
                conditional_amount: AmountOut::Unknown
            }
        );
        assert_eq!(result.missing_inputs, vec!["flag"]);
        inputs["flag"] = json!(true);
        assert_eq!(rule.evaluate(&inputs).unwrap_err(), expected_error);
    }
}
