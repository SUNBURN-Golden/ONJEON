//! rule-0.2 operators (GAP_REPORT section 5): golden, boundary, mutation and soundness tests.
//! Every rule here is synthetic (`fixture_only`); none encodes a real clause.

use onjeon_rules_engine::{AmountOut, ContractEffect, ContractEffectOut, Payout, Rule, Tri};
use serde_json::{json, Value as J};

/// A synthetic rule-0.2 document around one amount expression.
fn doc(inputs: J, amount: J) -> J {
    json!({
        "rule_id": "fixture-rule-02", "rule_version": "1", "schema_version": "rule-0.2",
        "inputs": inputs, "eligibility": true, "amount": amount,
        "unknown_policy": "use_three_valued_logic_never_default_to_zero",
        "evidence_refs": [], "publication_state": "fixture_only"
    })
}

fn load(d: &J) -> Rule {
    Rule::from_json(d).unwrap_or_else(|e| panic!("rule must load: {e}"))
}

fn amount(rule: &Rule, inputs: J) -> AmountOut {
    match rule.evaluate(&inputs).expect("evaluates").payout {
        Payout::Payable { amount } => amount,
        other => panic!("expected payable, got {other:?}"),
    }
}

fn exact(krw: i64) -> AmountOut {
    AmountOut::Exact { krw }
}

fn load_err(d: &J) -> String {
    Rule::from_json(d)
        .expect_err("must be rejected")
        .to_string()
}

fn eval_err(rule: &Rule, inputs: J) -> String {
    rule.evaluate(&inputs)
        .expect_err("must be an error")
        .to_string()
}

// ---------------------------------------------------------------- loader gating

#[test]
fn rule_01_documents_cannot_use_rule_02_features() {
    let mut d = doc(
        json!({"a": "money_krw", "n": "int"}),
        json!({"multiply_count": ["a", "n"]}),
    );
    d["schema_version"] = json!("rule-0.1");
    assert!(load_err(&d).contains("requires schema_version rule-0.2"));
    for amt in [
        json!({"subtract_floor0": ["a", "a"]}),
        json!({"pro_rata": ["a", "n", "n", {"rounding": "floor", "unit": 1}]}),
        json!({"divide_count": ["a", "n", {"rounding": "floor", "unit": 1}]}),
    ] {
        let mut d = doc(json!({"a": "money_krw", "n": "int"}), amt);
        d["schema_version"] = json!("rule-0.1");
        assert!(load_err(&d).contains("rule-0.2"), "{d}");
    }
    let mut d = doc(json!({"l": "class_money_list"}), json!({"max_over": "l"}));
    d["schema_version"] = json!("rule-0.1");
    assert!(load_err(&d).contains("class_money_list"));
    let mut d = doc(json!({}), json!({"krw": 1}));
    d["schema_version"] = json!("rule-0.1");
    d["contract_effect"] = json!("none");
    assert!(load_err(&d).contains("contract_effect"));
    d["schema_version"] = json!("rule-0.3");
    assert!(load_err(&d).contains("rule-0.1 or rule-0.2"));
}

#[test]
fn rule_01_results_report_no_contract_effect() {
    let mut d = doc(json!({}), json!({"krw": 5}));
    d["schema_version"] = json!("rule-0.1");
    let r = load(&d).evaluate(&json!({})).unwrap();
    assert_eq!(r.contract_effect, ContractEffectOut::None);
    assert_eq!(r.schema_version, "rule-0.1");
}

// ---------------------------------------------------------------- multiply_count

fn multiply_count_rule() -> Rule {
    load(&doc(
        json!({"daily": "money_krw", "days": "int"}),
        json!({"multiply_count": ["daily", "days"]}),
    ))
}

#[test]
fn multiply_count_golden_and_boundaries() {
    let r = multiply_count_rule();
    assert_eq!(amount(&r, json!({"daily": 10000, "days": 3})), exact(30000));
    assert_eq!(amount(&r, json!({"daily": 10000, "days": 0})), exact(0));
    assert_eq!(amount(&r, json!({"daily": 0, "days": 5})), exact(0));
    assert_eq!(
        amount(&r, json!({"daily": i64::MAX, "days": 1})),
        exact(i64::MAX)
    );
    assert!(eval_err(&r, json!({"daily": i64::MAX, "days": 2})).contains("overflow"));
    assert!(eval_err(&r, json!({"daily": 1, "days": -1})).contains("count must be >= 0"));
}

#[test]
fn multiply_count_unknown_is_never_zero() {
    let r = multiply_count_rule();
    let out = r.evaluate(&json!({"daily": 10000})).unwrap();
    assert_eq!(
        out.payout,
        Payout::Payable {
            amount: AmountOut::Unknown
        }
    );
    assert_eq!(out.missing_inputs, ["days"]);
    let out = r.evaluate(&json!({"days": 0})).unwrap();
    assert_eq!(
        out.payout,
        Payout::Payable {
            amount: AmountOut::Unknown
        }
    );
    assert_eq!(out.missing_inputs, ["daily"]);
}

#[test]
fn multiply_count_keeps_ranges() {
    let r = load(&doc(
        json!({"a": "money_krw", "n": "int"}),
        json!({"multiply_count": [{"multiply_rate": ["a", "0.5", {"rounding": "unspecified", "unit": 1}]}, "n"]}),
    ));
    // 5 * 0.5 = 2.5 -> [2, 3]; times 4 -> [8, 12]
    assert_eq!(
        amount(&r, json!({"a": 5, "n": 4})),
        AmountOut::Range {
            min_krw: 8,
            max_krw: 12
        }
    );
}

