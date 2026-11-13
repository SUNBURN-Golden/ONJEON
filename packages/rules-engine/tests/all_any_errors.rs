//! Audits 2/3/4/6: a decisive all/any result must survive irrelevant child errors,
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

fn days_comparison(inclusive_start: bool, inclusive_end: bool) -> J {
    json!({"lt": [{"days_between": ["d", {"date": "1900-01-01"},
        {"inclusive_start": inclusive_start, "inclusive_end": inclusive_end}]}, 90]})
}

#[test]
fn reversed_days_between_errors_are_absorbed_only_by_input_decisions() {
    for schema in ["rule-0.1", "rule-0.2"] {
        for (op, decisive) in [("all", false), ("any", true)] {
            for inclusive_start in [false, true] {
                for inclusive_end in [false, true] {
                    for error_index in 0..2 {
                        let mut children = vec![json!("flag")];
                        children
                            .insert(error_index, days_comparison(inclusive_start, inclusive_end));
                        let r = versioned_rule(schema, json!({op: children}));
                        let failed_path = format!("eligibility.{op}[{error_index}]");
                        let expected_error = EvalError::Type {
                            path: format!("{failed_path}.lt[0]"),
                            message: "days_between needs the first date on or before the second, \
                                found the second 1 day(s) earlier; compare the dates with \
                                lt/gt instead"
                                .into(),
                        };
                        let data = json!({"d": "1900-01-02", "flag": decisive});
                        let result = r.evaluate(&data).unwrap();
                        assert_eq!(result.payout, expected_payout(decisive));
                        assert_eq!(
                            result.eligibility,
                            if decisive { Tri::True } else { Tri::False }
                        );
                        assert!(result.missing_inputs.is_empty());
                        let errors: Vec<_> = result
                            .trace
                            .iter()
                            .filter(|entry| entry.result.starts_with("error: "))
                            .collect();
                        assert_eq!(errors.len(), 1);
                        assert_eq!(errors[0].path, failed_path);
                        assert_eq!(errors[0].op, "lt");
                        assert_eq!(errors[0].result, format!("error: {expected_error}"));
                        assert!(!result
                            .trace
                            .iter()
                            .any(|entry| entry.path.starts_with(&format!("{failed_path}."))));
                        assert!(result.trace.iter().any(|entry| entry.path == "eligibility"
                            && entry.op == op
                            && entry.result == decisive.to_string()));
                        let reloaded = Rule::from_json_str(&r.source_json().to_string()).unwrap();
                        assert_eq!(
                            serde_json::to_vec(&result).unwrap(),
                            serde_json::to_vec(&reloaded.evaluate(&data).unwrap()).unwrap()
                        );

                        // A neutral or unknown input cannot settle the result. Keep
                        // the original reversed-date error, including its exact path.
                        for data in [
                            json!({"d": "1900-01-02", "flag": !decisive}),
                            json!({"d": "1900-01-02", "flag": null}),
                            json!({"d": "1900-01-02"}),
                        ] {
                            assert_eq!(r.evaluate(&data).unwrap_err(), expected_error);
                        }
                    }
                }
            }
        }
    }
}

