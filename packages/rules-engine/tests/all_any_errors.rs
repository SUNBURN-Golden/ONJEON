//! Audits 2/3: a decisive all/any result must survive an irrelevant child error,
//! independently of child order. Errors that can still affect the answer remain errors.
use onjeon_rules_engine::{AmountOut, EvalError, Payout, Rule, Tri};
use serde_json::{json, Value as J};

fn rule(op: &str, children: Vec<J>) -> Rule {
    versioned_rule("rule-0.1", json!({op: children}))
}

fn versioned_rule(schema: &str, eligibility: J) -> Rule {
    Rule::from_json(&json!({
        "rule_id": "all-any-errors", "rule_version": "1", "schema_version": schema,
        "calendar": "Asia/Seoul", "publication_state": "fixture_only", "evidence_refs": [],
        "inputs": {"flag": "bool", "other": "bool", "d": "date", "amt": "money_krw"},
        "eligibility": eligibility, "amount": {"krw": 100},
        "unknown_policy": "use_three_valued_logic_never_default_to_zero"
    }))
    .unwrap()
}

fn failing_children() -> Vec<J> {
    vec![
        json!({"eq": [{"date_add": ["d", {"value": 1, "unit": "day"}]}, "d"]}),
        json!({"eq": [{"add": ["amt", {"krw": 1}]}, {"krw": 1}]}),
        // Reversed dates remain a runtime Type error. Range comparisons are now
        // rejected at load (covered by range_comparisons), so cannot be used here.
        json!({"lt": [{"days_between": ["d", {"date": "1900-01-01"},
            {"inclusive_start": true, "inclusive_end": true}]}, 3]}),
    ]
}

fn inputs() -> J {
    json!({"d": "2199-12-31", "amt": i64::MAX})
}

fn expected_payout(decisive: bool) -> Payout {
    if decisive {
        Payout::Payable {
            amount: AmountOut::Exact { krw: 100 },
        }
    } else {
        Payout::NotPayable
    }
}

fn check_decisive_pairs(op: &str, decisive: bool) {
    for schema in ["rule-0.1", "rule-0.2"] {
        for bad in failing_children() {
            for children in [
                vec![json!(decisive), bad.clone()],
                vec![bad, json!(decisive)],
            ] {
                let r = versioned_rule(schema, json!({op: children}));
                let res = r.evaluate(&inputs()).unwrap();
                assert_eq!(
                    res.eligibility,
                    if decisive { Tri::True } else { Tri::False }
                );
                assert_eq!(res.payout, expected_payout(decisive));
                assert!(res.missing_inputs.is_empty());
                // Deferred errors remain observable in either position, even after
                // a decisive child. The public trace contract evaluates every child.
                assert_eq!(
                    res.trace
                        .iter()
                        .filter(|t| t.result.starts_with("error: "))
                        .count(),
                    1
                );
                assert_eq!(
                    serde_json::to_vec(&res).unwrap(),
                    serde_json::to_vec(&r.evaluate(&inputs()).unwrap()).unwrap()
                );
            }
        }
    }
}

#[test]
fn all_false_absorbs_runtime_errors_in_both_versions() {
    check_decisive_pairs("all", false);
}

#[test]
fn any_true_absorbs_runtime_errors_in_both_versions() {
    check_decisive_pairs("any", true);
}

#[test]
fn nested_all_any_and_if_keep_decisions_and_relevant_errors() {
    for schema in ["rule-0.1", "rule-0.2"] {
        for (op, other_op, decisive) in [("all", "any", false), ("any", "all", true)] {
            for bad in failing_children() {
                // The inner expression fails without its own decisive child.
                let failing = json!({other_op: [bad.clone(), decisive]});
                let err = versioned_rule(schema, failing.clone())
                    .evaluate(&inputs())
                    .unwrap_err();
                for children in [
                    vec![json!(decisive), failing.clone()],
                    vec![failing.clone(), json!(decisive)],
                ] {
                    let res = versioned_rule(schema, json!({op: children}))
                        .evaluate(&inputs())
                        .unwrap();
                    assert_eq!(res.payout, expected_payout(decisive));
                    assert!(res.missing_inputs.is_empty());
                    assert_eq!(
                        res.trace
                            .iter()
                            .filter(|t| t.result.starts_with("error: "))
                            .count(),
                        1
                    );
                }

                // Both branches agree once all/any absorbs the irrelevant error.
                // An unknown condition must therefore stop blocking the answer.
                let branch = json!({op: [bad, decisive]});
                let res = versioned_rule(
                    schema,
                    json!({"if": "flag", "then": branch, "else": decisive}),
                )
                .evaluate(&inputs())
                .unwrap();
                assert_eq!(res.payout, expected_payout(decisive));
                assert!(res.missing_inputs.is_empty());

                // A selected failing branch still propagates the original error.
                let mut selected_inputs = inputs();
                selected_inputs["flag"] = json!(true);
                let selected = versioned_rule(
                    schema,
                    json!({"if": "flag", "then": failing, "else": decisive}),
                )
                .evaluate(&selected_inputs)
                .unwrap_err();
                assert_eq!(
                    selected.to_string(),
                    err.to_string()
                        .replacen("eligibility", "eligibility.then", 1)
                );
            }
        }
    }
}