#[test]
fn multiply_count_type_checks_at_load() {
    assert!(load_err(&doc(
        json!({"a": "money_krw"}),
        json!({"multiply_count": ["a", "0.5"]})
    ))
    .contains("expected int"));
    assert!(load_err(&doc(
        json!({"a": "money_krw"}),
        json!({"multiply_count": [3, 3]})
    ))
    .contains("expected money"));
}

// ---------------------------------------------------------------- subtract_floor0

fn subtract_rule() -> Rule {
    load(&doc(
        json!({"a": "money_krw", "b": "money_krw"}),
        json!({"subtract_floor0": ["a", "b"]}),
    ))
}

#[test]
fn subtract_floor0_golden_and_boundaries() {
    let r = subtract_rule();
    assert_eq!(amount(&r, json!({"a": 100, "b": 30})), exact(70));
    assert_eq!(amount(&r, json!({"a": 100, "b": 100})), exact(0));
    assert_eq!(amount(&r, json!({"a": 100, "b": 101})), exact(0));
    assert_eq!(amount(&r, json!({"a": 0, "b": i64::MAX})), exact(0));
    assert_eq!(amount(&r, json!({"a": i64::MAX, "b": 0})), exact(i64::MAX));
}

#[test]
fn subtract_floor0_unknown_is_not_floored_to_zero() {
    let r = subtract_rule();
    // The floor must never turn a missing deduction into "nothing left" or "everything left".
    for inputs in [json!({"a": 100}), json!({"b": 100}), json!({})] {
        let out = r.evaluate(&inputs).unwrap();
        assert_eq!(
            out.payout,
            Payout::Payable {
                amount: AmountOut::Unknown
            },
            "{inputs}"
        );
        assert!(!out.missing_inputs.is_empty());
    }
}

#[test]
fn subtract_floor0_range_bounds_are_conservative() {
    let r = load(&doc(
        json!({"a": "money_krw", "b": "money_krw"}),
        json!({"subtract_floor0": [
            {"multiply_rate": ["a", "0.5", {"rounding": "unspecified", "unit": 1}]},
            {"multiply_rate": ["b", "0.5", {"rounding": "unspecified", "unit": 1}]}]}),
    ));
    // a=5 -> [2,3]; b=3 -> [1,2]; lo = 2-2 = 0, hi = 3-1 = 2
    assert_eq!(
        amount(&r, json!({"a": 5, "b": 3})),
        AmountOut::Range {
            min_krw: 0,
            max_krw: 2
        }
    );
}

// ---------------------------------------------------------------- pro_rata

fn pro_rata_rule(rounding: &str, unit: i64) -> Rule {
    load(&doc(
        json!({"loss": "money_krw", "mine": "money_krw", "all": "money_krw"}),
        json!({"pro_rata": ["loss", "mine", "all", {"rounding": rounding, "unit": unit}]}),
    ))
}

#[test]
fn pro_rata_golden_and_rounding() {
    // 100 * 1/3 = 33.33..; 100 * 2/3 = 66.66..
    let cases = [
        ("floor", 1, 1, 33),
        ("ceil", 1, 1, 34),
        ("half_up", 1, 1, 33),
        ("floor", 1, 2, 66),
        ("ceil", 1, 2, 67),
        ("half_up", 1, 2, 67),
        ("half_even", 1, 2, 67),
        ("floor", 10, 2, 60),
        ("ceil", 10, 2, 70),
    ];
    for (rounding, unit, mine, want) in cases {
        let r = pro_rata_rule(rounding, unit);
        assert_eq!(
            amount(&r, json!({"loss": 100, "mine": mine, "all": 3})),
            exact(want),
            "{rounding}/{unit}/{mine}"
        );
    }
    // half_even on an exact tie: 5/2 = 2.5 -> 2, 7/2 = 3.5 -> 4
    let r = pro_rata_rule("half_even", 1);
    assert_eq!(
        amount(&r, json!({"loss": 5, "mine": 1, "all": 2})),
        exact(2)
    );
    assert_eq!(
        amount(&r, json!({"loss": 7, "mine": 1, "all": 2})),
        exact(4)
    );
    // unspecified rounding yields the [floor, ceil] range
    let r = pro_rata_rule("unspecified", 1);
    assert_eq!(
        amount(&r, json!({"loss": 100, "mine": 1, "all": 3})),
        AmountOut::Range {
            min_krw: 33,
            max_krw: 34
        }
    );
}

#[test]
fn pro_rata_boundaries() {
    let r = pro_rata_rule("floor", 1);
    assert_eq!(
        amount(&r, json!({"loss": 100, "mine": 0, "all": 3})),
        exact(0)
    );
    assert_eq!(
        amount(&r, json!({"loss": 100, "mine": 3, "all": 3})),
        exact(100)
    );
    assert_eq!(
        amount(&r, json!({"loss": 0, "mine": 1, "all": 3})),
        exact(0)
    );
    assert_eq!(
        amount(
            &r,
            json!({"loss": i64::MAX, "mine": i64::MAX, "all": i64::MAX})
        ),
        exact(i64::MAX)
    );
    assert!(eval_err(&r, json!({"loss": 100, "mine": 4, "all": 3})).contains("exceeds whole"));
}

