use onjeon_ai_gateway::fixture_only::ScriptedProvider as P;
use onjeon_ai_gateway::*;
use serde_json::json;

const PROMPT: &str = "SECRET-PROMPT-BODY 홍길동 주민번호";
const OUT: &str = r#"{"answer":"DOC-EXCERPT-TEXT"}"#;

fn schema() -> serde_json::Value {
    json!({"type":"object","required":["answer"],"properties":{"answer":{"type":"string"}},"additionalProperties":false})
}
fn req<'a>(s: &'a serde_json::Value, user: Option<&'a str>, day: &'a str) -> Request<'a> {
    Request {
        run_id: "run-1",
        user_id: user,
        month: "2026-10",
        day,
        prompt_version: "p1",
        schema_version: "s1",
        schema: s,
        prompt: PROMPT,
    }
}
fn limits(m: u64, u: u64, r: u32) -> Limits {
    Limits {
        monthly_cap_micro_units: m,
        user_daily_cap_micro_units: u,
        max_retries: r,
    }
}

#[test]
fn resolves_valid_output_and_records_without_bodies() {
    let g = Gateway::new(
        vec![Box::new(P::new("fam-a", vec![P::reply(OUT, 5)]))],
        limits(100, 100, 1),
    );
    let s = schema();
    assert_eq!(
        g.call("fam-a", &req(&s, Some("u"), "2026-10-18")).unwrap(),
        Outcome::Resolved(json!({"answer":"DOC-EXCERPT-TEXT"}))
    );
    let recs = g.records();
    assert_eq!(recs.len(), 1);
    assert_eq!(
        recs[0].model.model_ref_hash,
        model_ref_hash("fixture-model-ref")
    );
    let dump = serde_json::to_string(&recs).unwrap();
    for banned in [
        PROMPT,
        "SECRET-PROMPT",
        "DOC-EXCERPT-TEXT",
        "fixture-model-ref",
        "홍길동",
    ] {
        assert!(!dump.contains(banned), "record leaked {banned}");
    }
}

