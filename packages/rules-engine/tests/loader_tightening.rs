//! Audit 6: validate example metadata and reject ambiguous JSON before hashing.
use onjeon_rules_engine::Rule;
use serde_json::{json, Value as J};

const KINDS: [&str; 3] = [
    "synthetic_not_a_real_product",
    "real_clause_design_validation",
    "ontology_case_validation",
];

fn base(version: &str, state: &str) -> J {
    json!({
        "rule_id": "loader-tightening", "rule_version": "1", "schema_version": version,
        "release_id": "rel-1", "publication_state": state,
        "inputs": {"ok": "bool"}, "eligibility": {"input": "ok"},
        "amount": {"krw": 1}, "evidence_refs": ["clause-1"],
        "unknown_policy": "use_three_valued_logic_never_default_to_zero"
    })
}

fn each_rule(mut check: impl FnMut(J)) {
    for version in ["rule-0.1", "rule-0.2"] {
        for state in ["fixture_only", "candidate", "released"] {
            check(base(version, state));
        }
    }
}

fn duplicate_error(text: &str, key: &str) {
    let error = Rule::from_json_str(text).expect_err("duplicate member must not load");
    assert_eq!(error.path, "$");
    assert!(error.message.starts_with("invalid JSON:"), "{error}");
    assert!(
        error
            .message
            .contains(&format!("duplicate JSON key {key:?}")),
        "{error}"
    );
    assert!(error.message.contains("line "), "{error}");
}

fn with_member(doc: &J, member: &str) -> String {
    let text = serde_json::to_string(doc).unwrap();
    format!("{{{member},{}", &text[1..])
}

#[test]
fn example_kind_rejects_wrong_types_blank_and_unknown_values() {
    each_rule(|base| {
        for value in [
            J::Null,
            json!(true),
            json!(1),
            json!(1.5),
            json!([]),
            json!({}),
            json!({"release_id": "x"}),
            json!(""),
            json!(" \t\u{3000}"),
            json!("synthetic"),
            json!("REAL_CLAUSE_DESIGN_VALIDATION"),
            json!(" ontology_case_validation"),
            json!("ontology_case_validation\n"),
        ] {
            let mut doc = base.clone();
            doc["example_kind"] = value;
            for result in [
                Rule::from_json(&doc),
                Rule::from_json_str(&serde_json::to_string(&doc).unwrap()),
            ] {
                let error = result.expect_err("invalid example kind must not load");
                assert_eq!(error.path, "example_kind");
                for kind in KINDS {
                    assert!(error.message.contains(kind), "{error}");
                }
            }
        }
    });
}

#[test]
fn example_kind_is_optional_and_valid_tags_preserve_source_hash_and_results() {
    each_rule(|base| {
        let untagged = Rule::from_json(&base).unwrap();
        let mut hashes = std::collections::BTreeSet::new();
        hashes.insert(untagged.content_hash().to_owned());
        for kind in KINDS {
            let mut doc = base.clone();
            doc["example_kind"] = json!(kind);
            let text = serde_json::to_string_pretty(&doc).unwrap();
            let loaded = Rule::from_json_str(&text).unwrap();
            let reloaded = Rule::from_json(loaded.source_json()).unwrap();
            assert_eq!(loaded.source_json(), &doc);
            assert_eq!(loaded.content_hash(), reloaded.content_hash());
            assert!(hashes.insert(loaded.content_hash().to_owned()));
            for inputs in [json!({"ok": true}), json!({"ok": false}), json!({})] {
                let result = loaded.evaluate(&inputs).unwrap();
                assert_eq!(result.payout, untagged.evaluate(&inputs).unwrap().payout);
                assert_eq!(result.rule_content_hash, loaded.content_hash());
                assert_eq!(
                    serde_json::to_vec(&result).unwrap(),
                    serde_json::to_vec(&reloaded.evaluate(&inputs).unwrap()).unwrap()
                );
            }
        }
    });
}

#[test]
fn duplicate_top_level_members_fail_even_when_identical_or_last_value_is_valid() {
    each_rule(|mut doc| {
        doc["example_kind"] = json!(KINDS[0]);
        doc["calendar"] = json!("Asia/Seoul");
        if doc["schema_version"] == "rule-0.2" {
            doc["contract_effect"] = json!("none");
        }
        for (key, value) in doc.as_object().unwrap() {
            let encoded_key = serde_json::to_string(key).unwrap();
            for earlier in [value.clone(), J::Null, json!({"ignored": true})] {
                duplicate_error(&with_member(&doc, &format!("{encoded_key}:{earlier}")), key);
            }
        }
    });
}