#[test]
fn pro_rata_whole_zero_is_unknown_not_error_not_zero() {
    for rounding in ["floor", "ceil", "half_up", "half_even", "unspecified"] {
        let r = pro_rata_rule(rounding, 1);
        for mine in [0, 5] {
            let out = r
                .evaluate(&json!({"loss": 100, "mine": mine, "all": 0}))
                .unwrap();
            assert_eq!(
                out.payout,
                Payout::Payable {
                    amount: AmountOut::Unknown
                },
                "{rounding}/{mine}"
            );
            assert_eq!(out.eligibility, Tri::True);
            assert!(out
                .trace
                .iter()
                .any(|t| t.op == "pro_rata" && t.result == "unknown"));
        }
    }
    // whole = 0 inside a larger expression stays unknown instead of being absorbed as 0
    let r = load(&doc(
        json!({"loss": "money_krw", "mine": "money_krw", "all": "money_krw"}),
        json!({"add": [{"pro_rata": ["loss", "mine", "all", {"rounding": "floor", "unit": 1}]}, {"krw": 7}]}),
    ));
    assert_eq!(
        amount(&r, json!({"loss": 100, "mine": 1, "all": 0})),
        AmountOut::Unknown
    );
    let r = load(&doc(
        json!({"loss": "money_krw", "mine": "money_krw", "all": "money_krw"}),
        json!({"max": [{"pro_rata": ["loss", "mine", "all", {"rounding": "floor", "unit": 1}]}, {"krw": 7}]}),
    ));
    assert_eq!(
        amount(&r, json!({"loss": 100, "mine": 1, "all": 0})),
        AmountOut::Unknown
    );
}

#[test]
fn pro_rata_unknown_inputs_block() {
    let r = pro_rata_rule("floor", 1);
    for (inputs, blocked) in [
        (json!({"mine": 1, "all": 3}), vec!["loss"]),
        (json!({"loss": 100, "all": 3}), vec!["mine"]),
        (json!({"loss": 100, "mine": 1}), vec!["all"]),
        (json!({}), vec!["all", "loss", "mine"]),
    ] {
        let out = r.evaluate(&inputs).unwrap();
        assert_eq!(
            out.payout,
            Payout::Payable {
                amount: AmountOut::Unknown
            }
        );
        assert_eq!(out.missing_inputs, blocked);
    }
}

#[test]
fn pro_rata_accepts_int_parts_and_rejects_mixed_types() {
    let r = load(&doc(
        json!({"loss": "money_krw", "n": "int", "total": "int"}),
        json!({"pro_rata": ["loss", "n", "total", {"rounding": "floor", "unit": 1}]}),
    ));
    assert_eq!(
        amount(&r, json!({"loss": 90, "n": 1, "total": 3})),
        exact(30)
    );
    assert!(eval_err(&r, json!({"loss": 90, "n": -1, "total": 3})).contains("non-negative"));
    let bad = doc(
        json!({"loss": "money_krw", "n": "int", "m": "money_krw"}),
        json!({"pro_rata": ["loss", "n", "m", {"rounding": "floor", "unit": 1}]}),
    );
    assert!(load_err(&bad).contains("both be int or both be money"));
}

#[test]
fn pro_rata_requires_explicit_rounding() {
    let bad = doc(
        json!({"a": "money_krw"}),
        json!({"pro_rata": ["a", "a", "a", {"unit": 1}]}),
    );
    assert!(load_err(&bad).contains("rounding is required"));
    let bad = doc(
        json!({"a": "money_krw"}),
        json!({"pro_rata": ["a", "a", "a", {"rounding": "floor"}]}),
    );
    assert!(load_err(&bad).contains("unit is required"));
    let bad = doc(
        json!({"a": "money_krw"}),
        json!({"pro_rata": ["a", "a", "a", {"rounding": "floor", "unit": 1, "extra": 1}]}),
    );
    assert!(load_err(&bad).contains("only rounding and unit"));
}

#[test]
fn pro_rata_applies_to_ranges() {
    let r = load(&doc(
        json!({"a": "money_krw", "mine": "money_krw", "all": "money_krw"}),
        json!({"pro_rata": [
            {"multiply_rate": ["a", "0.5", {"rounding": "unspecified", "unit": 1}]},
            "mine", "all", {"rounding": "floor", "unit": 1}]}),
    ));
    // a=5 -> [2,3]; *1/1 -> [2,3]; a=5, 1/2 -> [1,1]
    assert_eq!(
        amount(&r, json!({"a": 5, "mine": 1, "all": 1})),
        AmountOut::Range {
            min_krw: 2,
            max_krw: 3
        }
    );
    assert_eq!(amount(&r, json!({"a": 5, "mine": 1, "all": 2})), exact(1));
}

// ---------------------------------------------------------------- divide_count

fn divide_rule(rounding: &str, unit: i64) -> Rule {
    load(&doc(
        json!({"total": "money_krw", "n": "int"}),
        json!({"divide_count": ["total", "n", {"rounding": rounding, "unit": unit}]}),
    ))
}

#[test]
fn divide_count_golden_and_boundaries() {
    let cases = [
        ("floor", 1, 100, 3, 33),
        ("ceil", 1, 100, 3, 34),
        ("half_up", 1, 100, 3, 33),
        ("half_up", 1, 101, 2, 51),
        ("half_even", 1, 101, 2, 50),
        ("half_even", 1, 103, 2, 52),
        ("floor", 100, 1000, 3, 300),
        ("ceil", 100, 1000, 3, 400),
        ("floor", 1, 100, 1, 100),
        ("floor", 1, 0, 5, 0),
    ];
    for (rounding, unit, total, n, want) in cases {
        let r = divide_rule(rounding, unit);
        assert_eq!(
            amount(&r, json!({"total": total, "n": n})),
            exact(want),
            "{rounding}/{unit}/{total}/{n}"
        );
    }
    let r = divide_rule("unspecified", 1);
    assert_eq!(
        amount(&r, json!({"total": 100, "n": 3})),
        AmountOut::Range {
            min_krw: 33,
            max_krw: 34
        }
    );
    assert_eq!(amount(&r, json!({"total": 99, "n": 3})), exact(33));
    assert!(
        eval_err(&divide_rule("floor", 1), json!({"total": 1, "n": -2}))
            .contains("count must be >= 0")
    );
}

