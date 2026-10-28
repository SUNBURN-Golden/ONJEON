//! Audits 2 and 3: a comparison must not load if either operand can produce a money range.
use onjeon_rules_engine::{AmountOut, Payout, Rule};
use serde_json::{json, Value as J};

const COMPARISONS: [&str; 6] = ["eq", "ne", "lt", "lte", "gt", "gte"];

fn rule(version: &str, eligibility: J, amount: J) -> J {
    json!({
        "rule_id": "range-comparison", "rule_version": "1", "schema_version": version,
        "calendar": "Asia/Seoul", "inputs": {"p": "money_krw", "flag": "bool"},
        "eligibility": eligibility, "amount": amount,
        "unknown_policy": "use_three_valued_logic_never_default_to_zero",
        "evidence_refs": [], "publication_state": "fixture_only"
    })
}

fn scaled(money: J, rounding: &str) -> J {
    json!({"multiply_rate": [money, "0.5", {"rounding": rounding, "unit": 1}]})
}

fn range() -> J {
    scaled(json!("p"), "unspecified")
}

fn assert_load_rejected(source: &J, path: &str) {
    // Exercise both public load boundaries; neither requires evaluation inputs.
    let text = serde_json::to_string(source).unwrap();
    for result in [Rule::from_json(source), Rule::from_json_str(&text)] {
        let err = result.expect_err("range comparison must fail at load");
        assert_eq!(err.path, path, "{source}");
        assert!(err.message.contains("money_range"), "{err}: {source}");
    }
}

fn assert_comparison_rejected(version: &str, expr: J) {
    for op in COMPARISONS {
        for operands in [
            json!([expr, {"krw": 100}]),
            json!([{"krw": 100}, expr]),
            json!([expr, expr]),
        ] {
            let source = rule(version, json!({op: operands}), json!({"krw": 1}));
            assert_load_rejected(&source, &format!("eligibility.{op}"));
        }
    }
}

#[test]
fn nested_and_unreachable_comparisons_fail_at_both_load_boundaries() {
    for version in ["rule-0.1", "rule-0.2"] {
        for op in COMPARISONS {
            for operands in [
                json!([range(), {"krw": 100}]),
                json!([{"krw": 100}, range()]),
                json!([range(), range()]),
            ] {
                let cmp = json!({op: operands});
                // Even a decisive sibling or a constant condition cannot bypass I5.
                for (eligibility, prefix) in [
                    (json!({"all": [false, cmp]}), "eligibility.all[1]"),
                    (json!({"any": [true, cmp]}), "eligibility.any[1]"),
                    (json!({"not": cmp}), "eligibility.not"),
                    (
                        json!({"if": false, "then": cmp, "else": true}),
                        "eligibility.then",
                    ),
                    (
                        json!({"if": true, "then": false, "else": cmp}),
                        "eligibility.else",
                    ),
                    (
                        json!({"if": cmp, "then": true, "else": false}),
                        "eligibility.if",
                    ),
                ] {
                    let source = rule(version, eligibility, json!({"krw": 1}));
                    assert_load_rejected(&source, &format!("{prefix}.{op}"));
                }
                let amount = json!({"if": false, "then": {"add": [
                    {"krw": 1}, {"if": cmp, "then": {"krw": 1}, "else": {"krw": 0}}
                ]}, "else": {"krw": 0}});
                let source = rule(version, json!(false), amount);
                assert_load_rejected(&source, &format!("amount.then.add[1].if.{op}"));
            }
        }
    }
}

fn assert_amount(version: &str, expr: J, inputs: J, amount: AmountOut) {
    let loaded = Rule::from_json(&rule(version, json!(true), expr)).unwrap();
    assert_eq!(
        loaded.evaluate(&inputs).unwrap().payout,
        Payout::Payable { amount }
    );
}

#[test]
fn audit_p201_is_rejected_before_input_dependent_failure() {
    // The same amount is exact for p=200 but a range for p=201.
    for version in ["rule-0.1", "rule-0.2"] {
        assert_amount(
            version,
            range(),
            json!({"p": 200}),
            AmountOut::Exact { krw: 100 },
        );
        assert_amount(
            version,
            range(),
            json!({"p": 201}),
            AmountOut::Range {
                min_krw: 100,
                max_krw: 101,
            },
        );
        assert_comparison_rejected(version, range());
    }
}