#[test]
fn decisive_result_wins_over_errors_and_unknowns_in_every_child_order() {
    for (op, decisive) in [("all", false), ("any", true)] {
        for bad in failing_children() {
            let children = [json!(decisive), bad, json!("flag")];
            for order in [
                [0, 1, 2],
                [0, 2, 1],
                [1, 0, 2],
                [1, 2, 0],
                [2, 0, 1],
                [2, 1, 0],
            ] {
                let r = rule(op, order.map(|i| children[i].clone()).to_vec());
                let res = r.evaluate(&inputs()).unwrap();
                assert_eq!(
                    res.eligibility,
                    if decisive { Tri::True } else { Tri::False }
                );
                assert_eq!(res.payout, expected_payout(decisive));
                assert!(res.missing_inputs.is_empty());
            }
        }
    }
}

#[test]
fn errors_are_preserved_without_a_decisive_child() {
    for (op, neutral) in [("all", true), ("any", false)] {
        for (kind, bad) in failing_children().into_iter().enumerate() {
            for children in [
                vec![json!(neutral), bad.clone()],
                vec![bad.clone(), json!(neutral)],
                vec![json!("flag"), bad.clone()],
                vec![bad.clone(), json!("flag")],
                vec![bad.clone(), bad.clone()],
                vec![bad],
            ] {
                let err = rule(op, children).evaluate(&inputs()).unwrap_err();
                assert!(
                    matches!(
                        (kind, &err),
                        (0, EvalError::DateOutOfRange { .. })
                            | (1, EvalError::Overflow { .. })
                            | (2, EvalError::Type { .. })
                    ),
                    "{op}: unexpected error {err:?}"
                );
            }
        }
        let err = rule(op, failing_children())
            .evaluate(&inputs())
            .unwrap_err();
        assert_eq!(
            err,
            EvalError::DateOutOfRange {
                path: format!("eligibility.{op}[0].eq[0]")
            }
        );
    }
}

#[test]
fn unknown_children_keep_their_blockers_without_defaulting_to_a_decision() {
    for (op, neutral) in [("all", true), ("any", false)] {
        let res = rule(op, vec![json!(neutral), json!("other"), json!("flag")])
            .evaluate(&json!({}))
            .unwrap();
        assert_eq!(res.eligibility, Tri::Unknown);
        assert_eq!(res.missing_inputs, vec!["flag", "other"]);
        assert_eq!(
            res.payout,
            Payout::Undetermined {
                conditional_amount: AmountOut::Exact { krw: 100 }
            }
        );
    }
}

#[test]
fn absorbed_errors_have_deterministic_trace_entries_without_partial_children() {
    for (op, decisive) in [("all", false), ("any", true)] {
        let r = rule(op, vec![failing_children()[0].clone(), json!(decisive)]);
        let res = r.evaluate(&inputs()).unwrap();
        assert_eq!(
            serde_json::to_vec(&res).unwrap(),
            serde_json::to_vec(&r.evaluate(&inputs()).unwrap()).unwrap()
        );
        let failed_path = format!("eligibility.{op}[0]");
        let entry = res.trace.iter().find(|t| t.path == failed_path).unwrap();
        assert_eq!(entry.op, "eq");
        assert_eq!(
            entry.result,
            format!(
            "error: date outside the supported range 1900-01-01..2199-12-31 at {failed_path}.eq[0]"
        )
        );
        assert!(!res
            .trace
            .iter()
            .any(|t| t.path.starts_with(&format!("{failed_path}."))));
        assert!(res
            .trace
            .iter()
            .any(|t| t.path == "eligibility" && t.op == op && t.result == decisive.to_string()));
    }
}