#[test]
fn divide_count_zero_count_is_unknown() {
    for rounding in ["floor", "ceil", "half_up", "half_even", "unspecified"] {
        let out = divide_rule(rounding, 1)
            .evaluate(&json!({"total": 100, "n": 0}))
            .unwrap();
        assert_eq!(
            out.payout,
            Payout::Payable {
                amount: AmountOut::Unknown
            },
            "{rounding}"
        );
    }
}

#[test]
fn divide_count_unknown_inputs_block() {
    let r = divide_rule("floor", 1);
    let out = r.evaluate(&json!({"total": 100})).unwrap();
    assert_eq!(
        out.payout,
        Payout::Payable {
            amount: AmountOut::Unknown
        }
    );
    assert_eq!(out.missing_inputs, ["n"]);
    let out = r.evaluate(&json!({"n": 2})).unwrap();
    assert_eq!(out.missing_inputs, ["total"]);
}

#[test]
fn divide_count_rounds_the_bounds_of_a_range() {
    let r = load(&doc(
        json!({"a": "money_krw", "n": "int"}),
        json!({"divide_count": [
            {"multiply_rate": ["a", "0.5", {"rounding": "unspecified", "unit": 1}]},
            "n", {"rounding": "floor", "unit": 1}]}),
    ));
    // a=5 -> [2,3]; /2 floor -> [1,1]; /1 -> [2,3]
    assert_eq!(amount(&r, json!({"a": 5, "n": 2})), exact(1));
    assert_eq!(
        amount(&r, json!({"a": 5, "n": 1})),
        AmountOut::Range {
            min_krw: 2,
            max_krw: 3
        }
    );
}

// ---------------------------------------------------------------- anniversary_band

fn band_rule(boundary: &str) -> Rule {
    load(&doc(
        json!({"start": "date", "at": "date"}),
        json!({"multiply_rate": [
            {"krw": 1000000},
            {"anniversary_band": ["start", "at", [[0, "0.5"], [1, "0.6"], [10, "1.5"]], {"boundary": boundary}]},
            {"rounding": "floor", "unit": 1}]}),
    ))
}

fn band_at(rule: &Rule, start: &str, at: &str) -> AmountOut {
    amount(rule, json!({"start": start, "at": at}))
}

#[test]
fn anniversary_band_lower_inclusive_boundaries() {
    let r = band_rule("lower_inclusive");
    assert_eq!(band_at(&r, "2020-03-15", "2020-03-15"), exact(500000));
    assert_eq!(band_at(&r, "2020-03-15", "2021-03-14"), exact(500000));
    assert_eq!(band_at(&r, "2020-03-15", "2021-03-15"), exact(600000)); // anniversary day belongs to the new band
    assert_eq!(band_at(&r, "2020-03-15", "2021-03-16"), exact(600000));
    assert_eq!(band_at(&r, "2020-03-15", "2030-03-14"), exact(600000));
    assert_eq!(band_at(&r, "2020-03-15", "2030-03-15"), exact(1500000));
    assert_eq!(band_at(&r, "2020-03-15", "2150-01-01"), exact(1500000));
}

#[test]
fn anniversary_band_upper_inclusive_boundaries() {
    let r = band_rule("upper_inclusive");
    assert_eq!(band_at(&r, "2020-03-15", "2020-03-15"), exact(500000)); // day 0 is the base band
    assert_eq!(band_at(&r, "2020-03-15", "2021-03-14"), exact(500000));
    assert_eq!(band_at(&r, "2020-03-15", "2021-03-15"), exact(500000)); // anniversary day still old band
    assert_eq!(band_at(&r, "2020-03-15", "2021-03-16"), exact(600000));
    assert_eq!(band_at(&r, "2020-03-15", "2030-03-15"), exact(600000));
    assert_eq!(band_at(&r, "2020-03-15", "2030-03-16"), exact(1500000));
}

#[test]
fn anniversary_band_leap_day_anniversary_is_the_last_day_of_february() {
    let r = band_rule("lower_inclusive");
    assert_eq!(band_at(&r, "2020-02-29", "2021-02-27"), exact(500000));
    assert_eq!(band_at(&r, "2020-02-29", "2021-02-28"), exact(600000));
    assert_eq!(band_at(&r, "2020-02-29", "2021-03-01"), exact(600000));
    // 2024 has a real Feb 29: the anniversary is that day, Feb 28 is still before it
    assert_eq!(band_at(&r, "2020-02-29", "2024-02-28"), exact(600000));
    let two_year = load(&doc(
        json!({"start": "date", "at": "date"}),
        json!({"multiply_rate": [{"krw": 1000},
            {"anniversary_band": ["start", "at", [[0, "1"], [4, "2"]], {"boundary": "lower_inclusive"}]},
            {"rounding": "floor", "unit": 1}]}),
    ));
    assert_eq!(band_at(&two_year, "2020-02-29", "2024-02-28"), exact(1000));
    assert_eq!(band_at(&two_year, "2020-02-29", "2024-02-29"), exact(2000));
}

#[test]
fn anniversary_band_rejects_reversed_dates_and_propagates_unknown() {
    let r = band_rule("lower_inclusive");
    assert!(
        eval_err(&r, json!({"start": "2020-03-15", "at": "2020-03-14"})).contains("on or after")
    );
    for inputs in [
        json!({"start": "2020-03-15"}),
        json!({"at": "2020-03-15"}),
        json!({}),
    ] {
        let out = r.evaluate(&inputs).unwrap();
        assert_eq!(
            out.payout,
            Payout::Payable {
                amount: AmountOut::Unknown
            },
            "{inputs}"
        );
        assert!(!out.missing_inputs.is_empty());
    }
}

