//! Audit 2: explicit strings must never be resolved as input names or rates.
use onjeon_rules_engine::{AmountOut, Payout, Rule, Tri};
use serde_json::{json, Value as J};

const VERSIONS: [&str; 2] = ["rule-0.1", "rule-0.2"];

fn doc(version: &str, eligibility: J) -> J {
    json!({
        "rule_id": "string-literals", "rule_version": "1", "schema_version": version,
        "inputs": {"event": "string"}, "eligibility": eligibility, "amount": {"krw": 1},
        "unknown_policy": "use_three_valued_logic_never_default_to_zero",
        "evidence_refs": [], "publication_state": "fixture_only"
    })
}

fn assert_result(rule: &Rule, inputs: J, expected: bool) {
    let result = rule.evaluate(&inputs).unwrap();
    assert_eq!(
        result.eligibility,
        if expected { Tri::True } else { Tri::False }
    );
    assert_eq!(
        result.payout,
        if expected {
            Payout::Payable {
                amount: AmountOut::Exact { krw: 1 },
            }
        } else {
            Payout::NotPayable
        }
    );
    assert!(result.missing_inputs.is_empty());
    assert_eq!(
        serde_json::to_vec(&result).unwrap(),
        serde_json::to_vec(&rule.evaluate(&inputs).unwrap()).unwrap()
    );
}

#[test]
fn explicit_strings_support_eq_ne_on_either_side() {
    for version in VERSIONS {
        for op in ["eq", "ne"] {
            for reversed in [false, true] {
                let mut operands = vec![json!({"input": "event"}), json!({"str": "surgery"})];
                if reversed {
                    operands.reverse();
                }
                let rule = Rule::from_json(&doc(version, json!({op: operands}))).unwrap();
                for event in ["surgery", "diagnosis"] {
                    assert_result(
                        &rule,
                        json!({"event": event}),
                        (event == "surgery") == (op == "eq"),
                    );
                }
            }
        }
    }
}

#[test]
fn literal_values_are_preserved_without_rate_parsing_or_normalization() {
    for version in VERSIONS {
        for literal in [
            "",
            "수술",
            "0.5",
            "0.50",
            "123",
            " surgery ",
            "a\"\\\n\u{0}😀",
            "수술",
        ] {
            let source = doc(version, json!({"eq": ["event", {"str": literal}]}));
            // Exercise JSON escaping and the text loader as well as from_json.
            let rule = Rule::from_json_str(&serde_json::to_string(&source).unwrap()).unwrap();
            assert_result(&rule, json!({"event": literal}), true);
            assert_result(&rule, json!({"event": format!("{literal}x")}), false);
        }
        for (left, right) in [("0.5", "0.50"), ("surgery", " surgery "), ("수술", "수술")]
        {
            let rule = Rule::from_json(&doc(
                version,
                json!({"eq": [{"str": left}, {"str": right}]}),
            ))
            .unwrap();
            assert_result(&rule, json!({}), false);
        }
    }
}

#[test]
fn declared_input_names_cannot_capture_explicit_literals() {
    for version in VERSIONS {
        for name in ["surgery", "0.5", "event"] {
            let mut source = doc(version, json!({"eq": [{"input": "event"}, {"str": name}]}));
            source["inputs"][name] = json!("string");
            let rule = Rule::from_json(&source).unwrap();
            assert_result(&rule, json!({"event": name}), true);
            if name != "event" {
                for value in [J::Null, json!("different")] {
                    assert_result(&rule, json!({"event": name, name: value}), true);
                }
            }
        }
        // Even a same-named input of another type cannot change the literal's type.
        let mut source = doc(version, json!({"eq": ["event", {"str": "surgery"}]}));
        source["inputs"]["surgery"] = json!("int");
        assert_result(
            &Rule::from_json(&source).unwrap(),
            json!({"event": "surgery", "surgery": 7}),
            true,
        );
    }
}

#[test]
fn missing_and_null_string_inputs_remain_unknown() {
    for version in VERSIONS {
        for op in ["eq", "ne"] {
            let rule =
                Rule::from_json(&doc(version, json!({op: ["event", {"str": "surgery"}]}))).unwrap();
            let missing = rule.evaluate(&json!({})).unwrap();
            let null = rule.evaluate(&json!({"event": null})).unwrap();
            assert_eq!(missing.eligibility, Tri::Unknown);
            assert_eq!(
                missing.payout,
                Payout::Undetermined {
                    conditional_amount: AmountOut::Exact { krw: 1 }
                }
            );
            assert_eq!(missing.missing_inputs, ["event"]);
            assert_eq!(
                serde_json::to_vec(&missing).unwrap(),
                serde_json::to_vec(&null).unwrap()
            );
        }
    }
}

