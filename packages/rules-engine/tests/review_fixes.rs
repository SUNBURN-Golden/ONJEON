//! Regression tests for review findings on f50d264:
//! 1. results must identify the exact rule content, version, release and evidence;
//! 2. ranges from unspecified rounding must flow through later multiplication;
//! 3. date arithmetic must reject out-of-range values instead of overflowing.
use onjeon_rules_engine::{AmountOut, EvalError, Payout, Rule};
use serde_json::{json, Value as J};

fn rule(amount: J, eligibility: J) -> J {
    json!({
        "rule_id": "r", "rule_version": "3", "schema_version": "rule-0.1", "calendar": "Asia/Seoul",
        "inputs": {"amt": "money_krw", "d1": "date", "d2": "date"},
        "eligibility": eligibility, "amount": amount,
        "unknown_policy": "use_three_valued_logic_never_default_to_zero",
        "evidence_refs": ["clause-17", "annex-2"], "publication_state": "fixture_only"
    })
}

fn amount(j: &J, inputs: J) -> AmountOut {
    match Rule::from_json(j)
        .unwrap()
        .evaluate(&inputs)
        .unwrap()
        .payout
    {
        Payout::Payable { amount } => amount,
        other => panic!("expected payable, got {other:?}"),
    }
}

// ---- 1. traceability ----

#[test]
fn result_identifies_rule_version_release_content_and_evidence() {
    let mut j = rule(json!({"krw": 1}), json!(true));
    j["publication_state"] = json!("published");
    j["release_id"] = json!("rel-2026-10-01");
    let r = Rule::from_json(&j).unwrap().evaluate(&json!({})).unwrap();
    assert_eq!(r.rule_version, "3");
    assert_eq!(r.release_id.as_deref(), Some("rel-2026-10-01"));
    assert_eq!(r.evidence_refs, vec!["clause-17", "annex-2"]);
    assert_eq!(r.rule_content_hash.len(), 64);
    let out = serde_json::to_value(&r).unwrap();
    for key in [
        "rule_version",
        "release_id",
        "rule_content_hash",
        "evidence_refs",
    ] {
        assert!(
            out.get(key).is_some(),
            "serialized result must expose {key}"
        );
    }
}

#[test]
fn content_hash_changes_with_content_even_if_version_is_not_bumped() {
    let a = Rule::from_json(&rule(json!({"krw": 1}), json!(true))).unwrap();
    let b = Rule::from_json(&rule(json!({"krw": 2}), json!(true))).unwrap();
    assert_eq!(a.rule_version, b.rule_version, "same declared version");
    assert_ne!(
        a.content_hash, b.content_hash,
        "different content must not share a hash"
    );
}

#[test]
fn content_hash_ignores_formatting_and_release_but_not_evidence() {
    let base = rule(json!({"krw": 1}), json!(true));
    let pretty = serde_json::to_string_pretty(&base).unwrap();
    let compact = serde_json::to_string(&base).unwrap();
    let h1 = Rule::from_json_str(&pretty).unwrap().content_hash;
    let h2 = Rule::from_json_str(&compact).unwrap().content_hash;
    assert_eq!(h1, h2, "whitespace and key order must not matter");

    let mut rel = base.clone();
    rel["release_id"] = json!("rel-b");
    assert_eq!(
        Rule::from_json(&rel).unwrap().content_hash,
        h1,
        "re-releasing the same content keeps the hash"
    );

    let mut ev = base.clone();
    ev["evidence_refs"] = json!(["clause-18"]);
    assert_ne!(
        Rule::from_json(&ev).unwrap().content_hash,
        h1,
        "pointing at a different clause is a content change"
    );
}

#[test]
fn version_and_release_are_enforced_at_load_time() {
    let mut j = rule(json!({"krw": 1}), json!(true));
    j.as_object_mut().unwrap().remove("rule_version");
    assert!(Rule::from_json(&j)
        .unwrap_err()
        .to_string()
        .contains("rule_version"));

    let mut j = rule(json!({"krw": 1}), json!(true));
    j["rule_version"] = json!("  ");
    assert!(Rule::from_json(&j).is_err());

    let mut j = rule(json!({"krw": 1}), json!(true));
    j["publication_state"] = json!("published");
    assert!(
        Rule::from_json(&j)
            .unwrap_err()
            .to_string()
            .contains("release"),
        "published rules must name their release"
    );

    let fixture = Rule::from_json(&rule(json!({"krw": 1}), json!(true))).unwrap();
    assert_eq!(fixture.release_id, None, "fixtures may omit the release");
}

// ---- 2. ranges through later calculation ----