#[test]
fn anniversary_band_table_is_validated_at_load() {
    let mk = |table: J, boundary: J| {
        doc(
            json!({"s": "date", "a": "date"}),
            json!({"multiply_rate": [{"krw": 10}, {"anniversary_band": ["s", "a", table, boundary]},
                {"rounding": "floor", "unit": 1}]}),
        )
    };
    let ok = json!({"boundary": "lower_inclusive"});
    assert!(load_err(&mk(json!([]), ok.clone())).contains("1..=64 bands"));
    assert!(load_err(&mk(json!([[1, "1"]]), ok.clone())).contains("start at 0"));
    assert!(load_err(&mk(json!([[0, "1"], [0, "2"]]), ok.clone())).contains("ascending"));
    assert!(load_err(&mk(json!([[0, "1"], [5, "2"], [3, "3"]]), ok.clone())).contains("ascending"));
    assert!(load_err(&mk(json!([[0, 1]]), ok.clone())).contains("decimal rate string"));
    assert!(load_err(&mk(json!([[0, "1.5e3"]]), ok.clone())).contains("decimal rate string"));
    assert!(load_err(&mk(json!([[0.5, "1"]]), ok.clone())).contains("years"));
    assert!(load_err(&mk(json!([[-1, "1"]]), ok.clone())).contains("years"));
    assert!(load_err(&mk(json!([[0, "1"]]), json!({}))).contains("boundary is required"));
    assert!(
        load_err(&mk(json!([[0, "1"]]), json!({"boundary": "sometimes"})))
            .contains("boundary is required")
    );
    assert!(load_err(&mk(
        json!([[0, "1"]]),
        json!({"boundary": "lower_inclusive", "x": 1})
    ))
    .contains("only boundary"));
    // the band value is a rate, so it cannot be used as money directly
    let bad = doc(
        json!({"s": "date", "a": "date"}),
        json!({"anniversary_band": ["s", "a", [[0, "1"]], {"boundary": "lower_inclusive"}]}),
    );
    assert!(load_err(&bad).contains("expected money, found rate"));
}

// ---------------------------------------------------------------- list input + max_over

fn max_over_rule() -> Rule {
    load(&doc(
        json!({"events": "class_money_list"}),
        json!({"max_over": "events"}),
    ))
}

#[test]
fn max_over_takes_the_highest_per_class_and_sums_classes() {
    let r = max_over_rule();
    let ev = |items: J| json!({ "events": items });
    assert_eq!(amount(&r, ev(json!([]))), exact(0)); // known: no events happened
    assert_eq!(
        amount(&r, ev(json!([{"class": "a", "krw": 100}]))),
        exact(100)
    );
    assert_eq!(
        amount(
            &r,
            ev(
                json!([{"class": "a", "krw": 100}, {"class": "a", "krw": 300}, {"class": "a", "krw": 200}])
            )
        ),
        exact(300)
    );
    assert_eq!(
        amount(
            &r,
            ev(
                json!([{"class": "a", "krw": 100}, {"class": "b", "krw": 50}, {"class": "a", "krw": 70}])
            )
        ),
        exact(150)
    );
    assert_eq!(
        amount(
            &r,
            ev(json!([{"class": "a", "krw": 0}, {"class": "a", "krw": 0}]))
        ),
        exact(0)
    );
    // order does not matter
    assert_eq!(
        amount(
            &r,
            ev(
                json!([{"class": "b", "krw": 50}, {"class": "a", "krw": 70}, {"class": "a", "krw": 100}])
            )
        ),
        exact(150)
    );
}

#[test]
fn max_over_unknown_list_or_amount_is_unknown_not_zero() {
    let r = max_over_rule();
    for inputs in [
        json!({}),
        json!({"events": null}),
        json!({"events": [{"class": "a", "krw": null}]}),
        // an unknown amount may be the largest of its class, even next to a known one
        json!({"events": [{"class": "a", "krw": 100}, {"class": "a", "krw": null}]}),
        json!({"events": [{"class": "b", "krw": 100}, {"class": "a", "krw": null}]}),
    ] {
        let out = r.evaluate(&inputs).unwrap();
        assert_eq!(
            out.payout,
            Payout::Payable {
                amount: AmountOut::Unknown
            },
            "{inputs}"
        );
        assert_eq!(out.missing_inputs, ["events"], "{inputs}");
    }
}

#[test]
fn max_over_overflow_is_an_error() {
    let r = max_over_rule();
    let at_max = json!({"events": [{"class": "a", "krw": i64::MAX}, {"class": "b", "krw": 0}]});
    assert_eq!(amount(&r, at_max), exact(i64::MAX));
    let over = json!({"events": [{"class": "a", "krw": i64::MAX}, {"class": "b", "krw": 1}]});
    assert!(eval_err(&r, over).contains("overflow"));
}

#[test]
fn list_inputs_are_validated() {
    let r = max_over_rule();
    for bad in [
        json!({"events": "x"}),
        json!({"events": [1]}),
        json!({"events": [{"class": "a"}]}),
        json!({"events": [{"class": "", "krw": 1}]}),
        json!({"events": [{"class": 1, "krw": 1}]}),
        json!({"events": [{"class": "a", "krw": -1}]}),
        json!({"events": [{"class": "a", "krw": 1.5}]}),
        json!({"events": [{"class": "a", "krw": 1, "extra": 1}]}),
    ] {
        assert!(eval_err(&r, bad.clone()).contains("class, krw"), "{bad}");
    }
}

