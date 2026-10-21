//! Audit 1 finding: the `EvalError::Overflow` paths in `eval.rs` (`add` and `multiply_rate`,
//! including the `unit` rounding step and the range bounds) had no direct test. Every case here
//! sits on the `i64::MAX` edge: one step below it must evaluate exactly, one step over it must
//! fail with `Overflow` at the offending expression, and never wrap or saturate.
use onjeon_rules_engine::{AmountOut, EvalError, Payout, Rule};
use serde_json::{json, Value as J};

const MAX: i64 = i64::MAX; // 9_223_372_036_854_775_807

fn rule(amount: J) -> Rule {
    Rule::from_json(&json!({
        "rule_id": "r", "rule_version": "1", "schema_version": "rule-0.1", "calendar": "Asia/Seoul",
        "inputs": {"amt": "money_krw", "other": "money_krw"},
        "eligibility": true, "amount": amount,
        "unknown_policy": "use_three_valued_logic_never_default_to_zero",
        "evidence_refs": ["clause-1"], "publication_state": "fixture_only"
    }))
    .unwrap()
}

fn amount(amount_expr: J, inputs: J) -> AmountOut {
    match rule(amount_expr).evaluate(&inputs).unwrap().payout {
        Payout::Payable { amount } => amount,
        other => panic!("expected payable, got {other:?}"),
    }
}

/// The path of the `Overflow` error; panics on any other outcome.
fn overflow_path(amount_expr: J, inputs: J) -> String {
    match rule(amount_expr).evaluate(&inputs) {
        Err(EvalError::Overflow { path }) => path,
        other => panic!("expected Overflow, got {other:?}"),
    }
}

fn rate(money: impl Into<J>, rate: &str, rounding: &str, unit: i64) -> J {
    json!({"multiply_rate": [money.into(), rate, {"rounding": rounding, "unit": unit}]})
}

#[test]
fn add_is_exact_up_to_i64_max() {
    let add = json!({"add": ["amt", "other"]});
    assert_eq!(
        amount(add.clone(), json!({"amt": MAX - 1, "other": 1})),
        AmountOut::Exact { krw: MAX }
    );
    assert_eq!(
        amount(add, json!({"amt": MAX, "other": 0})),
        AmountOut::Exact { krw: MAX }
    );
}

#[test]
fn add_past_i64_max_overflows_instead_of_wrapping() {
    let add = json!({"add": ["amt", "other"]});
    for (a, b) in [(MAX, 1), (1, MAX), (MAX, MAX), (MAX - 1, 2)] {
        let path = overflow_path(add.clone(), json!({"amt": a, "other": b}));
        assert_eq!(path, "amount", "{a} + {b}");
    }
}

#[test]
fn add_overflow_is_found_in_any_position_of_a_long_sum() {
    let sum = json!({"add": ["amt", {"krw": 1}, {"krw": 1}]});
    // (MAX - 2) + 1 + 1 is exactly MAX; one more step overflows at the last item.
    assert_eq!(
        amount(sum.clone(), json!({"amt": MAX - 2})),
        AmountOut::Exact { krw: MAX }
    );
    overflow_path(sum, json!({"amt": MAX - 1}));
}

#[test]
fn add_overflow_in_a_nested_expression_reports_the_inner_path() {
    let nested = json!({"min": [{"add": ["amt", {"krw": 1}]}, {"krw": 5}]});
    let path = overflow_path(nested, json!({"amt": MAX}));
    assert_eq!(path, "amount.min[0]");
}

#[test]
fn min_max_and_cap_at_i64_max_never_overflow() {
    let inputs = json!({"amt": MAX, "other": MAX});
    for expr in [
        json!({"min": ["amt", "other"]}),
        json!({"max": ["amt", "other"]}),
        json!({"apply_cap": ["amt", "other"]}),
    ] {
        assert_eq!(amount(expr, inputs.clone()), AmountOut::Exact { krw: MAX });
    }
}

