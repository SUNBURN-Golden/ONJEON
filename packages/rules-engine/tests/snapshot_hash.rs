use onjeon_rules_engine::{Rule, ENGINE_VERSION};
use serde_json::{json, Value as J};
use sha2::{Digest, Sha256};

fn rule(version: &str, inputs: J) -> Rule {
    Rule::from_json(&json!({
        "schema_version": version,
        "rule_id": "snapshot-test",
        "rule_version": "1",
        "release_id": "fixture",
        "publication_state": "fixture_only",
        "unknown_policy": "use_three_valued_logic_never_default_to_zero",
        "evidence_refs": [],
        "inputs": inputs,
        "eligibility": true,
        "amount": {"krw": 1}
    }))
    .unwrap()
}

fn hash(rule: &Rule, inputs: &J) -> String {
    rule.evaluate(inputs).unwrap().input_snapshot_hash
}

#[test]
fn hash_matches_independent_canonical_json_with_all_input_types() {
    let rule = rule(
        "rule-0.2",
        json!({
            "z": "string", "money": "money_krw", "list": "class_money_list",
            "int": "int", "date": "date", "bool": "bool", "absent": "string"
        }),
    );
    let inputs = json!({
        "z": "보험=\n\"\\\t\r\u{0000}\u{001f}\u{007f}\u{0085}\u{200d}\u{2028}😀",
        "money": i64::MAX, "int": i64::MIN, "date": "1970-01-01", "bool": false,
        "list": [{"krw": null, "class": "수술=\n\"\\"}, {"class": "B", "krw": 0}]
    });
    // Hand-written preimage: JSON escaping, sorted keys at every depth, tagged runtime
    // types, dates in epoch days, and explicit unknowns. No Display/Debug formatting.
    let canonical = concat!(
        r#"{"absent":{"type":"unknown"},"bool":{"type":"bool","value":false},"date":{"type":"date","value":0},"int":{"type":"int","value":-9223372036854775808},"list":{"type":"class_money_list","value":[{"class":"수술=\n\"\\","krw":null},{"class":"B","krw":0}]},"money":{"type":"money","value":9223372036854775807},"z":{"type":"string","value":"보험=\n\"\\\t\r\u0000\u001f"#,
        "\u{007f}\u{0085}\u{200d}\u{2028}😀",
        r#""}}"#
    );
    let expected = format!("{:x}", Sha256::digest(canonical.as_bytes()));
    assert_eq!(hash(&rule, &inputs), expected);
    // Repeated evaluations include the same trace and version as well as the same hash.
    let first = rule.evaluate(&inputs).unwrap();
    assert_eq!(first.engine_version, ENGINE_VERSION);
    assert!(first.engine_version.ends_with("+snapshot-json-1"));
    assert_eq!(
        serde_json::to_vec(&first).unwrap(),
        serde_json::to_vec(&rule.evaluate(&inputs).unwrap()).unwrap()
    );
}

#[test]
fn delimiter_injection_no_longer_collides() {
    for version in ["rule-0.1", "rule-0.2"] {
        let split = rule(version, json!({"a": "bool", "b": "bool"}));
        let joined = rule(version, json!({"a=true\nb": "bool"}));
        // Both previously hashed the bytes `a=true\nb=false\n`.
        assert_ne!(
            hash(&split, &json!({"a": true, "b": false})),
            hash(&joined, &json!({"a=true\nb": false}))
        );
        let equals = rule(version, json!({"a=": "string"}));
        let plain = rule(version, json!({"a": "string"}));
        assert_ne!(
            hash(&equals, &json!({"a=": "x"})),
            hash(&plain, &json!({"a": "=x"}))
        );
    }
}

#[test]
fn object_order_and_null_vs_missing_do_not_change_the_snapshot() {
    for version in ["rule-0.1", "rule-0.2"] {
        let a = rule(
            version,
            serde_json::from_str(r#"{"z":"string","a":"bool"}"#).unwrap(),
        );
        let b = rule(
            version,
            serde_json::from_str(r#"{"a":"bool","z":"string"}"#).unwrap(),
        );
        let x = serde_json::from_str(r#"{"z":"보험","a":true}"#).unwrap();
        let y = serde_json::from_str(r#"{"a":true,"z":"보험"}"#).unwrap();
        assert_eq!(hash(&a, &x), hash(&b, &y));
        assert_eq!(
            hash(&a, &json!({})),
            hash(&a, &json!({"z": null, "a": null}))
        );
        assert_ne!(hash(&a, &json!({})), hash(&a, &json!({"a": false})));
        assert_ne!(hash(&a, &json!({})), hash(&a, &json!({"z": "unknown"})));
    }
}

#[test]
fn runtime_types_and_string_bytes_remain_distinct() {
    for version in ["rule-0.1", "rule-0.2"] {
        let mut hashes = std::collections::BTreeSet::new();
        for (ty, value) in [
            ("bool", json!(false)),
            ("int", json!(0)),
            ("money_krw", json!(0)),
            ("date", json!("1970-01-01")),
            ("string", json!("0")),
            ("string", json!("unknown")),
            ("string", json!("")),
            ("string", json!("\n")),
            ("string", json!("\\n")),
            ("string", json!("é")),
            ("string", json!("e\u{0301}")),
            ("string", J::Null),
        ] {
            let rule = rule(version, json!({"x": ty}));
            assert!(
                hashes.insert(hash(&rule, &json!({"x": value}))),
                "{ty}: {value}"
            );
        }
    }
}

#[test]
fn every_input_name_is_hashed_including_release_id_and_json_metacharacters() {
    for version in ["rule-0.1", "rule-0.2"] {
        let mut hashes = std::collections::BTreeSet::new();
        for name in [
            "release_id",
            "a=b",
            "a\nb",
            "a\\nb",
            "\"\\\t\u{0000}",
            "보험😀",
        ] {
            let rule = rule(version, json!({name: "bool"}));
            let a = hash(&rule, &json!({name: true}));
            assert_ne!(a, hash(&rule, &json!({name: false})), "{name}");
            assert!(hashes.insert(a), "{name}");
        }
    }
}

#[test]
fn list_member_order_amount_and_class_are_preserved_but_object_order_is_not() {
    let rule = rule("rule-0.2", json!({"events": "class_money_list"}));
    let initial = json!({"events": [{"class": "A=\n", "krw": null}, {"class": "B", "krw": 1}]});
    let reversed_keys =
        serde_json::from_str(r#"{"events":[{"krw":null,"class":"A=\n"},{"krw":1,"class":"B"}]}"#)
            .unwrap();
    assert_eq!(hash(&rule, &initial), hash(&rule, &reversed_keys));
    let mut hashes = std::collections::BTreeSet::from([hash(&rule, &initial)]);
    for inputs in [
        json!({"events": [{"class": "B", "krw": 1}, {"class": "A=\n", "krw": null}]}),
        json!({"events": [{"class": "A=\n", "krw": 0}, {"class": "B", "krw": 1}]}),
        json!({"events": [{"class": "A=\\n", "krw": null}, {"class": "B", "krw": 1}]}),
        json!({"events": []}),
        json!({"events": null}),
    ] {
        assert!(hashes.insert(hash(&rule, &inputs)), "{inputs}");
    }
}