#[test]
fn unspecified_rounding_range_flows_through_a_second_multiplication() {
    let inner = json!({"multiply_rate": ["amt", "0.5", {"rounding": "unspecified", "unit": 1}]});
    // 1001 * 0.5 = 500.5 -> [500, 501]
    assert_eq!(
        amount(&rule(inner.clone(), json!(true)), json!({"amt": 1001})),
        AmountOut::Range {
            min_krw: 500,
            max_krw: 501
        }
    );

    // [500, 501] * 0.5 with floor -> [250, 250] -> exact 250
    let floor = json!({"multiply_rate": [inner.clone(), "0.5", {"rounding": "floor", "unit": 1}]});
    assert_eq!(
        amount(&rule(floor, json!(true)), json!({"amt": 1001})),
        AmountOut::Exact { krw: 250 }
    );

    // [500, 501] * 0.5 unspecified -> [floor(250), ceil(250.5)] = [250, 251]
    let again =
        json!({"multiply_rate": [inner.clone(), "0.5", {"rounding": "unspecified", "unit": 1}]});
    assert_eq!(
        amount(&rule(again, json!(true)), json!({"amt": 1001})),
        AmountOut::Range {
            min_krw: 250,
            max_krw: 251
        }
    );

    // [500, 501] * 0.9 half_up -> [450, 450.9 -> 451]
    let half = json!({"multiply_rate": [inner, "0.9", {"rounding": "half_up", "unit": 1}]});
    assert_eq!(
        amount(&rule(half, json!(true)), json!({"amt": 1001})),
        AmountOut::Range {
            min_krw: 450,
            max_krw: 451
        }
    );
}

// ---- 3. bounded date arithmetic ----

#[test]
fn loader_rejects_huge_date_offsets() {
    for (value, unit) in [
        (i64::MAX, "day"),
        (110_001, "day"),
        (3_601, "calendar_month"),
        (301, "calendar_year"),
        (-301, "calendar_year"),
    ] {
        let amt = json!({"krw": 1});
        let elig = json!({"eq": [{"date_add": ["d1", {"value": value, "unit": unit, "month_end": "clamp"}]}, "d2"]});
        let err = Rule::from_json(&rule(amt, elig)).unwrap_err().to_string();
        assert!(err.contains("|value|"), "{value} {unit}: {err}");
    }
}

#[test]
fn date_arithmetic_beyond_supported_range_is_an_error_not_a_panic() {
    let elig = json!({"eq": [{"date_add": ["d1", {"value": 300, "unit": "calendar_year", "month_end": "clamp"}]}, "d2"]});
    let r = Rule::from_json(&rule(json!({"krw": 1}), elig)).unwrap();
    let err = r
        .evaluate(&json!({"d1": "2199-06-01", "d2": "2199-06-01"}))
        .unwrap_err();
    assert!(matches!(err, EvalError::DateOutOfRange { .. }), "{err:?}");

    let elig = json!({"eq": [{"date_add": ["d1", {"value": 110_000, "unit": "day"}]}, "d2"]});
    let r = Rule::from_json(&rule(json!({"krw": 1}), elig)).unwrap();
    assert!(matches!(
        r.evaluate(&json!({"d1": "2100-01-01", "d2": "2100-01-01"}))
            .unwrap_err(),
        EvalError::DateOutOfRange { .. }
    ));
}

#[test]
fn input_dates_outside_supported_range_are_rejected() {
    let r = Rule::from_json(&rule(json!({"krw": 1}), json!({"lte": ["d1", "d2"]}))).unwrap();
    assert!(r
        .evaluate(&json!({"d1": "1899-12-31", "d2": "2000-01-01"}))
        .is_err());
    assert!(r
        .evaluate(&json!({"d1": "2000-01-01", "d2": "2200-01-01"}))
        .is_err());
    assert!(r
        .evaluate(&json!({"d1": "1900-01-01", "d2": "2199-12-31"}))
        .is_ok());
}

#[test]
fn content_hash_is_independent_of_key_order_in_the_file() {
    let a = r#"{"rule_id":"k","rule_version":"1","schema_version":"rule-0.1","inputs":{"x":"int","y":"bool"},
        "eligibility":{"gte":["x",0]},"amount":{"krw":1},
        "unknown_policy":"use_three_valued_logic_never_default_to_zero","evidence_refs":["c"],"publication_state":"fixture_only"}"#;
    let b = r#"{"publication_state":"fixture_only","evidence_refs":["c"],
        "unknown_policy":"use_three_valued_logic_never_default_to_zero","amount":{"krw":1},
        "eligibility":{"gte":["x",0]},"inputs":{"y":"bool","x":"int"},"schema_version":"rule-0.1","rule_version":"1","rule_id":"k"}"#;
    assert_eq!(
        Rule::from_json_str(a).unwrap().content_hash,
        Rule::from_json_str(b).unwrap().content_hash
    );
}
