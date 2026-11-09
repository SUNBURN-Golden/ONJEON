//! Keep raw JSON text: constructing a Value first would erase the regression.
use onjeon_rules_engine::{parse_rule_json, Rule};
use serde_json::{json, Value};

fn document(version: &str, state: &str, inputs: &str, eligibility: &str, amount: &str) -> String {
    format!(
        r#"{{"schema_version":"{version}","rule_id":"duplicate-audit","rule_version":"1",
        "release_id":"synthetic-release","publication_state":"{state}",
        "calendar":"Asia/Seoul","example_kind":"synthetic",
        "unknown_policy":"use_three_valued_logic_never_default_to_zero",
        "evidence_refs":["synthetic-clause"],"inputs":{inputs},
        "eligibility":{eligibility},"amount":{amount}}}"#
    )
}

fn rejects(text: &str, key: &str) {
    for err in [
        Rule::from_json_str(text).unwrap_err(),
        parse_rule_json(text.as_bytes()).unwrap_err(),
    ] {
        assert_eq!(err.path, "$");
        assert!(err.message.starts_with("invalid JSON:"), "{err}");
        assert!(
            err.message.contains(&format!("duplicate JSON key {key:?}")),
            "{err}"
        );
        assert!(err.message.contains("line "), "{err}");
        assert!(err.message.contains("column "), "{err}");
    }
}