#[test]
fn max_over_and_lists_are_typed_at_load() {
    let d = doc(json!({"x": "money_krw"}), json!({"max_over": "x"}));
    assert!(load_err(&d).contains("class_money_list"));
    let d = doc(
        json!({"l": "class_money_list"}),
        json!({"max_over": "nope"}),
    );
    assert!(load_err(&d).contains("class_money_list"));
    // a list is not money, and lists cannot be compared
    let d = doc(json!({"l": "class_money_list"}), json!("l"));
    assert!(load_err(&d).contains("expected money, found class_money_list"));
    let mut d = doc(json!({"l": "class_money_list"}), json!({"krw": 1}));
    d["eligibility"] = json!({"eq": ["l", "l"]});
    assert!(load_err(&d).contains("lists cannot be compared"));
}

#[test]
fn list_input_changes_the_snapshot_hash() {
    let r = max_over_rule();
    let h = |v: J| r.evaluate(&v).unwrap().input_snapshot_hash;
    let a = h(json!({"events": [{"class": "a", "krw": 1}]}));
    assert_ne!(a, h(json!({"events": [{"class": "a", "krw": 2}]})));
    assert_ne!(a, h(json!({"events": [{"class": "b", "krw": 1}]})));
    assert_ne!(a, h(json!({"events": [{"class": "a", "krw": null}]})));
    assert_ne!(a, h(json!({})));
    assert_eq!(a, h(json!({"events": [{"krw": 1, "class": "a"}]})));
}

// ---------------------------------------------------------------- contract_effect

fn effect_rule(effect: Option<&str>) -> Rule {
    let mut d = doc(json!({"hit": "bool"}), json!({"krw": 100}));
    d["eligibility"] = json!("hit");
    if let Some(e) = effect {
        d["contract_effect"] = json!(e);
    }
    load(&d)
}

#[test]
fn contract_effect_follows_eligibility() {
    for (name, effect) in [
        ("void_refund_premium", ContractEffect::VoidRefundPremium),
        (
            "terminated_pay_reserve",
            ContractEffect::TerminatedPayReserve,
        ),
    ] {
        let r = effect_rule(Some(name));
        assert_eq!(r.contract_effect(), effect);
        let t = r.evaluate(&json!({"hit": true})).unwrap();
        assert_eq!(t.contract_effect, ContractEffectOut::Applies { effect });
        let f = r.evaluate(&json!({"hit": false})).unwrap();
        assert_eq!(f.contract_effect, ContractEffectOut::None);
        let u = r.evaluate(&json!({})).unwrap();
        assert_eq!(
            u.contract_effect,
            ContractEffectOut::Undetermined {
                conditional_effect: effect
            }
        );
        assert_eq!(u.missing_inputs, ["hit"]);
        assert_eq!(
            serde_json::to_value(&u.contract_effect).unwrap(),
            json!({"kind": "undetermined", "conditional_effect": name})
        );
    }
}

#[test]
fn undetermined_eligibility_never_reports_no_effect() {
    let r = effect_rule(Some("void_refund_premium"));
    let u = r.evaluate(&json!({"hit": null})).unwrap();
    assert_eq!(u.eligibility, Tri::Unknown);
    assert_ne!(u.contract_effect, ContractEffectOut::None);
}

#[test]
fn contract_effect_defaults_to_none_and_is_validated() {
    for r in [effect_rule(None), effect_rule(Some("none"))] {
        for inputs in [json!({"hit": true}), json!({"hit": false}), json!({})] {
            assert_eq!(
                r.evaluate(&inputs).unwrap().contract_effect,
                ContractEffectOut::None
            );
        }
    }
    let mut d = doc(json!({}), json!({"krw": 1}));
    d["contract_effect"] = json!("cancel_everything");
    assert!(load_err(&d).contains("must be one of"));
    d["contract_effect"] = json!(7);
    assert!(load_err(&d).contains("must be one of"));
}

#[test]
fn contract_effect_is_part_of_the_content_hash() {
    let a = effect_rule(None).content_hash().to_string();
    let b = effect_rule(Some("void_refund_premium"))
        .content_hash()
        .to_string();
    let c = effect_rule(Some("terminated_pay_reserve"))
        .content_hash()
        .to_string();
    assert!(a != b && b != c && a != c);
}

// ---------------------------------------------------------------- mutation

/// A golden table for a rule; a mutated rule must disagree with it somewhere.
struct Golden {
    rule: J,
    cases: Vec<(J, AmountOut)>,
}

fn disagrees(g: &Golden, mutated: &J) -> bool {
    let Ok(rule) = Rule::from_json(mutated) else {
        return true; // a mutation the loader rejects is caught
    };
    g.cases
        .iter()
        .any(|(inputs, want)| match rule.evaluate(inputs) {
            Ok(r) => {
                r.payout
                    != Payout::Payable {
                        amount: want.clone(),
                    }
            }
            Err(_) => true,
        })
}

fn assert_golden(g: &Golden) {
    assert!(
        !disagrees(g, &g.rule),
        "golden table must pass on the unmutated rule"
    );
}

fn mutate(rule: &J, path: &[&str], with: J) -> J {
    let mut m = rule.clone();
    let mut cur = &mut m;
    for k in path {
        cur = match k.parse::<usize>() {
            Ok(i) => &mut cur[i],
            Err(_) => &mut cur[*k],
        };
    }
    *cur = with;
    m
}

