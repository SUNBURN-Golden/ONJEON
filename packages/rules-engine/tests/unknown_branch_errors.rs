//! Audit 1 finding: `if` with an undecided condition evaluated both branches and let an error
//! from the branch that might not be taken abort the whole rule. Such a branch is now unknown,
//! with the condition's (and the other branch's) unknown inputs as blockers. An error in a
//! branch that is actually selected, or in both branches, still fails the evaluation.
use onjeon_rules_engine::{AmountOut, EvalError, Payout, Rule};
use serde_json::{json, Value as J};

const MAX: i64 = i64::MAX;

fn rule(eligibility: J, amount: J) -> Rule {
    Rule::from_json(&json!({
        "rule_id": "r", "rule_version": "1", "schema_version": "rule-0.1", "calendar": "Asia/Seoul",
        "inputs": {"flag": "bool", "amt": "money_krw", "other": "money_krw", "d1": "date"},
        "eligibility": eligibility, "amount": amount,
        "unknown_policy": "use_three_valued_logic_never_default_to_zero",
        "evidence_refs": ["clause-1"], "publication_state": "fixture_only"
    }))
    .unwrap()
}

fn overflow() -> J {
    json!({"add": ["amt", "amt"]})
}

fn if_flag(then: J, els: J) -> J {
    json!({"if": {"eq": ["flag", true]}, "then": then, "else": els})
}

fn payable_amount(r: &Rule, inputs: J) -> (AmountOut, Vec<String>) {
    let res = r.evaluate(&inputs).unwrap();
    match res.payout {
        Payout::Payable { amount } => (amount, res.missing_inputs),
        other => panic!("expected payable, got {other:?}"),
    }
}

#[test]
fn failing_branch_under_unknown_condition_is_unknown_with_blockers() {
    for amount in [
        if_flag(json!({"krw": 100}), overflow()),
        if_flag(overflow(), json!({"krw": 100})),
    ] {
        let r = rule(json!(true), amount);
        let (amt, missing) = payable_amount(&r, json!({"amt": MAX}));
        assert_eq!(amt, AmountOut::Unknown);
        assert_eq!(missing, vec!["flag"]);
    }
}

#[test]
fn blockers_include_the_other_unknown_branch() {
    let r = rule(json!(true), if_flag(overflow(), json!("other")));
    let (amt, missing) = payable_amount(&r, json!({"amt": MAX}));
    assert_eq!(amt, AmountOut::Unknown);
    assert_eq!(missing, vec!["flag", "other"]);
}

#[test]
fn type_errors_in_a_branch_are_absorbed_too() {
    // Range comparisons now fail at load. Reversed days_between inputs still
    // produce a runtime Type error and exercise the same branch-error handling.
    let days = json!({"days_between": ["d1", {"date": "1900-01-01"},
        {"inclusive_start": true, "inclusive_end": true}]});
    let bad = json!({"if": {"lt": [days, 1]}, "then": {"krw": 1}, "else": {"krw": 2}});
    let r = rule(json!(true), if_flag(json!({"krw": 7}), bad));
    let (amt, missing) = payable_amount(&r, json!({"d1": "2024-01-01"}));
    assert_eq!(amt, AmountOut::Unknown);
    assert_eq!(missing, vec!["flag"]);
    let err = r
        .evaluate(&json!({"d1": "2024-01-01", "flag": false}))
        .unwrap_err();
    assert!(matches!(err, EvalError::Type { .. }), "{err:?}");
}

#[test]
fn a_selected_failing_branch_is_still_an_error() {
    let r = rule(json!(true), if_flag(json!({"krw": 100}), overflow()));
    let err = r.evaluate(&json!({"amt": MAX, "flag": false})).unwrap_err();
    assert!(matches!(err, EvalError::Overflow { .. }), "{err:?}");
    // The failing branch is not evaluated when the other one is selected.
    let (amt, missing) = payable_amount(&r, json!({"amt": MAX, "flag": true}));
    assert_eq!(amt, AmountOut::Exact { krw: 100 });
    assert!(missing.is_empty());
}

#[test]
fn both_branches_failing_is_still_an_error() {
    let r = rule(json!(true), if_flag(overflow(), overflow()));
    let err = r.evaluate(&json!({"amt": MAX})).unwrap_err();
    assert!(matches!(err, EvalError::Overflow { .. }), "{err:?}");
}

#[test]
fn a_failing_branch_never_makes_the_other_branch_the_answer() {
    // Even though the surviving branch is a definite 100, the result must not claim it.
    let r = rule(json!(true), if_flag(json!({"krw": 100}), overflow()));
    let (amt, _) = payable_amount(&r, json!({"amt": MAX}));
    assert_ne!(amt, AmountOut::Exact { krw: 100 });
}

#[test]
fn eligibility_branch_errors_leave_eligibility_unknown() {
    let out_of_range =
        json!({"eq": [{"date_add": ["d1", {"value": 110_000, "unit": "day"}]}, "d1"]});
    let elig = json!({"if": {"eq": ["flag", true]}, "then": out_of_range, "else": true});
    let r = rule(elig, json!({"krw": 1}));
    let res = r.evaluate(&json!({"d1": "2100-01-01"})).unwrap();
    assert_eq!(serde_json::to_value(res.eligibility).unwrap(), "unknown");
    assert_eq!(res.missing_inputs, vec!["flag"]);
    assert!(matches!(res.payout, Payout::Undetermined { .. }));
}

#[test]
fn trace_records_the_absorbed_error_and_is_deterministic() {
    let r = rule(json!(true), if_flag(json!({"krw": 100}), overflow()));
    let inputs = json!({"amt": MAX});
    let a = r.evaluate(&inputs).unwrap();
    let b = r.evaluate(&inputs).unwrap();
    assert_eq!(a.trace, b.trace);
    let entry = a
        .trace
        .iter()
        .find(|t| t.path == "amount.else")
        .expect("trace entry for the failed branch");
    assert_eq!(entry.op, "add");
    assert!(
        entry.result.starts_with("error: arithmetic overflow"),
        "{}",
        entry.result
    );
    assert!(
        !a.trace.iter().any(|t| t.path.starts_with("amount.else.")),
        "partial trace of the failed branch is dropped"
    );
}