#[test]
fn ranges_propagate_through_every_v01_money_operator_and_if_branch() {
    let r = range();
    let expressions = [
        scaled(r.clone(), "floor"),
        json!({"add": [{"krw": 1}, {"krw": 2}, r]}),
        json!({"min": [{"krw": 500}, r]}),
        json!({"max": [r, {"krw": 1}]}),
        json!({"apply_cap": [r, {"krw": 500}]}),
        json!({"apply_cap": [{"krw": 500}, r]}),
        json!({"if": "flag", "then": r, "else": {"krw": 1}}),
        json!({"if": "flag", "then": {"krw": 1}, "else": r}),
        json!({"if": "flag", "then": r, "else": r}),
        json!({"add": [{"krw": 1}, {"if": "flag", "then": {"krw": 1}, "else": {
            "apply_cap": [{"max": [r, {"krw": 1}]}, {"krw": 500}]
        }}]}),
    ];
    for version in ["rule-0.1", "rule-0.2"] {
        for expr in &expressions {
            assert_comparison_rejected(version, expr.clone());
            // These expressions remain valid amount expressions, including mixed if branches.
            Rule::from_json(&rule(version, json!(true), expr.clone())).unwrap();
        }
    }
}

#[test]
fn v02_rounding_operators_introduce_ranges() {
    for expr in [
        json!({"divide_count": ["p", 2, {"rounding": "unspecified", "unit": 1}]}),
        json!({"pro_rata": ["p", 1, 2, {"rounding": "unspecified", "unit": 1}]}),
        json!({"pro_rata": ["p", {"krw": 1}, {"krw": 2}, {"rounding": "unspecified", "unit": 1}]}),
    ] {
        assert_amount(
            "rule-0.2",
            expr.clone(),
            json!({"p": 201}),
            AmountOut::Range {
                min_krw: 100,
                max_krw: 101,
            },
        );
        assert_comparison_rejected("rule-0.2", expr);
    }
}

#[test]
fn v02_money_operators_preserve_input_ranges_even_with_explicit_rounding() {
    let r = range();
    for expr in [
        json!({"multiply_count": [r, 2]}),
        json!({"subtract_floor0": [r, {"krw": 1}]}),
        json!({"subtract_floor0": [{"krw": 200}, r]}),
        json!({"pro_rata": [r, 1, 1, {"rounding": "floor", "unit": 1}]}),
        json!({"divide_count": [r, 1, {"rounding": "floor", "unit": 1}]}),
    ] {
        assert_comparison_rejected("rule-0.2", expr.clone());
        Rule::from_json(&rule("rule-0.2", json!(true), expr)).unwrap();
    }
}

#[test]
fn static_range_checks_do_not_depend_on_constant_values_or_reachable_branches() {
    for expr in [
        scaled(json!({"krw": 200}), "unspecified"),
        json!({"apply_cap": [range(), {"krw": 0}]}),
        json!({"multiply_rate": [range(), "0", {"rounding": "floor", "unit": 1}]}),
        json!({"if": false, "then": range(), "else": {"krw": 1}}),
        json!({"if": true, "then": {"krw": 1}, "else": range()}),
    ] {
        assert_comparison_rejected("rule-0.1", expr);
    }
    // A comparison hidden in an amount branch must also be checked at load.
    let source = rule(
        "rule-0.1",
        json!(true),
        json!({
            "if": false, "then": {"if": {"eq": [range(), {"krw": 100}]},
                "then": {"krw": 1}, "else": {"krw": 0}}, "else": {"krw": 0}
        }),
    );
    assert_eq!(
        Rule::from_json(&source).unwrap_err().path,
        "amount.then.if.eq"
    );
}