#[test]
fn mutated_rule_02_operators_are_caught() {
    let ma = |op: &str, args: J| {
        doc(
            json!({"a": "money_krw", "b": "money_krw", "n": "int"}),
            json!({ op: args }),
        )
    };
    let mut checked = 0;
    let mut check = |g: Golden, mutations: Vec<J>| {
        assert_golden(&g);
        for m in mutations {
            assert!(disagrees(&g, &m), "mutation survived: {m}");
            checked += 1;
        }
    };

    let g = Golden {
        rule: ma("multiply_count", json!(["a", "n"])),
        cases: vec![
            (json!({"a": 7, "n": 3}), exact(21)),
            (json!({"a": 7, "n": 0}), exact(0)),
        ],
    };
    check(
        g,
        vec![
            ma("add", json!(["a", "n"])),
            ma("multiply_count", json!(["a", 1])),
            ma("multiply_count", json!(["b", "n"])),
        ],
    );

    let g = Golden {
        rule: ma("subtract_floor0", json!(["a", "b"])),
        cases: vec![
            (json!({"a": 10, "b": 4}), exact(6)),
            (json!({"a": 4, "b": 10}), exact(0)),
            (json!({"a": 4, "b": 4}), exact(0)),
        ],
    };
    check(
        g,
        vec![
            ma("subtract_floor0", json!(["b", "a"])),
            ma("min", json!(["a", "b"])),
            ma("max", json!(["a", "b"])),
        ],
    );

    let pdoc = |amt: J| doc(json!({"a": "money_krw", "b": "int", "n": "int"}), amt);
    let g = Golden {
        rule: pdoc(json!({"pro_rata": ["a", "b", "n", {"rounding": "floor", "unit": 1}]})),
        cases: vec![
            (json!({"a": 100, "b": 1, "n": 3}), exact(33)),
            (json!({"a": 100, "b": 2, "n": 3}), exact(66)),
            (json!({"a": 100, "b": 1, "n": 0}), AmountOut::Unknown),
        ],
    };
    check(
        g,
        vec![
            pdoc(json!({"pro_rata": ["a", "b", "n", {"rounding": "ceil", "unit": 1}]})),
            pdoc(json!({"pro_rata": ["a", "n", "b", {"rounding": "floor", "unit": 1}]})),
            pdoc(json!({"pro_rata": ["a", "b", "n", {"rounding": "floor", "unit": 10}]})),
            pdoc(json!({"divide_count": ["a", "n", {"rounding": "floor", "unit": 1}]})),
        ],
    );

    let ddoc = |amt: J| doc(json!({"a": "money_krw", "n": "int"}), amt);
    let g = Golden {
        rule: ddoc(json!({"divide_count": ["a", "n", {"rounding": "half_up", "unit": 1}]})),
        cases: vec![
            (json!({"a": 100, "n": 3}), exact(33)),
            (json!({"a": 101, "n": 2}), exact(51)),
            (json!({"a": 100, "n": 0}), AmountOut::Unknown),
        ],
    };
    check(
        g,
        vec![
            ddoc(json!({"divide_count": ["a", "n", {"rounding": "floor", "unit": 1}]})),
            ddoc(json!({"divide_count": ["a", "n", {"rounding": "ceil", "unit": 1}]})),
            ddoc(json!({"divide_count": ["a", "n", {"rounding": "half_even", "unit": 1}]})),
            ddoc(json!({"multiply_count": ["a", "n"]})),
        ],
    );

    let bdoc = |table: J, boundary: &str| {
        doc(
            json!({"s": "date", "a": "date"}),
            json!({"multiply_rate": [{"krw": 1000}, {"anniversary_band": ["s", "a", table, {"boundary": boundary}]},
                {"rounding": "floor", "unit": 1}]}),
        )
    };
    let table = json!([[0, "0.5"], [1, "0.6"], [10, "1.5"]]);
    let case = |s: &str, a: &str| json!({"s": s, "a": a});
    let g = Golden {
        rule: bdoc(table.clone(), "lower_inclusive"),
        cases: vec![
            (case("2020-03-15", "2021-03-14"), exact(500)),
            (case("2020-03-15", "2021-03-15"), exact(600)),
            (case("2020-03-15", "2030-03-15"), exact(1500)),
            (case("2020-02-29", "2021-02-28"), exact(600)),
        ],
    };
    check(
        g,
        vec![
            bdoc(table.clone(), "upper_inclusive"),
            bdoc(
                json!([[0, "0.5"], [1, "0.6"], [11, "1.5"]]),
                "lower_inclusive",
            ),
            bdoc(
                json!([[0, "0.5"], [2, "0.6"], [10, "1.5"]]),
                "lower_inclusive",
            ),
            bdoc(
                json!([[0, "0.5"], [1, "0.7"], [10, "1.5"]]),
                "lower_inclusive",
            ),
            bdoc(json!([[0, "0.5"], [1, "0.6"]]), "lower_inclusive"),
        ],
    );

    let g = Golden {
        rule: doc(json!({"e": "class_money_list"}), json!({"max_over": "e"})),
        cases: vec![
            (
                json!({"e": [{"class": "a", "krw": 1}, {"class": "a", "krw": 5}, {"class": "b", "krw": 2}]}),
                exact(7),
            ),
            (json!({"e": []}), exact(0)),
            (
                json!({"e": [{"class": "a", "krw": null}]}),
                AmountOut::Unknown,
            ),
        ],
    };
    let rule = g.rule.clone();
    check(
        g,
        vec![
            mutate(&rule, &["amount"], json!({"krw": 7})),
            mutate(&rule, &["inputs", "e"], json!("money_krw")),
        ],
    );
    assert!(checked >= 20, "ran {checked} mutations");

    // mutate() is exercised on a nested path too
    let m = mutate(
        &pdoc(json!({"pro_rata": ["a", "b", "n", {"rounding": "floor", "unit": 1}]})),
        &["amount", "pro_rata", "3", "rounding"],
        json!("ceil"),
    );
    assert_eq!(m["amount"]["pro_rata"][3]["rounding"], "ceil");
}

