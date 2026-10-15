//! Audit 1 finding: rules such as `{"eq":["target_event",1]}` (string vs int) or
//! `"amount": true` used to load and only failed when an input reached them, so invariant I5
//! (a loaded rule is well-formed) held syntactically only. The loader now type-checks every
//! expression, so these rules are rejected at load time with the path of the offending node.
use onjeon_rules_engine::{AmountOut, Payout, Rule};
use serde_json::{json, Value as J};

fn base(eligibility: J, amount: J) -> J {
    json!({
        "rule_id": "t", "rule_version": "1", "schema_version": "rule-0.1", "calendar": "Asia/Seoul",
        "inputs": {
            "target_event": "string", "other_event": "string", "n": "int", "amt": "money_krw",
            "d1": "date", "d2": "date", "flag": "bool"
        },
        "eligibility": eligibility, "amount": amount,
        "unknown_policy": "use_three_valued_logic_never_default_to_zero",
        "evidence_refs": ["x"], "publication_state": "fixture_only"
    })
}

fn load_err(eligibility: J, amount: J) -> (String, String) {
    let e = Rule::from_json(&base(eligibility, amount)).expect_err("must be rejected at load");
    (e.path, e.message)
}

fn loads(eligibility: J, amount: J) {
    Rule::from_json(&base(eligibility, amount)).expect("must load");
}

#[test]
fn audit_examples_are_rejected_at_load() {
    // string input compared with an int literal
    let (path, msg) = load_err(json!({"eq": ["target_event", 1]}), json!({"krw": 1}));
    assert_eq!(path, "eligibility.eq");
    assert_eq!(msg, "cannot compare string with int");
    // amount is a boolean
    let (path, msg) = load_err(json!(true), json!(true));
    assert_eq!(path, "amount");
    assert_eq!(msg, "expected money, found bool");
}

#[test]
fn top_level_expressions_must_be_bool_and_money() {
    assert_eq!(
        load_err(json!({"krw": 1}), json!({"krw": 1})).0,
        "eligibility"
    );
    assert_eq!(load_err(json!("n"), json!({"krw": 1})).0, "eligibility");
    assert_eq!(load_err(json!(true), json!("n")).0, "amount");
    assert_eq!(load_err(json!(true), json!("0.5")).0, "amount");
    assert_eq!(load_err(json!(true), json!(5)).0, "amount");
    assert_eq!(
        load_err(json!(true), json!({"date": "2024-01-01"})).0,
        "amount"
    );
    assert_eq!(
        load_err(
            json!(true),
            json!({"days_between": ["d1", "d2", {"inclusive_start": true, "inclusive_end": true}]})
        )
        .0,
        "amount"
    );
}

#[test]
fn comparisons_need_matching_operand_types() {
    for (l, r) in [
        (json!("n"), json!("amt")),
        (json!("n"), json!({"krw": 1})),
        (json!("d1"), json!("n")),
        (json!("flag"), json!(1)),
        (json!("amt"), json!("0.5")),
        (json!("target_event"), json!(true)),
    ] {
        let (path, msg) = load_err(json!({"eq": [l, r]}), json!({"krw": 1}));
        assert_eq!(path, "eligibility.eq");
        assert!(msg.starts_with("cannot compare"), "{msg}");
    }
    // matching types still load, including equality on bool/string
    loads(
        json!({"eq": ["target_event", "other_event"]}),
        json!({"krw": 1}),
    );
    loads(json!({"ne": ["flag", true]}), json!({"krw": 1}));
    loads(json!({"gte": ["n", 3]}), json!({"krw": 1}));
    loads(json!({"lt": ["d1", "d2"]}), json!({"krw": 1}));
    loads(json!({"lte": ["amt", {"krw": 10}]}), json!({"krw": 1}));
}

#[test]
fn ordering_on_bool_or_string_is_rejected_at_load() {
    for op in ["lt", "lte", "gt", "gte"] {
        let (path, msg) = load_err(json!({op: ["flag", true]}), json!({"krw": 1}));
        assert_eq!(path, format!("eligibility.{op}"));
        assert_eq!(msg, "ordering comparison is not defined for bool");
        let (_, msg) = load_err(
            json!({op: ["target_event", "other_event"]}),
            json!({"krw": 1}),
        );
        assert_eq!(msg, "ordering comparison is not defined for string");
    }
}

#[test]
fn logic_operators_need_boolean_arguments() {
    for e in [
        json!({"all": [true, "n"]}),
        json!({"any": [{"krw": 1}]}),
        json!({"not": "amt"}),
        json!({"all": [{"eq": ["n", 1]}, {"any": [false, 1]}]}),
    ] {
        load_err(e, json!({"krw": 1}));
    }
    assert_eq!(
        load_err(json!({"all": [true, "n"]}), json!({"krw": 1})).0,
        "eligibility.all[1]"
    );
    assert_eq!(
        load_err(
            json!({"all": [{"eq": ["n", 1]}, {"any": [false, 1]}]}),
            json!({"krw": 1})
        )
        .0,
        "eligibility.all[1].any[1]"
    );
    loads(
        json!({"all": [true, {"not": "flag"}, {"eq": ["n", 1]}]}),
        json!({"krw": 1}),
    );
}