#[test]
fn every_top_level_key_is_unique_in_both_versions_and_all_publication_states() {
    for version in ["rule-0.1", "rule-0.2"] {
        for state in ["fixture_only", "candidate", "released"] {
            let mut text = document(version, state, "{}", "true", r#"{"krw":1}"#);
            if version == "rule-0.2" {
                text.pop();
                text.push_str(r#", "contract_effect":"none"}"#);
            }
            let value: Value = serde_json::from_str(&text).unwrap();
            Rule::from_json_str(&text).unwrap();
            for (key, value) in value.as_object().unwrap() {
                let duplicate = format!("{},{}:{value}}}", &text[..text.len() - 1], json!(key));
                rejects(&duplicate, key);
            }
            // Audit 5's conflicting top-level amount: last-wins used to pay 999.
            let conflicting = format!(r#"{},"amount":{{"krw":999}}}}"#, &text[..text.len() - 1]);
            rejects(&conflicting, "amount");
        }
    }
}

#[test]
fn repeated_constructor_keys_cannot_bypass_the_one_key_check() {
    for version in ["rule-0.1", "rule-0.2"] {
        for amount in [
            r#"{"krw":1,"krw":999}"#,
            r#"{"krw":999,"krw":1}"#,
            r#"{"krw":1,"krw":1}"#,
        ] {
            rejects(
                &document(version, "fixture_only", "{}", "true", amount),
                "krw",
            );
        }
        for (eligibility, amount, key) in [
            (
                r#"{"eq":[{"str":"a","str":"b"},{"str":"b"}]}"#,
                r#"{"krw":1}"#,
                "str",
            ),
            (
                "true",
                r#"{"multiply_rate":[{"krw":10},{"rate":"0.1","rate":"0.9"},{"rounding":"floor","unit":1}]}"#,
                "rate",
            ),
        ] {
            rejects(
                &document(version, "fixture_only", "{}", eligibility, amount),
                key,
            );
        }
    }
}

#[test]
fn arrays_unselected_branches_and_operator_parameters_are_checked_recursively() {
    for version in ["rule-0.1", "rule-0.2"] {
        for (amount, key) in [
            (r#"{"add":[{"krw":1},{"krw":2,"krw":999}]}"#, "krw"),
            (
                r#"{"if":false,"then":{"krw":1,"krw":999},"else":{"krw":2}}"#,
                "krw",
            ),
            (
                r#"{"if":false,"then":{"krw":1},"then":{"krw":999},"else":{"krw":2}}"#,
                "then",
            ),
            (
                r#"{"multiply_rate":[{"krw":10},"0.5",{"rounding":"floor","unit":1,"unit":10}]}"#,
                "unit",
            ),
        ] {
            rejects(
                &document(version, "fixture_only", "{}", "true", amount),
                key,
            );
        }
        let eligibility = r#"{"all":[true,{"eq":[{"date_add":[{"date":"2026-01-01"},{"value":1,"value":2,"unit":"day"}]},{"date":"2026-01-03"}]}]}"#;
        rejects(
            &document(version, "fixture_only", "{}", eligibility, r#"{"krw":1}"#),
            "value",
        );
        // Even metadata that does not affect evaluation must have one interpretation.
        let text = document(version, "fixture_only", "{}", "true", r#"{"krw":1}"#)
            .replace(r#""synthetic""#, r#"[{"x":{"a":1,"a":2}}]"#);
        rejects(&text, "a");
    }
}

#[test]
fn input_names_and_escaped_equivalent_keys_are_checked_after_decoding() {
    for version in ["rule-0.1", "rule-0.2"] {
        for (inputs, key) in [
            (r#"{"x":"bool","x":"money_krw"}"#, "x"),
            (r#"{"x":"bool","\u0078":"bool"}"#, "x"),
            (r#"{"보장":"bool","\ubcf4\uc7a5":"bool"}"#, "보장"),
            (r#"{"a\nb":"bool","a\u000ab":"bool"}"#, "a\nb"),
            (r#"{"":"bool","":"bool"}"#, ""),
        ] {
            rejects(
                &document(version, "fixture_only", inputs, "true", r#"{"krw":1}"#),
                key,
            );
        }
        let amount = r#"{"krw":1,"\u006brw":999}"#;
        rejects(
            &document(version, "fixture_only", "{}", "true", amount),
            "krw",
        );
        let text = document(version, "fixture_only", "{}", "true", r#"{"krw":1}"#);
        let escaped = format!(
            r#"{},"\u0061mount":{{"krw":999}}}}"#,
            &text[..text.len() - 1]
        );
        rejects(&escaped, "amount");
    }
}

#[test]
fn unique_keys_keep_source_hash_and_full_evaluation_unchanged() {
    for version in ["rule-0.1", "rule-0.2"] {
        // Equal keys in separate objects are legal; NFC/NFD are distinct keys.
        let text = document(
            version,
            "fixture_only",
            r#"{"é":"bool","e\u0301":"bool","krw":"int"}"#,
            r#"{"all":[true,{"eq":[{"str":"amount, \"krw\":1, \"krw\":999"},{"str":"amount, \"krw\":1, \"krw\":999"}]}]}"#,
            r#"{"add":[{"krw":1},{"krw":999}]}"#,
        );
        let value: Value = serde_json::from_str(&text).unwrap();
        assert_eq!(parse_rule_json(text.as_bytes()).unwrap(), value);
        let strict = Rule::from_json_str(&text).unwrap();
        let constructed = Rule::from_json(&value).unwrap();
        let reloaded =
            Rule::from_json_str(&serde_json::to_string(strict.source_json()).unwrap()).unwrap();
        let inputs = json!({});
        let expected = serde_json::to_value(constructed.evaluate(&inputs).unwrap()).unwrap();
        for rule in [strict, reloaded] {
            assert_eq!(rule.source_json(), constructed.source_json());
            assert_eq!(rule.content_hash(), constructed.content_hash());
            assert_eq!(
                serde_json::to_value(rule.evaluate(&inputs).unwrap()).unwrap(),
                expected
            );
        }
    }
}

#[test]
fn strict_artifact_parser_preserves_json_values_and_syntax_guards() {
    let text = br#"{"a":[null,true,false,-9223372036854775808,18446744073709551615,1.25,"a\nb"],"b":{},"c":[]}"#;
    assert_eq!(
        parse_rule_json(text).unwrap(),
        serde_json::from_slice::<Value>(text).unwrap()
    );
    for text in [
        b"{} {}".as_slice(),
        b"[1,]",
        b"{",
        b"{\"x\":\"\xff\"}",
        b"1e999",
    ] {
        let err = parse_rule_json(text).unwrap_err();
        assert_eq!(err.path, "$");
        assert!(err.message.starts_with("invalid JSON:"), "{err}");
    }
    let deeply_nested = format!("{}null{}", "[".repeat(150), "]".repeat(150));
    assert!(parse_rule_json(deeply_nested.as_bytes())
        .unwrap_err()
        .message
        .contains("recursion limit exceeded"));
}
