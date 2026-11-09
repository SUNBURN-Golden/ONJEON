// Raw member text is intentional: parsing to Value would erase duplicate keys.
fn duplicate_artifacts() -> Vec<(String, &'static str)> {
    let plain = std::fs::read(golden_dir().join("규칙/hana-2601-3d-cancer-dx.json")).unwrap();
    let mut value: Value = serde_json::from_slice(&plain).unwrap();
    value.as_object_mut().unwrap().remove("amount");
    let text = serde_json::to_string(&value).unwrap();
    let prefix = &text[..text.len() - 1];
    [
        (r#""amount":{"krw":1},"amount":{"krw":999}"#, "amount"),
        (r#""amount":{"krw":1,"krw":999}"#, "krw"),
        (r#""amount":{"krw":1},"\u0061mount":{"krw":999}"#, "amount"),
        (r#""amount":{"krw":1,"\u006brw":999}"#, "krw"),
        (
            r#""amount":{"krw":1},"inputs_from_outside_dsl":[],"inputs_from_outside_dsl":null"#,
            "inputs_from_outside_dsl",
        ),
        (
            r#""amount":{"krw":1},"inputs_from_outside_dsl":null,"\u0069nputs_from_outside_dsl":[]"#,
            "inputs_from_outside_dsl",
        ),
        (
            r#""amount":{"krw":1},"inputs_from_outside_dsl":[{"name":"dx_in_category","name":"already_paid","judged_by":"ontology"}]"#,
            "name",
        ),
        (
            r#""amount":{"krw":1},"inputs_from_outside_dsl":[{"name":"already_paid","judged_by":"time_stage","duration":{"value":1,"value":2,"unit":"day"}}]"#,
            "value",
        ),
    ]
    .into_iter()
    .map(|(members, key)| (format!("{prefix},{members}}}"), key))
    .collect()
}

#[test]
fn artifact_loader_rejects_duplicate_keys_before_extracting_the_declaration() {
    for (text, key) in duplicate_artifacts() {
        let err = load_rule_artifact(text.as_bytes()).unwrap_err();
        assert!(err.contains(&format!("duplicate JSON key {key:?}")), "{err}");
        assert!(err.contains("invalid JSON:"), "{err}");
        assert!(err.contains("line "), "{err}");
        assert!(err.contains("column "), "{err}");
    }
}

#[test]
fn artifact_duplicates_stop_evaluate_request_before_any_engine_call() {
    for (text, key) in duplicate_artifacts() {
        let mut a = declared_abox();
        a.rule_files.insert(
            "규칙/hana-2601-3d-cancer-dx.json".into(),
            text.into_bytes(),
        );
        // A candidate avoids the unrelated frozen-byte integrity gate: this must
        // reach rule loading through the linked request pipeline.
        let snap = candidate_snapshot(&a);
        let out = run(&snap, &question("Q1"));
        assert!(out.integrity_findings.is_empty());
        assert!(out.request_error.is_none());
        assert!(out.chain.as_ref().and_then(Chain::linked).is_some());
        let err = out.pre_engine_error.as_deref().expect("rule load must fail");
        assert!(err.contains("rule load failed:"), "{err}");
        assert!(err.contains(&format!("duplicate JSON key {key:?}")), "{err}");
        assert_eq!(out.engine_calls, 0);
        assert!(out.rule.is_none());
        assert!(out.filled.is_none());
        assert!(out.judgements.is_empty());
        assert!(out.eval.is_none());
    }
}

#[test]
fn artifact_parser_keeps_valid_body_hash_evaluation_and_optional_declaration() {
    let plain = std::fs::read(golden_dir().join("규칙/hana-2601-3d-cancer-dx.json")).unwrap();
    let value: Value = serde_json::from_slice(&plain).unwrap();
    let text = serde_json::to_string(&value).unwrap();
    let prefix = &text[..text.len() - 1];
    let baseline = onjeon_rules_engine::Rule::from_json(&value).unwrap();
    let mut facts = facts_of(&question("Q1"));
    facts.retain(|name, _| baseline.input_types().contains_key(name));
    let inputs = Value::Object(facts);
    let expected = serde_json::to_value(baseline.evaluate(&inputs).unwrap()).unwrap();
    for extra in [
        "",
        r#", "inputs_from_outside_dsl":null"#,
        r#", "inputs_from_outside_dsl":[]"#,
    ] {
        let (rule, outside) = load_rule_artifact(format!("{prefix}{extra}}}").as_bytes()).unwrap();
        assert!(outside.is_empty());
        assert_eq!(rule.content_hash(), baseline.content_hash());
        assert_eq!(rule.source_json(), baseline.source_json());
        assert_eq!(serde_json::to_value(rule.evaluate(&inputs).unwrap()).unwrap(), expected);
    }
    for bytes in [b"{} trailing".as_slice(), b"{\"x\":\"\xff\"}"] {
        assert!(load_rule_artifact(bytes).unwrap_err().contains("invalid JSON:"));
    }
}