#[test]
fn add_overflows_on_the_upper_bound_of_a_range_alone() {
    // Inner range: 9_223_372_036_854_775_001 rounded to 10 is [...775_000, ...775_010].
    let range = rate("amt", "1", "unspecified", 10);
    let inputs = json!({"amt": 9_223_372_036_854_775_001_i64});
    assert_eq!(
        amount(range.clone(), inputs.clone()),
        AmountOut::Range {
            min_krw: 9_223_372_036_854_775_000,
            max_krw: 9_223_372_036_854_775_010
        }
    );
    // 807 + lower bound is exactly i64::MAX, so only the upper bound (MAX + 10) overflows.
    let exact_lo = json!({"add": [range.clone(), {"krw": 807}]});
    overflow_path(exact_lo, inputs.clone());
    // Without the range width (floor instead of unspecified) the same total is exactly MAX.
    let fits = json!({"add": [{"krw": 807}, rate("amt", "1", "floor", 10)]});
    assert_eq!(amount(fits, inputs), AmountOut::Exact { krw: MAX });
}

#[test]
fn multiply_rate_is_exact_when_the_result_is_i64_max() {
    // Rate "1" with unit 1: the exact product fits.
    assert_eq!(
        amount(rate("amt", "1", "floor", 1), json!({"amt": MAX})),
        AmountOut::Exact { krw: MAX }
    );
    // Floor to a unit stays below i64::MAX.
    assert_eq!(
        amount(rate("amt", "1", "floor", 1000), json!({"amt": MAX})),
        AmountOut::Exact {
            krw: 9_223_372_036_854_775_000
        }
    );
}

#[test]
fn multiply_rate_product_past_i64_max_overflows() {
    for r in ["2", "1.000000001"] {
        let path = overflow_path(rate("amt", r, "floor", 1), json!({"amt": MAX}));
        assert_eq!(path, "amount", "rate {r}");
    }
}

#[test]
fn multiply_rate_overflows_when_rounding_up_to_the_unit_exceeds_i64_max() {
    // i64::MAX is not a multiple of 1000: its remainder is 807, so anything that rounds up
    // lands on ...776_000 > i64::MAX, while floor is fine.
    let inputs = json!({"amt": MAX});
    for rounding in ["ceil", "half_up", "half_even"] {
        let path = overflow_path(rate("amt", "1", rounding, 1000), inputs.clone());
        assert_eq!(path, "amount", "{rounding}");
    }
    // 807 rounds down under half_up/half_even only when the remainder is below half a unit.
    // 9_223_372_036_854_775_300 has remainder 300, so those two modes round down and fit.
    let low = json!({"amt": 9_223_372_036_854_775_300_i64});
    for (rounding, krw) in [
        ("floor", 9_223_372_036_854_775_000),
        ("half_up", 9_223_372_036_854_775_000),
        ("half_even", 9_223_372_036_854_775_000),
    ] {
        assert_eq!(
            amount(rate("amt", "1", rounding, 1000), low.clone()),
            AmountOut::Exact { krw },
            "{rounding}"
        );
    }
    overflow_path(rate("amt", "1", "ceil", 1000), low);
}

#[test]
fn unspecified_rounding_overflows_when_only_the_upper_bound_does() {
    // floor (...775_000) fits but ceil (...776_000) does not: no half-built range is returned.
    let path = overflow_path(rate("amt", "1", "unspecified", 1000), json!({"amt": MAX}));
    assert_eq!(path, "amount");
}

#[test]
fn multiply_rate_on_a_range_overflows_on_either_bound() {
    let inner = rate("amt", "1", "unspecified", 10); // [...775_000, ...775_010]
    let inputs = json!({"amt": 9_223_372_036_854_775_001_i64});
    // Both bounds overflow.
    overflow_path(rate(inner.clone(), "2", "floor", 1), inputs.clone());
    // Lower bound rounds up to ...775_000 and fits; the upper bound rounds up to ...776_000.
    let path = overflow_path(rate(inner.clone(), "1", "ceil", 1000), inputs.clone());
    assert_eq!(path, "amount");
    // The same range through floor stays in bounds and keeps both ends.
    assert_eq!(
        amount(rate(inner, "1", "floor", 1000), inputs),
        AmountOut::Exact {
            krw: 9_223_372_036_854_775_000
        }
    );
}

#[test]
fn overflow_is_an_error_not_an_unknown_amount() {
    // A definite overflow must not be turned into "unknown" or a zero payout.
    let err = rule(rate("amt", "2", "floor", 1))
        .evaluate(&json!({"amt": MAX}))
        .unwrap_err();
    assert_eq!(err.to_string(), "arithmetic overflow at amount");
}