#[test]
fn exact_money_comparisons_still_load_and_evaluate_for_all_rounding_modes() {
    for version in ["rule-0.1", "rule-0.2"] {
        for rounding in ["floor", "ceil", "half_up", "half_even"] {
            let mut expressions = vec![
                json!("p"),
                json!({"input": "p"}),
                json!({"krw": 100}),
                scaled(json!("p"), rounding),
                json!({"add": [scaled(json!("p"), rounding), {"krw": 1}]}),
                json!({"min": ["p", {"krw": 100}]}),
                json!({"max": ["p", {"krw": 100}]}),
                json!({"apply_cap": ["p", {"krw": 100}]}),
                json!({"if": "flag", "then": "p", "else": {"krw": 100}}),
            ];
            if version == "rule-0.2" {
                expressions.extend([
                    json!({"multiply_count": ["p", 2]}),
                    json!({"subtract_floor0": ["p", {"krw": 1}]}),
                    json!({"pro_rata": ["p", 1, 2, {"rounding": rounding, "unit": 1}]}),
                    json!({"divide_count": ["p", 2, {"rounding": rounding, "unit": 1}]}),
                ]);
            }
            for expr in expressions {
                for op in COMPARISONS {
                    let loaded = Rule::from_json(&rule(
                        version,
                        json!({op: [expr, expr]}),
                        json!({"krw": 1}),
                    ))
                    .unwrap();
                    let result = loaded.evaluate(&json!({"p": 201, "flag": true})).unwrap();
                    let expected = if ["eq", "lte", "gte"].contains(&op) {
                        Payout::Payable {
                            amount: AmountOut::Exact { krw: 1 },
                        }
                    } else {
                        Payout::NotPayable
                    };
                    assert_eq!(
                        result.payout, expected,
                        "{version}: {rounding}: {op}: {expr}"
                    );
                }
            }
        }
    }
}

#[test]
fn exact_money_threshold_comparisons_preserve_order_and_missing_inputs() {
    for version in ["rule-0.1", "rule-0.2"] {
        for rounding in ["floor", "ceil", "half_up", "half_even"] {
            for op in COMPARISONS {
                let source = rule(
                    version,
                    json!({op: [scaled(json!("p"), rounding), {"krw": 100}]}),
                    json!({"krw": 1}),
                );
                let loaded = Rule::from_json_str(&serde_json::to_string(&source).unwrap()).unwrap();
                // Below, at, and above the threshold, independent of tie rounding.
                for (p, expected_ops) in [
                    (198, ["ne", "lt", "lte"]),
                    (200, ["eq", "lte", "gte"]),
                    (202, ["ne", "gt", "gte"]),
                ] {
                    let expected = if expected_ops.contains(&op) {
                        Payout::Payable {
                            amount: AmountOut::Exact { krw: 1 },
                        }
                    } else {
                        Payout::NotPayable
                    };
                    assert_eq!(
                        loaded.evaluate(&json!({"p": p})).unwrap().payout,
                        expected,
                        "{version}: {rounding}: {op}: p={p}"
                    );
                }
                for inputs in [json!({}), json!({"p": null})] {
                    let result = loaded.evaluate(&inputs).unwrap();
                    assert_eq!(
                        result.payout,
                        Payout::Undetermined {
                            conditional_amount: AmountOut::Exact { krw: 1 }
                        }
                    );
                    assert_eq!(result.missing_inputs, vec!["p"]);
                }
            }
        }
    }
}

#[test]
fn mixed_exact_and_range_if_amounts_keep_runtime_results_and_unknowns() {
    for (then, els, range_flag) in [
        (range(), json!({"krw": 1}), true),
        (json!({"krw": 1}), range(), false),
    ] {
        let expr = json!({"if": "flag", "then": then, "else": els});
        for version in ["rule-0.1", "rule-0.2"] {
            assert_amount(
                version,
                expr.clone(),
                json!({"p": 201, "flag": range_flag}),
                AmountOut::Range {
                    min_krw: 100,
                    max_krw: 101,
                },
            );
            assert_amount(
                version,
                expr.clone(),
                json!({"p": 201, "flag": !range_flag}),
                AmountOut::Exact { krw: 1 },
            );
            let loaded = Rule::from_json(&rule(version, json!(true), expr.clone())).unwrap();
            let result = loaded.evaluate(&json!({"p": 201})).unwrap();
            assert_eq!(
                result.payout,
                Payout::Payable {
                    amount: AmountOut::Unknown
                }
            );
            assert_eq!(result.missing_inputs, vec!["flag"]);
        }
    }
}

#[test]
fn pro_rata_ratio_operands_still_require_exact_money() {
    // The finer money type also enforces this existing runtime restriction at load.
    for (part, whole) in [
        (range(), json!({"krw": 500})),
        (json!({"krw": 1}), range()),
        (range(), range()),
    ] {
        let source = rule(
            "rule-0.2",
            json!(true),
            json!({
                "pro_rata": ["p", part, whole, {"rounding": "floor", "unit": 1}]
            }),
        );
        let err = Rule::from_json(&source).unwrap_err();
        assert_eq!(err.path, "amount.pro_rata");
        assert!(err.message.contains("money_range"), "{err}");
    }
}
