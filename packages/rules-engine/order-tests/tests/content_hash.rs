use onjeon_rules_engine::Rule;

const RULE: &str = r#"{
    "rule_id":"k","rule_version":"1","schema_version":"rule-0.1","inputs":{},
    "eligibility":true,"amount":{"add":[{"if":true,"then":{"krw":1},"else":{"krw":2}},{"krw":3}]},
    "unknown_policy":"use_three_valued_logic_never_default_to_zero",
    "evidence_refs":["c"],"publication_state":"fixture_only"
}"#;

fn assert_same_hash_with_reordered_keys(original: &str, reordered: &str) {
    let baseline = Rule::from_json_str(RULE).unwrap();
    let permuted = Rule::from_json_str(&RULE.replacen(original, reordered, 1)).unwrap();

    assert_eq!(baseline.source_json(), permuted.source_json());
    assert_ne!(
        serde_json::to_vec(baseline.source_json()).unwrap(),
        serde_json::to_vec(permuted.source_json()).unwrap(),
        "the loader must retain different object key orders for this test"
    );
    assert_eq!(
        baseline.content_hash(),
        permuted.content_hash(),
        "object key order must not affect the rule content hash"
    );
}

#[test]
fn content_hash_is_independent_of_top_level_key_order() {
    assert_same_hash_with_reordered_keys(
        r#""rule_id":"k","rule_version":"1""#,
        r#""rule_version":"1","rule_id":"k""#,
    );
}

#[test]
fn content_hash_is_independent_of_object_key_order_inside_arrays() {
    assert_same_hash_with_reordered_keys(
        r#""if":true,"then":{"krw":1},"else":{"krw":2}"#,
        r#""else":{"krw":2},"then":{"krw":1},"if":true"#,
    );
}
