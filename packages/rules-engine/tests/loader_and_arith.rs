use onjeon_rules_engine::{AmountOut, Payout, Rule};
use serde_json::{json, Value as J};

fn base(eligibility: J, amount: J) -> J {
    json!({
        "rule_id": "t", "rule_version": "1", "schema_version": "rule-0.1", "calendar": "Asia/Seoul",
        "inputs": {"amt": "money_krw", "d1": "date", "d2": "date", "n": "int", "flag": "bool"},
        "eligibility": eligibility, "amount": amount,
        "unknown_policy": "use_three_valued_logic_never_default_to_zero",
        "evidence_refs": ["x"], "publication_state": "fixture_only"
    })
}

fn amount_of(rule_amount: J, inputs: J) -> AmountOut {
    let rule = Rule::from_json(&base(json!(true), rule_amount)).unwrap();
    match rule.evaluate(&inputs).unwrap().payout {
        Payout::Payable { amount } => amount,
        other => panic!("expected payable, got {other:?}"),
    }
}

#[test]
fn rounding_modes_are_explicit_and_exact() {
    let mk = |mode: &str| json!({"multiply_rate": ["amt", "0.5", {"rounding": mode, "unit": 1}]});
    // 1001 * 0.5 = 500.5 ; 1003 * 0.5 = 501.5
    for (amt, floor, ceil, half_up, half_even) in
        [(1001, 500, 501, 501, 500), (1003, 501, 502, 502, 502)]
    {
        let inp = json!({"amt": amt});
        assert_eq!(
            amount_of(mk("floor"), inp.clone()),
            AmountOut::Exact { krw: floor }
        );
        assert_eq!(
            amount_of(mk("ceil"), inp.clone()),
            AmountOut::Exact { krw: ceil }
        );
        assert_eq!(
            amount_of(mk("half_up"), inp.clone()),
            AmountOut::Exact { krw: half_up }
        );
        assert_eq!(
            amount_of(mk("half_even"), inp.clone()),
            AmountOut::Exact { krw: half_even }
        );
        assert_eq!(
            amount_of(mk("unspecified"), inp),
            AmountOut::Range {
                min_krw: floor,
                max_krw: ceil
            }
        );
    }
    // exact results collapse an unspecified range to a single value
    assert_eq!(
        amount_of(mk("unspecified"), json!({"amt": 1000})),
        AmountOut::Exact { krw: 500 }
    );
}

#[test]
fn rounding_to_unit() {
    let r = json!({"multiply_rate": ["amt", "0.333", {"rounding": "floor", "unit": 10}]});
    // 10000 * 0.333 = 3330 exactly; 10001 * 0.333 = 3330.333 -> 3330
    assert_eq!(
        amount_of(r.clone(), json!({"amt": 10000})),
        AmountOut::Exact { krw: 3330 }
    );
    assert_eq!(
        amount_of(r, json!({"amt": 10001})),
        AmountOut::Exact { krw: 3330 }
    );
}

#[test]
fn cap_min_max_add_with_ranges() {
    let spec = json!({"apply_cap": [{"multiply_rate": ["amt", "0.5", {"rounding": "unspecified", "unit": 1}]}, {"krw": 500}]});
    assert_eq!(
        amount_of(spec, json!({"amt": 1001})),
        AmountOut::Exact { krw: 500 }
    );
    let add = json!({"add": [{"krw": 100}, {"multiply_rate": ["amt", "0.5", {"rounding": "unspecified", "unit": 1}]}]});
    assert_eq!(
        amount_of(add, json!({"amt": 1001})),
        AmountOut::Range {
            min_krw: 600,
            max_krw: 601
        }
    );
}

#[test]
fn days_between_inclusivity_is_explicit() {
    let mk = |s: bool, e: bool| {
        Rule::from_json(&base(
            json!({"gte": [{"days_between": ["d1", "d2", {"inclusive_start": s, "inclusive_end": e}]}, 0]}),
            json!({"krw": 1}),
        ))
        .unwrap()
    };
    // Observe the computed gap through the trace.
    let gap = |s: bool, e: bool, d1: &str, d2: &str| -> String {
        let r = mk(s, e).evaluate(&json!({"d1": d1, "d2": d2})).unwrap();
        r.trace
            .iter()
            .find(|t| t.op == "days_between")
            .unwrap()
            .result
            .clone()
    };
    assert_eq!(gap(true, false, "2026-01-01", "2026-06-30"), "180"); // 180 days after start
    assert_eq!(gap(true, true, "2026-01-01", "2026-01-01"), "1");
    assert_eq!(gap(true, false, "2026-01-01", "2026-01-01"), "0");
    assert_eq!(gap(false, false, "2026-01-01", "2026-01-02"), "0");
    assert_eq!(
        gap(true, false, "2026-01-02", "2026-01-01"),
        "-1",
        "before start is reported as a negative gap"
    );
}