#[test]
fn duplicate_nested_members_fail_in_inputs_expressions_parameters_and_dead_branches() {
    each_rule(|base| {
        for (field, raw, key) in [
            ("inputs", r#"{"ok":"int","ok":"bool"}"#, "ok"),
            ("amount", r#"{"krw":0,"krw":1}"#, "krw"),
            (
                "eligibility",
                r#"{"input":"missing","input":"ok"}"#,
                "input",
            ),
            ("eligibility", r#"{"all":[false],"all":[true]}"#, "all"),
            (
                "amount",
                r#"{"multiply_rate":[{"krw":1},"0.5",{"rounding":"ceil","rounding":"floor","unit":1}]}"#,
                "rounding",
            ),
            (
                "amount",
                r#"{"multiply_rate":[{"krw":1},"0.5",{"rounding":"floor","unit":100,"unit":1}]}"#,
                "unit",
            ),
            (
                "eligibility",
                r#"{"eq":[{"date_add":[{"date":"2026-01-01"},{"value":2,"value":1,"unit":"day"}]},{"date":"2026-01-02"}]}"#,
                "value",
            ),
        ] {
            let mut doc = base.clone();
            doc.as_object_mut().unwrap().remove(field);
            duplicate_error(&with_member(&doc, &format!("{field:?}:{raw}")), key);
            if field != "inputs" {
                let fallback = &base[field];
                let dead_branch = format!(r#"{{"if":false,"then":{raw},"else":{fallback}}}"#);
                duplicate_error(&with_member(&doc, &format!("{field:?}:{dead_branch}")), key);
            }
        }
    });
    let mut doc = base("rule-0.2", "fixture_only");
    doc.as_object_mut().unwrap().remove("amount");
    duplicate_error(
        &with_member(
            &doc,
            r#""amount":{"multiply_rate":[{"krw":1},{"anniversary_band":[{"date":"2020-01-01"},{"date":"2026-01-01"},[[0,"0.5"]],{"boundary":"upper_inclusive","boundary":"lower_inclusive"}]},{"rounding":"floor","unit":1}]}"#,
        ),
        "boundary",
    );
}

#[test]
fn duplicate_keys_are_compared_after_json_string_decoding() {
    each_rule(|base| {
        for member in [
            r#""rule_\u0069d":"earlier""#,
            r#""\u0072ule_id":"loader-tightening""#,
        ] {
            duplicate_error(&with_member(&base, member), "rule_id");
        }
        let mut doc = base.clone();
        doc.as_object_mut().unwrap().remove("inputs");
        for (raw, key) in [
            (r#""inputs":{"ok":"bool","\u006fk":"bool"}"#, "ok"),
            (
                r#""inputs":{"규칙":"bool","\uaddc\uce59":"bool","ok":"bool"}"#,
                "규칙",
            ),
            (
                r#""inputs":{"a\"b":"bool","a\u0022b":"bool","ok":"bool"}"#,
                "a\"b",
            ),
        ] {
            duplicate_error(&with_member(&doc, raw), key);
        }
    });
}

#[test]
fn repeated_keys_in_separate_objects_and_key_like_string_contents_are_valid() {
    each_rule(|mut doc| {
        doc["rule_id"] = json!("{\"rule_id\":1,\"rule_id\":2} \\ \"규칙\"");
        doc["eligibility"] = json!({"all": [
            {"eq": [{"str": "규칙"}, {"str": "규칙"}]},
            {"eq": [{"krw": 1}, {"krw": 1}]}
        ]});
        let text = serde_json::to_string_pretty(&doc).unwrap();
        let escaped = text.replace("규칙", r"\uaddc\uce59");
        for text in [text, escaped] {
            let loaded = Rule::from_json_str(&text).unwrap();
            let value_loaded = Rule::from_json(&doc).unwrap();
            assert_eq!(loaded.source_json(), &doc);
            assert_eq!(loaded.content_hash(), value_loaded.content_hash());
            assert_eq!(
                loaded.evaluate(&json!({})).unwrap(),
                value_loaded.evaluate(&json!({})).unwrap()
            );
        }
    });
}
