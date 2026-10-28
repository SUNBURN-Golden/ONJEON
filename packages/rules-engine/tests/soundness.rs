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
        let (n, flips) = hide_each_input(
            &|i| observe(&rule, i),
            case["id"].as_str().unwrap(),
            &case["inputs"],
        );
        assert!(flips.is_empty(), "{}", flips.join("\n"));
        checked += n;
    }
    assert!(
        checked >= 20,
        "soundness test must actually exercise many hidden-input combinations"
    );
}

/// Hide each known input with both null and key omission; return the number checked and
/// every variant whose definite answer differs from the fully-known one.
fn hide_each_input(observe: &dyn Fn(&J) -> J, id: &str, inputs: &J) -> (usize, Vec<String>) {
    let full = observe(inputs);
    let mut checked = 0;
    let mut flips = Vec::new();
    if !is_definite(&full) {
        return (checked, flips);
    }
    for (name, value) in inputs.as_object().unwrap() {
        if value.is_null() {
            continue; // Already unknown: this would not test hiding information.
        }
        for mode in ["null", "omitted"] {
            let mut hidden = inputs.clone();
            if mode == "null" {
                hidden[name] = J::Null;
            } else {
                hidden.as_object_mut().unwrap().remove(name);
            }
            let obs = observe(&hidden);
            if is_definite(&obs) && obs["payout"] != full["payout"] {
                flips.push(format!(
                    "case {id} hiding {name} ({mode}): {} became {}",
                    full["payout"], obs["payout"]
                ));
            }
            checked += 1;
        }
    }
    (checked, flips)
}

#[test]
fn hiding_an_input_never_changes_a_definite_answer_on_real_rules() {
    // I1 on the real-clause rules: the same invariant as the synthetic fixture above.
    let rules = real_rules();
    assert_eq!(
        rules.keys().map(String::as_str).collect::<Vec<_>>(),
        REAL_RULE_IDS,
        "real rule inventory must stay at seven audited rules"
    );
    let mut checked = 0;
    let mut per_rule = std::collections::BTreeMap::<String, usize>::new();
    let mut flips = Vec::new();
    for (case, rule_id, inputs) in real_cases() {
        let rule = &rules[&rule_id];
        let (n, f) = hide_each_input(&|i| observe(rule, i), case["id"].as_str().unwrap(), &inputs);
        if n > 0 {
            *per_rule.entry(rule_id).or_default() += n;
        }
        checked += n;
        flips.extend(f);
    }
    assert!(flips.is_empty(), "{}", flips.join("\n"));
    assert_eq!(
        per_rule.keys().collect::<Vec<_>>(),
        rules.keys().collect::<Vec<_>>(),
        "every real rule needs a definite case to hide inputs from; exercised {per_rule:?}"
    );
    assert!(
        checked >= 200,
        "expected many hidden-input combinations on real rules, ran {checked}"
    );
    println!("I1 null/omission variants by rule: {per_rule:?}; total {checked}");
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
            for (name, ty) in rule.source_json()["inputs"].as_object().unwrap() {
                if i.get(name).is_none_or(J::is_null) {
                    match ty.as_str() {
                        Some("bool") => i[name] = J::Bool(false),
                        Some("int" | "money_krw") => i[name] = J::from(0),
                        _ => {}
                    };
                }
            }
            observe(rule, &i)
        };
        flips.extend(hide_each_input(&broken, case["id"].as_str().unwrap(), &inputs).1);
    }
    for mode in ["null", "omitted"] {
        assert!(
            flips.iter().any(|f| f.contains(&format!("({mode})"))),
            "the checker must detect an unknown-as-false evaluator for {mode}"
        );
    }
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
    assert_eq!(checked, 4);
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
    // Range comparisons are rejected at load. A reversed date interval remains
    // loadable and exercises runtime Type errors under unknown eligibility.
    let reversed_days = json!({"days_between": ["date", {"date": "2199-12-30"},
        {"inclusive_start": true, "inclusive_end": true}]});
    for (condition, expected_error) in [
        (
            json!({"eq": [{"date_add": ["date", {"value": 1, "unit": "day"}]}, "date"]}),
            EvalError::DateOutOfRange {
                path: "amount.if.eq[0]".into(),
            },
        ),
        (
            json!({"lt": [reversed_days, 1]}),
            EvalError::Type {
                path: "amount.if.lt[0]".into(),
                message: "days_between needs the first date on or before the second, \
                          found the second 1 day(s) earlier; compare the dates with \
                          lt/gt instead"
                    .into(),
            },
        ),
    ] {
        let rule = conditional_amount_rule(
            json!({"if": condition, "then": {"krw": 1}, "else": {"krw": 2}}),
        );
        let mut inputs = json!({"amt": 5, "date": "2199-12-31"});
        let result = rule.evaluate(&inputs).unwrap();
        assert_eq!(result.eligibility, Tri::Unknown);
        assert_eq!(
            result.payout,
            Payout::Undetermined {
                conditional_amount: AmountOut::Unknown
            }
        );
        assert_eq!(result.missing_inputs, vec!["flag"]);
        assert!(result
            .trace
            .iter()
            .any(|entry| entry.path == "amount"
                && entry.result == format!("error: {expected_error}")));
        inputs["flag"] = json!(true);
        assert_eq!(rule.evaluate(&inputs).unwrap_err(), expected_error);
        inputs["flag"] = json!(false);
        assert_eq!(rule.evaluate(&inputs).unwrap().payout, Payout::NotPayable);
    }
}

#[test]
fn unknown_eligibility_handles_all_any_errors_inside_conditional_amount() {
    for (op, decisive) in [("all", false), ("any", true)] {
        for gate in [decisive, !decisive] {
            for error_first in [false, true] {
                let bad = json!({"eq": [{"add": ["amt", {"krw": 1}]}, {"krw": 1}]});
                let mut children = vec![json!(gate), bad];
                if error_first {
                    children.reverse();
                }
                let rule = conditional_amount_rule(json!({
                    "if": {op: children}, "then": {"krw": 10}, "else": {"krw": 20}
                }));
                let result = rule.evaluate(&json!({"amt": i64::MAX})).unwrap();
                let conditional_amount = if gate == decisive {
                    AmountOut::Exact {
                        krw: if decisive { 10 } else { 20 },
                    }
                } else {
                    AmountOut::Unknown
                };
                assert_eq!(result.eligibility, Tri::Unknown);
                assert_eq!(result.payout, Payout::Undetermined { conditional_amount });
                assert_eq!(result.missing_inputs, vec!["flag"]);
                assert!(result
                    .trace
                    .iter()
                    .any(|entry| entry.result.starts_with("error: arithmetic overflow")));
            }
        }
    }
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