#[test]
fn if_needs_boolean_condition_and_same_typed_branches() {
    let cond = |c: J, t: J, e: J| json!({"if": c, "then": t, "else": e});
    // non-boolean condition
    let (path, _) = load_err(
        json!(true),
        cond(json!("amt"), json!({"krw": 1}), json!({"krw": 2})),
    );
    assert_eq!(path, "amount.if");
    // branches of different types, in an amount and in an eligibility
    let (path, msg) = load_err(
        json!(true),
        cond(json!("flag"), json!({"krw": 1}), json!(false)),
    );
    assert_eq!(path, "amount.else");
    assert_eq!(msg, "expected money, found bool");
    let (path, _) = load_err(
        cond(json!("flag"), json!(true), json!("n")),
        json!({"krw": 1}),
    );
    assert_eq!(path, "eligibility.else");
    // the type of an `if` is the type of its branches: a bool-valued `if` is not an amount
    let (path, _) = load_err(json!(true), cond(json!("flag"), json!(true), json!(false)));
    assert_eq!(path, "amount");
    loads(
        json!(true),
        cond(json!("flag"), json!({"krw": 1}), json!("amt")),
    );
    loads(
        cond(json!("flag"), json!("flag"), json!({"eq": ["n", 1]})),
        json!({"krw": 1}),
    );
}

#[test]
fn money_operators_need_money_arguments() {
    let rounding = json!({"rounding": "floor", "unit": 1});
    for amount in [
        json!({"add": [{"krw": 1}, "n"]}),
        json!({"min": ["amt", true]}),
        json!({"max": [{"krw": 1}, "0.5"]}),
        json!({"apply_cap": ["amt", "n"]}),
        json!({"multiply_rate": ["n", "0.5", rounding]}),
        json!({"multiply_rate": ["amt", "amt", rounding]}),
        json!({"multiply_rate": ["amt", 2, rounding]}),
        json!({"multiply_rate": ["amt", "n", rounding]}),
        json!({"add": [{"krw": 1}, {"lt": ["amt", {"krw": 1}]}]}),
    ] {
        load_err(json!(true), amount);
    }
    assert_eq!(
        load_err(json!(true), json!({"add": [{"krw": 1}, "n"]})).0,
        "amount.add[1]"
    );
    assert_eq!(
        load_err(
            json!(true),
            json!({"multiply_rate": ["amt", "amt", rounding]})
        )
        .0,
        "amount.multiply_rate[1]"
    );
    loads(
        json!(true),
        json!({"add": [{"krw": 1}, "amt", {"multiply_rate": ["amt", "0.5", rounding]}]}),
    );
    loads(
        json!(true),
        json!({"apply_cap": [{"min": ["amt", {"krw": 9}]}, {"krw": 5}]}),
    );
}

#[test]
fn date_operators_need_date_arguments() {
    let incl = json!({"inclusive_start": true, "inclusive_end": false});
    let by_day = json!({"value": 1, "unit": "day"});
    assert_eq!(
        load_err(
            json!({"eq": [{"days_between": ["d1", "n", incl]}, 1]}),
            json!({"krw": 1})
        )
        .0,
        "eligibility.eq[0].days_between[1]"
    );
    assert_eq!(
        load_err(
            json!({"eq": [{"date_add": ["n", by_day]}, "d1"]}),
            json!({"krw": 1})
        )
        .0,
        "eligibility.eq[0].date_add[0]"
    );
    // days_between yields an int, date_add a date
    load_err(
        json!({"eq": [{"days_between": ["d1", "d2", incl]}, "d1"]}),
        json!({"krw": 1}),
    );
    load_err(
        json!({"eq": [{"date_add": ["d1", by_day]}, 1]}),
        json!({"krw": 1}),
    );
    loads(
        json!({"eq": [{"days_between": ["d1", "d2", incl]}, 1]}),
        json!({"krw": 1}),
    );
    loads(
        json!({"lte": [{"date_add": ["d1", by_day]}, {"date": "2030-01-01"}]}),
        json!({"krw": 1}),
    );
}

#[test]
fn literal_forms_carry_their_types() {
    loads(json!({"eq": [{"input": "n"}, 3]}), json!({"krw": 1}));
    load_err(
        json!({"eq": [{"input": "n"}, {"krw": 3}]}),
        json!({"krw": 1}),
    );
    load_err(json!({"eq": [{"rate": "0.5"}, 1]}), json!({"krw": 1}));
    loads(json!({"eq": [{"rate": "0.5"}, "0.50"]}), json!({"krw": 1}));
    load_err(
        json!({"eq": [{"date": "2024-01-01"}, "n"]}),
        json!({"krw": 1}),
    );
}

#[test]
fn well_typed_rules_still_evaluate_as_before() {
    let r = Rule::from_json(&base(
        json!({"all": [{"eq": ["target_event", "other_event"]}, {"gte": ["n", 1]}]}),
        json!({"if": "flag", "then": {"apply_cap": ["amt", {"krw": 500}]}, "else": {"krw": 0}}),
    ))
    .unwrap();
    let res = r
        .evaluate(&json!({"target_event": "surgery", "other_event": "surgery", "n": 2, "amt": 900, "flag": true}))
        .unwrap();
    assert_eq!(
        res.payout,
        Payout::Payable {
            amount: AmountOut::Exact { krw: 500 }
        }
    );
}
