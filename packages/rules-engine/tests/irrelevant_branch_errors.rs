//! Audit 5: the reported real-clause reproduction and the interaction between
//! deferred logical errors and an amount error under unknown eligibility.
use onjeon_rules_engine::{
    AmountOut, ContractEffect, ContractEffectOut, EvalError, Payout, Rule, Tri,
};
use serde_json::{json, Value as J};

#[test]
fn kyobo_waiting_exclusion_survives_an_out_of_range_waiting_date() {
    let original: J = serde_json::from_str(include_str!(
        "../../fixtures/rules/real/kyobo-1995-cancer-waiting.json"
    ))
    .unwrap();
    for schema in ["rule-0.1", "rule-0.2"] {
        for reversed in [false, true] {
            let mut source = original.clone();
            source["schema_version"] = json!(schema);
            if reversed {
                source["eligibility"]["all"]
                    .as_array_mut()
                    .unwrap()
                    .reverse();
            }
            let rule = Rule::from_json(&source).unwrap();
            assert_eq!(rule.publication_state(), "fixture_only");
            let error = EvalError::DateOutOfRange {
                path: format!("eligibility.all[{}].gte[1]", usize::from(reversed)),
            };
            for amount in [None, Some(J::Null), Some(json!(10_000_000))] {
                let mut inputs = json!({
                    "contract_date": "2199-11-01", "diagnosis_date": "2199-12-31",
                    "dx_in_cancer_annex": false
                });
                if let Some(amount) = amount {
                    inputs["benefit_amount_krw"] = amount;
                }
                let result = rule.evaluate(&inputs).unwrap();
                assert_eq!(result.eligibility, Tri::False);
                assert_eq!(result.payout, Payout::NotPayable);
                assert!(result.missing_inputs.is_empty());
                assert!(result
                    .trace
                    .iter()
                    .any(|t| t.result == format!("error: {error}")));
                assert!(!result.trace.iter().any(|t| t.path.starts_with("amount")));
                let reloaded = Rule::from_json(rule.source_json()).unwrap();
                assert_eq!(
                    serde_json::to_vec(&result).unwrap(),
                    serde_json::to_vec(&reloaded.evaluate(&inputs).unwrap()).unwrap()
                );

                // Without a definite exclusion the date failure is relevant, even
                // when the annex input is unknown. Do not invent a payable answer.
                for annex in [Some(json!(true)), Some(J::Null), None] {
                    if let Some(annex) = annex {
                        inputs["dx_in_cancer_annex"] = annex;
                    } else {
                        inputs.as_object_mut().unwrap().remove("dx_in_cancer_annex");
                    }
                    assert_eq!(rule.evaluate(&inputs).unwrap_err(), error);
                }
            }
        }
    }
}

#[test]
fn logical_and_amount_errors_preserve_unknown_eligibility_together() {
    for schema in ["rule-0.1", "rule-0.2"] {
        for (op, decisive) in [("all", false), ("any", true)] {
            for error_first in [false, true] {
                let bad = json!({"eq": [
                    {"date_add": ["date", {"value": 1, "unit": "day"}]}, "date"
                ]});
                let mut children = vec![json!(decisive), bad];
                if error_first {
                    children.reverse();
                }
                let mut source = json!({
                    "rule_id": "audit5-irrelevant-branch-errors", "rule_version": "1",
                    "schema_version": schema, "calendar": "Asia/Seoul",
                    "publication_state": "fixture_only", "evidence_refs": [],
                    "inputs": {"flag": "bool", "date": "date", "amt": "money_krw"},
                    "eligibility": {"if": {op: children},
                        "then": if decisive { json!("flag") } else { json!(false) },
                        "else": if decisive { json!(false) } else { json!("flag") }},
                    "amount": {"add": ["amt", {"krw": 1}]},
                    "unknown_policy": "use_three_valued_logic_never_default_to_zero"
                });
                if schema == "rule-0.2" {
                    source["contract_effect"] = json!("terminated_pay_reserve");
                }
                let rule = Rule::from_json(&source).unwrap();
                let inputs = json!({"date": "2199-12-31", "amt": i64::MAX});
                let result = rule.evaluate(&inputs).unwrap();
                assert_eq!(result.eligibility, Tri::Unknown);
                assert_eq!(
                    result.payout,
                    Payout::Undetermined {
                        conditional_amount: AmountOut::Unknown
                    }
                );
                assert_eq!(result.missing_inputs, ["flag"]);
                assert_eq!(
                    result.contract_effect,
                    if schema == "rule-0.2" {
                        ContractEffectOut::Undetermined {
                            conditional_effect: ContractEffect::TerminatedPayReserve,
                        }
                    } else {
                        ContractEffectOut::None
                    }
                );
                let errors: Vec<_> = result
                    .trace
                    .iter()
                    .filter(|t| t.result.starts_with("error: "))
                    .collect();
                assert_eq!(errors.len(), 2);
                assert_eq!(errors[1].path, "amount");
                assert_eq!(errors[1].result, "error: arithmetic overflow at amount");
                for error in errors {
                    assert!(!result
                        .trace
                        .iter()
                        .any(|t| t.path.starts_with(&format!("{}.", error.path))));
                }
                let mut null_inputs = inputs.clone();
                null_inputs["flag"] = J::Null;
                assert_eq!(
                    serde_json::to_vec(&result).unwrap(),
                    serde_json::to_vec(&rule.evaluate(&null_inputs).unwrap()).unwrap()
                );
                null_inputs["flag"] = json!(true);
                assert_eq!(
                    rule.evaluate(&null_inputs).unwrap_err(),
                    EvalError::Overflow {
                        path: "amount".into()
                    }
                );
                null_inputs["flag"] = json!(false);
                let excluded = rule.evaluate(&null_inputs).unwrap();
                assert_eq!(excluded.payout, Payout::NotPayable);
                assert!(excluded.missing_inputs.is_empty());
                assert!(!excluded.trace.iter().any(|t| t.path.starts_with("amount")));
            }
        }
    }
}