#[test]
fn schema_failure_retries_then_unresolved() {
    let bad = P::reply(r#"{"answer":1}"#, 1);
    let g = Gateway::new(
        vec![Box::new(P::new(
            "fam-a",
            vec![bad.clone(), bad.clone(), bad],
        ))],
        limits(100, 100, 2),
    );
    let s = schema();
    assert_eq!(
        g.call("fam-a", &req(&s, None, "d")).unwrap(),
        Outcome::Unresolved
    );
    let recs = g.records();
    assert_eq!(recs.len(), 3);
    assert!(recs
        .iter()
        .all(|r| r.status == AttemptStatus::SchemaInvalid));
}

#[test]
fn retry_recovers() {
    let g = Gateway::new(
        vec![Box::new(P::new(
            "fam-a",
            vec![P::reply("not json", 1), P::reply(OUT, 1)],
        ))],
        limits(100, 100, 1),
    );
    let s = schema();
    assert!(matches!(
        g.call("fam-a", &req(&s, None, "d")).unwrap(),
        Outcome::Resolved(_)
    ));
}

#[test]
fn provider_error_is_recorded_and_unresolved() {
    let g = Gateway::new(
        vec![Box::new(P::new(
            "fam-a",
            vec![Err(ProviderError { retryable: true })],
        ))],
        limits(100, 100, 0),
    );
    let s = schema();
    assert_eq!(
        g.call("fam-a", &req(&s, None, "d")).unwrap(),
        Outcome::Unresolved
    );
    assert_eq!(g.records()[0].status, AttemptStatus::ProviderError);
}

#[test]
fn monthly_cap_degrades_with_l020() {
    let g = Gateway::new(
        vec![Box::new(P::new(
            "fam-a",
            vec![P::reply(OUT, 10), P::reply(OUT, 10)],
        ))],
        limits(10, 100, 0),
    );
    let s = schema();
    g.call("fam-a", &req(&s, Some("u1"), "d")).unwrap();
    let Err(GatewayError::CapExceeded(d)) = g.call("fam-a", &req(&s, Some("u2"), "d")) else {
        panic!("expected cap")
    };
    assert_eq!(d.error.code, "ONJ-AP-L-020");
    assert_eq!(d.error.error_class, onjeon_contracts::ErrorClass::Limit);
    assert!(d.degraded);
    assert_eq!(d.error.message_key, "err.cost_cap_reached");
    assert_eq!(
        Some(d.error.clone()),
        onjeon_contracts::errors::catalog().error_response("ONJ-AP-L-020", "run-1")
    );
    assert_eq!(g.records().len(), 1, "no provider call after cap");
}

#[test]
fn user_daily_cap_is_per_user_and_per_day() {
    let g = Gateway::new(
        vec![Box::new(P::new(
            "fam-a",
            vec![P::reply(OUT, 10), P::reply(OUT, 1), P::reply(OUT, 1)],
        ))],
        limits(1000, 10, 0),
    );
    let s = schema();
    g.call("fam-a", &req(&s, Some("u1"), "d1")).unwrap();
    assert!(matches!(
        g.call("fam-a", &req(&s, Some("u1"), "d1")),
        Err(GatewayError::CapExceeded(_))
    ));
    assert!(g.call("fam-a", &req(&s, Some("u2"), "d1")).is_ok());
    assert!(g.call("fam-a", &req(&s, Some("u1"), "d2")).is_ok());
}

#[test]
fn cap_crossed_mid_retry_stops_retries() {
    let bad = P::reply("{}", 10);
    let g = Gateway::new(
        vec![Box::new(P::new(
            "fam-a",
            vec![bad.clone(), bad.clone(), bad],
        ))],
        limits(10, 100, 5),
    );
    let s = schema();
    assert!(matches!(
        g.call("fam-a", &req(&s, None, "d")),
        Err(GatewayError::CapExceeded(_))
    ));
    assert_eq!(g.records().len(), 1);
}

#[test]
fn multiple_families_and_unknown_family() {
    let g = Gateway::new(
        vec![
            Box::new(P::new("fam-a", vec![P::reply(OUT, 1)])),
            Box::new(P::new("fam-b", vec![P::reply(OUT, 1)])),
        ],
        limits(100, 100, 0),
    );
    let s = schema();
    assert_eq!(g.families(), vec!["fam-a", "fam-b"]);
    g.call("fam-a", &req(&s, None, "d")).unwrap();
    g.call("fam-b", &req(&s, None, "d")).unwrap();
    assert_eq!(
        g.call("zzz", &req(&s, None, "d")),
        Err(GatewayError::UnknownFamily)
    );
    let labels: Vec<_> = g
        .records()
        .iter()
        .map(|r| r.model.provider_family_label.clone())
        .collect();
    assert_eq!(labels, ["fam-a", "fam-b"]);
}

#[test]
fn schema_subset_checks() {
    let s = json!({"type":"object","required":["n","k"],"properties":{"n":{"type":"integer","minimum":0,"maximum":5},"k":{"enum":["a","b"]},"l":{"type":"array","items":{"type":"string"},"maxItems":1}}});
    assert!(schema::validate(&s, &json!({"n":1,"k":"a","l":["x"]})).is_empty());
    assert!(!schema::validate(&s, &json!({"n":9,"k":"a"})).is_empty());
    assert!(!schema::validate(&s, &json!({"n":1,"k":"c"})).is_empty());
    assert!(!schema::validate(&s, &json!({"n":1})).is_empty());
    assert!(!schema::validate(&s, &json!({"n":1,"k":"a","l":["x","y"]})).is_empty());
    assert!(
        !schema::validate(&json!({"pattern":"x"}), &json!("x")).is_empty(),
        "unsupported keyword must not pass silently"
    );
}

#[test]
fn non_retryable_error_is_not_retried() {
    let g = Gateway::new(
        vec![Box::new(P::new(
            "fam-a",
            vec![Err(ProviderError { retryable: false }), P::reply(OUT, 1)],
        ))],
        limits(100, 100, 3),
    );
    let s = schema();
    assert_eq!(
        g.call("fam-a", &req(&s, None, "d")).unwrap(),
        Outcome::Unresolved
    );
    let r = g.records();
    assert_eq!(r.len(), 1);
    assert_eq!(
        r[0].model.model_ref_hash,
        model_ref_hash(onjeon_ai_gateway::NO_MODEL_REF),
        "sentinel hash on provider error"
    );
    assert_eq!(r[0].model.model_ref_hash.len(), 64);
    assert!(r[0]
        .model
        .model_ref_hash
        .bytes()
        .all(|b| b.is_ascii_hexdigit()));
}

#[test]
fn retryable_error_is_retried() {
    let g = Gateway::new(
        vec![Box::new(P::new(
            "fam-a",
            vec![Err(ProviderError { retryable: true }), P::reply(OUT, 1)],
        ))],
        limits(100, 100, 1),
    );
    let s = schema();
    assert!(matches!(
        g.call("fam-a", &req(&s, None, "d")).unwrap(),
        Outcome::Resolved(_)
    ));
    assert_eq!(g.records().len(), 2);
}

#[test]
fn unsupported_schema_fails_before_any_provider_call() {
    let g = Gateway::new(
        vec![Box::new(P::new("fam-a", vec![P::reply(OUT, 5)]))],
        limits(100, 100, 2),
    );
    let s = json!({"type":"object","properties":{"a":{"pattern":"x"}}});
    assert!(matches!(
        g.call("fam-a", &req(&s, None, "d")),
        Err(GatewayError::UnsupportedSchema(_))
    ));
    assert!(g.records().is_empty());
}

#[test]
fn cost_accumulation_saturates() {
    let g = Gateway::new(
        vec![Box::new(P::new(
            "fam-a",
            vec![P::reply(OUT, u64::MAX - 1), P::reply(OUT, 2)],
        ))],
        limits(u64::MAX, u64::MAX, 0),
    );
    let s = schema();
    g.call("fam-a", &req(&s, Some("u"), "d")).unwrap();
    // would overflow without saturating_add; lands exactly on the cap
    g.call("fam-a", &req(&s, Some("u"), "d")).unwrap();
    assert!(matches!(
        g.call("fam-a", &req(&s, Some("u"), "d")),
        Err(GatewayError::CapExceeded(_))
    ));
}

#[test]
fn bad_prompt_version_is_rejected_before_any_call() {
    let g = Gateway::new(
        vec![Box::new(P::new("fam-a", vec![P::reply(OUT, 1)]))],
        limits(100, 100, 0),
    );
    let s = schema();
    for bad in ["", "a b", "a\tb"] {
        let mut r = req(&s, None, "d");
        r.prompt_version = bad;
        assert_eq!(g.call("fam-a", &r), Err(GatewayError::InvalidPromptVersion));
    }
    assert!(g.records().is_empty());
}

#[test]
fn integer_accepts_integral_float() {
    let s = json!({"type":"integer"});
    assert!(schema::validate(&s, &json!(1.0)).is_empty());
    assert!(!schema::validate(&s, &json!(1.5)).is_empty());
}