#[test]
fn missing_date_blockers_survive_until_an_input_decides_all_any() {
    for schema in ["rule-0.1", "rule-0.2"] {
        for (op, decisive) in [("all", false), ("any", true)] {
            for inclusive_start in [false, true] {
                for inclusive_end in [false, true] {
                    for error_index in 0..2 {
                        let mut children = vec![json!("flag")];
                        children
                            .insert(error_index, days_comparison(inclusive_start, inclusive_end));
                        let r = versioned_rule(schema, json!({op: children}));
                        for (flag, missing) in [
                            (json!(decisive), vec![]),
                            (json!(!decisive), vec!["d"]),
                            (J::Null, vec!["d", "flag"]),
                        ] {
                            let data = json!({"flag": flag});
                            let result = r.evaluate(&data).unwrap();
                            assert_eq!(result.missing_inputs, missing);
                            if flag == json!(decisive) {
                                assert_eq!(
                                    result.eligibility,
                                    if decisive { Tri::True } else { Tri::False }
                                );
                                assert_eq!(result.payout, expected_payout(decisive));
                            } else {
                                assert_eq!(result.eligibility, Tri::Unknown);
                                assert_eq!(
                                    result.payout,
                                    Payout::Undetermined {
                                        conditional_amount: AmountOut::Exact { krw: 100 }
                                    }
                                );
                            }
                            assert!(!result
                                .trace
                                .iter()
                                .any(|entry| entry.result.starts_with("error: ")));
                            let mut null_data = data.clone();
                            null_data["d"] = J::Null;
                            assert_eq!(
                                serde_json::to_vec(&result).unwrap(),
                                serde_json::to_vec(&r.evaluate(&null_data).unwrap()).unwrap()
                            );
                            if flag.is_null() {
                                assert_eq!(
                                    serde_json::to_vec(&result).unwrap(),
                                    serde_json::to_vec(&r.evaluate(&json!({})).unwrap()).unwrap()
                                );
                            }
                        }
                    }
                }
            }
        }
    }
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

fn check_multiple_errors(has_decision: bool) {
    for schema in ["rule-0.1", "rule-0.2"] {
        for (op, decisive) in [("all", false), ("any", true)] {
            let failures = failing_children();
            for order in [
                [0, 1, 2],
                [0, 2, 1],
                [1, 0, 2],
                [1, 2, 0],
                [2, 0, 1],
                [2, 1, 0],
            ] {
                for position in 0..=4 {
                    let mut children = vec![json!("flag")];
                    children.extend(order.map(|i| failures[i].clone()));
                    children.insert(
                        position,
                        json!(if has_decision { decisive } else { !decisive }),
                    );
                    let r = versioned_rule(schema, json!({op: children}));
                    let mut null_inputs = inputs();
                    null_inputs["flag"] = J::Null;
                    for data in [inputs(), null_inputs] {
                        if has_decision {
                            let res = r.evaluate(&data).unwrap();
                            assert_eq!(
                                res.eligibility,
                                if decisive { Tri::True } else { Tri::False }
                            );
                            assert_eq!(res.payout, expected_payout(decisive));
                            assert!(res.missing_inputs.is_empty());
                            let errors: Vec<_> = res
                                .trace
                                .iter()
                                .filter(|t| t.result.starts_with("error: "))
                                .collect();
                            assert_eq!(errors.len(), 3);
                            for error in errors {
                                assert!(!res
                                    .trace
                                    .iter()
                                    .any(|t| t.path.starts_with(&format!("{}.", error.path))));
                            }
                            // Reloading and null/missing input representations preserve
                            // the entire result, including trace and both hashes.
                            let reloaded = Rule::from_json(r.source_json()).unwrap();
                            assert_eq!(
                                serde_json::to_vec(&res).unwrap(),
                                serde_json::to_vec(&reloaded.evaluate(&inputs()).unwrap()).unwrap()
                            );
                        } else {
                            // With only a neutral child, even an unknown sibling must
                            // preserve the first error's kind, message and expression path.
                            let original = versioned_rule(schema, failures[order[0]].clone())
                                .evaluate(&data)
                                .unwrap_err();
                            let first_error_index = if position <= 1 { 2 } else { 1 };
                            let expected = original.to_string().replacen(
                                "eligibility",
                                &format!("eligibility.{op}[{first_error_index}]"),
                                1,
                            );
                            assert_eq!(r.evaluate(&data).unwrap_err().to_string(), expected);
                        }
                    }
                }
            }
        }
    }
}

#[test]
fn multiple_errors_cannot_override_a_decisive_child_in_both_versions() {
    check_multiple_errors(true);
}

#[test]
fn multiple_errors_preserve_the_first_error_without_a_decision_in_both_versions() {
    check_multiple_errors(false);
}