// ---------------------------------------------------------------- soundness (I1)

/// Hiding any one input must never turn the full-information answer into a *different definite*
/// answer, and hiding every input must leave nothing definite.
fn assert_sound(rule: &Rule, full: J) {
    let want = rule.evaluate(&full).expect("full evaluation");
    let obj = full.as_object().unwrap().clone();
    for hidden in obj.keys() {
        let mut part = obj.clone();
        part.remove(hidden);
        let got = rule.evaluate(&J::Object(part)).expect("partial evaluation");
        if let (
            Payout::Payable {
                amount: AmountOut::Exact { krw: g },
            },
            Payout::Payable { amount: w },
        ) = (&got.payout, &want.payout)
        {
            assert_eq!(&exact(*g), w, "hiding `{hidden}` changed a definite amount");
        }
        assert_ne!(
            got.payout,
            Payout::Payable { amount: exact(0) },
            "hiding `{hidden}` produced a zero from nothing"
        );
        if got.payout
            == (Payout::Payable {
                amount: AmountOut::Unknown,
            })
        {
            assert!(
                !got.missing_inputs.is_empty() || obj.get(hidden).is_some(),
                "unknown amount must name its blockers"
            );
        }
    }
    let none = rule.evaluate(&json!({})).unwrap();
    assert!(
        !matches!(
            none.payout,
            Payout::Payable {
                amount: AmountOut::Exact { .. }
            }
        ),
        "no inputs must not give an exact amount: {:?}",
        none.payout
    );
}

#[test]
fn rule_02_operators_are_sound_under_hidden_inputs() {
    assert_sound(&multiply_count_rule(), json!({"daily": 10000, "days": 3}));
    assert_sound(&subtract_rule(), json!({"a": 100, "b": 30}));
    assert_sound(
        &pro_rata_rule("floor", 1),
        json!({"loss": 100, "mine": 1, "all": 3}),
    );
    assert_sound(&divide_rule("half_up", 1), json!({"total": 100, "n": 3}));
    assert_sound(
        &band_rule("lower_inclusive"),
        json!({"start": "2020-03-15", "at": "2025-03-15"}),
    );
    assert_sound(
        &band_rule("upper_inclusive"),
        json!({"start": "2020-03-15", "at": "2025-03-15"}),
    );
    assert_sound(
        &max_over_rule(),
        json!({"events": [{"class": "a", "krw": 100}, {"class": "a", "krw": 50}]}),
    );
}

#[test]
fn zero_operands_that_are_known_differ_from_unknown_ones() {
    // 0 is a real answer only when the inputs say so
    let r = multiply_count_rule();
    assert_eq!(amount(&r, json!({"daily": 100, "days": 0})), exact(0));
    assert_eq!(amount(&r, json!({"daily": 100})), AmountOut::Unknown);
    let r = subtract_rule();
    assert_eq!(amount(&r, json!({"a": 5, "b": 9})), exact(0));
    assert_eq!(amount(&r, json!({"a": 5})), AmountOut::Unknown);
}

#[test]
fn unknown_eligibility_with_rule_02_amount_stays_undetermined() {
    let mut d = doc(
        json!({"covered": "bool", "daily": "money_krw", "days": "int"}),
        json!({"multiply_count": ["daily", "days"]}),
    );
    d["eligibility"] = json!("covered");
    d["contract_effect"] = json!("terminated_pay_reserve");
    let r = load(&d);
    let out = r.evaluate(&json!({"daily": 10, "days": 2})).unwrap();
    assert_eq!(out.eligibility, Tri::Unknown);
    assert_eq!(
        out.payout,
        Payout::Undetermined {
            conditional_amount: exact(20)
        }
    );
    assert_eq!(
        out.contract_effect,
        ContractEffectOut::Undetermined {
            conditional_effect: ContractEffect::TerminatedPayReserve
        }
    );
    assert_eq!(out.missing_inputs, ["covered"]);
}

#[test]
fn rule_02_results_are_reproducible_and_identify_the_schema() {
    let r = pro_rata_rule("half_up", 1);
    let inputs = json!({"loss": 100, "mine": 2, "all": 3});
    let a = r.evaluate(&inputs).unwrap();
    let b = r.evaluate(&inputs).unwrap();
    assert_eq!(a, b);
    assert_eq!(a.schema_version, "rule-0.2");
    assert_eq!(a.trace.last().unwrap().path, "amount");
    assert!(a
        .trace
        .iter()
        .any(|t| t.op == "pro_rata" && t.result == "67 KRW"));
}

#[test]
fn composes_with_rule_01_operators() {
    // (daily * days) capped, minus a deductible, with a conditional on unknown days
    let r = load(&doc(
        json!({"daily": "money_krw", "days": "int", "deductible": "money_krw", "cap": "money_krw"}),
        json!({"subtract_floor0": [
            {"apply_cap": [{"multiply_count": ["daily", "days"]}, "cap"]}, "deductible"]}),
    ));
    assert_eq!(
        amount(
            &r,
            json!({"daily": 100, "days": 10, "deductible": 50, "cap": 600})
        ),
        exact(550)
    );
    assert_eq!(
        amount(
            &r,
            json!({"daily": 100, "days": 10, "deductible": 50, "cap": 300})
        ),
        exact(250)
    );
    assert_eq!(
        amount(
            &r,
            json!({"daily": 100, "days": 10, "deductible": 2000, "cap": 300})
        ),
        exact(0)
    );
    assert_eq!(
        amount(&r, json!({"daily": 100, "deductible": 50, "cap": 300})),
        AmountOut::Unknown
    );
}