#[test]
fn str_rejects_non_string_arguments_and_extra_keys_at_load() {
    for version in VERSIONS {
        for value in [
            J::Null,
            json!(true),
            json!(1),
            json!(0.5),
            json!([]),
            json!({}),
            json!({"input": "event"}),
        ] {
            let err = Rule::from_json(&doc(version, json!({"eq": ["event", {"str": value}]})))
                .unwrap_err();
            assert_eq!(err.path, "eligibility.eq[1].str");
            assert_eq!(err.message, "must be a string");
        }
        for extra in ["extra", "input", "if"] {
            let err = Rule::from_json(&doc(
                version,
                json!({"eq": ["event", {"str": "surgery", extra: true}]}),
            ))
            .unwrap_err();
            assert_eq!(err.path, "eligibility.eq[1]");
            assert!(err.message.contains("exactly"));
        }
        // Invalid literals are rejected even in an unselected branch.
        let err = Rule::from_json(&doc(
            version,
            json!({"eq": ["event", {
                "if": true, "then": {"str": "surgery"}, "else": {"str": null}
            }]}),
        ))
        .unwrap_err();
        assert_eq!(err.path, "eligibility.eq[1].else.str");
    }
}

#[test]
fn string_literals_obey_static_comparison_and_context_types() {
    for version in VERSIONS {
        for op in ["eq", "ne", "lt", "lte", "gt", "gte"] {
            for other in [
                json!(1),
                json!(true),
                json!({"krw": 1}),
                json!({"rate": "0.5"}),
                json!({"date": "2026-01-01"}),
            ] {
                for operands in [
                    json!([{ "str": "0.5" }, other]),
                    json!([other, { "str": "0.5" }]),
                ] {
                    let err = Rule::from_json(&doc(version, json!({op: operands}))).unwrap_err();
                    assert_eq!(err.path, format!("eligibility.{op}"));
                    assert!(err.message.starts_with("cannot compare"));
                }
            }
            if !matches!(op, "eq" | "ne") {
                let err =
                    Rule::from_json(&doc(version, json!({op: ["event", {"str": "surgery"}]})))
                        .unwrap_err();
                assert_eq!(err.path, format!("eligibility.{op}"));
                assert_eq!(err.message, "ordering comparison is not defined for string");
            }
        }
        let err = Rule::from_json(&doc(version, json!({"str": "true"}))).unwrap_err();
        assert_eq!(err.path, "eligibility");
        assert_eq!(err.message, "expected bool, found string");
        let mut source = doc(version, json!(true));
        source["amount"] = json!({"str": "1"});
        let err = Rule::from_json(&source).unwrap_err();
        assert_eq!(err.path, "amount");
        assert_eq!(err.message, "expected money, found string");
    }
}

#[test]
fn string_literals_compose_with_if_and_boolean_operators() {
    for version in VERSIONS {
        let mut source = doc(
            version,
            json!({"all": [
                {"eq": ["event", {"if": "flag", "then": {"str": "surgery"}, "else": {"str": "diagnosis"}}]},
                {"not": {"ne": [{"str": "수술"}, {"str": "수술"}]}}
            ]}),
        );
        source["inputs"]["flag"] = json!("bool");
        let rule = Rule::from_json(&source).unwrap();
        assert_result(&rule, json!({"event": "surgery", "flag": true}), true);
        assert_result(&rule, json!({"event": "diagnosis", "flag": false}), true);
        assert_result(&rule, json!({"event": "surgery", "flag": false}), false);
        let unknown = rule.evaluate(&json!({"event": "surgery"})).unwrap();
        assert_eq!(unknown.eligibility, Tri::Unknown);
        assert_eq!(unknown.missing_inputs, ["flag"]);
    }
}

#[test]
fn legacy_bare_strings_keep_input_precedence_and_rate_fallback() {
    for version in VERSIONS {
        let mut source = doc(version, json!({"eq": ["event", "surgery"]}));
        let err = Rule::from_json(&source).unwrap_err();
        assert_eq!(err.path, "eligibility.eq[1]");
        assert!(err
            .message
            .contains("neither a declared input nor a decimal rate"));
        source["inputs"]["surgery"] = json!("string");
        let rule = Rule::from_json(&source).unwrap();
        assert_result(
            &rule,
            json!({"event": "surgery", "surgery": "different"}),
            false,
        );
        assert_result(
            &rule,
            json!({"event": "different", "surgery": "different"}),
            true,
        );
        assert_eq!(
            rule.evaluate(&json!({"event": "surgery"}))
                .unwrap()
                .missing_inputs,
            ["surgery"]
        );

        let mut source = doc(version, json!({"eq": ["0.5", {"rate": "0.50"}]}));
        assert_result(&Rule::from_json(&source).unwrap(), json!({}), true);
        source["inputs"]["0.5"] = json!("string");
        source["eligibility"] = json!({"eq": ["event", "0.5"]});
        assert_result(
            &Rule::from_json(&source).unwrap(),
            json!({"event": "surgery", "0.5": "surgery"}),
            true,
        );
        assert!(Rule::from_json(&doc(
            version,
            json!({"eq": [{"input": "typo"}, {"str": "surgery"}]})
        ))
        .is_err());
    }
}