#[test]
fn date_add_never_assumes_365_days_per_year() {
    let rule = Rule::from_json(&base(
        json!({"eq": [{"date_add": ["d1", {"value": 1, "unit": "calendar_year", "month_end": "clamp"}]}, "d2"]}),
        json!({"krw": 1}),
    ))
    .unwrap();
    // 2024-02-29 + 1 calendar year = 2025-02-28 (clamped), not +365 days (2025-02-28 is +365 here, so also check a leap span)
    let ok = rule
        .evaluate(&json!({"d1": "2024-02-29", "d2": "2025-02-28"}))
        .unwrap();
    assert_eq!(serde_json::to_value(ok.eligibility).unwrap(), "true");
    let leap_span = rule
        .evaluate(&json!({"d1": "2023-03-01", "d2": "2024-03-01"}))
        .unwrap();
    assert_eq!(
        serde_json::to_value(leap_span.eligibility).unwrap(),
        "true",
        "a calendar year across a leap day is 366 days"
    );
}

#[test]
fn loader_rejects_everything_outside_the_allow_list() {
    let bad = |e: J, a: J| Rule::from_json(&base(e, a)).unwrap_err().to_string();
    assert!(bad(json!({"exec": "rm -rf"}), json!({"krw": 1})).contains("allow-list"));
    assert!(bad(json!(true), json!({"multiply": ["amt", "0.5"]})).contains("multiply_rate"));
    assert!(bad(
        json!(true),
        json!({"multiply_rate": ["amt", "0.5", {"unit": 1}]})
    )
    .contains("rounding is required"));
    assert!(bad(
        json!(true),
        json!({"multiply_rate": ["amt", "0.5", {"rounding": "floor"}]})
    )
    .contains("unit is required"));
    assert!(bad(json!({"gte": ["n", 0.5]}), json!({"krw": 1})).contains("floating-point"));
    assert!(
        bad(json!({"gte": ["nope", 0]}), json!({"krw": 1})).contains("neither a declared input")
    );
    assert!(bad(json!({"gte": [["n"], 0]}), json!({"krw": 1})).contains("bare array"));
    assert!(bad(
        json!(true),
        json!({"date_add": ["d1", {"value": 1, "unit": "calendar_year"}]})
    )
    .contains("month_end"));
    assert!(bad(
        json!(true),
        json!({"days_between": ["d1", "d2", {"inclusive_start": true}]})
    )
    .contains("required"));
}

#[test]
fn loader_enforces_rule_level_invariants() {
    let mut j = base(json!(true), json!({"krw": 1}));
    j["unknown_policy"] = json!("default_to_zero");
    assert!(
        Rule::from_json(&j).is_err(),
        "unknown policy must forbid defaulting to zero"
    );

    let mut j = base(json!(true), json!({"krw": 1}));
    j["publication_state"] = json!("released");
    j["evidence_refs"] = json!([]);
    assert!(
        Rule::from_json(&j)
            .unwrap_err()
            .to_string()
            .contains("evidence"),
        "published rules need evidence (principle 5)"
    );

    let mut j = base(json!(true), json!({"krw": 1}));
    j["extra_key"] = json!(1);
    assert!(Rule::from_json(&j).is_err());

    let mut j = base(json!(true), json!({"krw": 1}));
    j["schema_version"] = json!("rule-9.9");
    assert!(Rule::from_json(&j).is_err());
}

#[test]
fn evaluation_rejects_undeclared_or_mistyped_inputs() {
    let rule = Rule::from_json(&base(json!({"gte": ["n", 0]}), json!({"krw": 1}))).unwrap();
    assert!(
        rule.evaluate(&json!({"typo": 1})).is_err(),
        "undeclared inputs are typos, not ignorable"
    );
    assert!(rule.evaluate(&json!({"n": "five"})).is_err());
    assert!(
        rule.evaluate(&json!({"n": 1.5})).is_err(),
        "no floats in inputs"
    );
    assert!(rule.evaluate(&json!([1])).is_err());
    assert!(
        rule.evaluate(&json!({"amt": -5})).is_err(),
        "negative money is rejected"
    );
}
