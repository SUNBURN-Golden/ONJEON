//! Audit 4: exercise existing load-time guards through both public loaders.
//! Each expression rejection is also checked in a statically unselected branch.
use onjeon_rules_engine::Rule;
use serde_json::{json, Value as J};

const VERSIONS: [&str; 2] = ["rule-0.1", "rule-0.2"];

fn base(version: &str) -> J {
    json!({
        "rule_id": "loader-audit", "rule_version": "1", "schema_version": version,
        "calendar": "Asia/Seoul", "publication_state": "fixture_only",
        "unknown_policy": "use_three_valued_logic_never_default_to_zero",
        "evidence_refs": ["synthetic-clause"],
        "inputs": {"amt": "money_krw", "n": "int", "d1": "date", "d2": "date"},
        "eligibility": true, "amount": {"krw": 1}
    })
}

fn rejects(doc: &J, path: &str, message: &str) {
    let text = serde_json::to_string(doc).unwrap();
    for (loader, result) in [
        ("value", Rule::from_json(doc)),
        ("text", Rule::from_json_str(&text)),
    ] {
        let err = result.expect_err(&format!("{loader} must reject {doc}"));
        assert_eq!(err.path, path, "{loader}: {doc}: {err}");
        assert!(
            err.message.contains(message),
            "{loader}: {doc}: expected {message:?}, got {err}"
        );
    }
}

fn accepts(doc: &J) {
    let a = Rule::from_json(doc).expect("valid control must load");
    let b = Rule::from_json_str(&serde_json::to_string(doc).unwrap()).unwrap();
    assert_eq!(a.source_json(), doc);
    assert_eq!(a.content_hash(), b.content_hash());
    let mut inputs = json!({"amt": 1000, "n": 2, "d1": "2024-01-01", "d2": "2024-01-02"});
    if doc["inputs"].get("events").is_some() {
        inputs["events"] = json!([{"class": "a", "krw": 10}]);
    }
    assert_eq!(
        serde_json::to_vec(&a.evaluate(&inputs).unwrap()).unwrap(),
        serde_json::to_vec(&b.evaluate(&inputs).unwrap()).unwrap()
    );
}

fn rejects_expr(version: &str, field: &str, expr: J, suffix: &str, message: &str) {
    let mut doc = base(version);
    let fallback = doc[field].clone();
    doc[field] = expr.clone();
    rejects(&doc, &format!("{field}{suffix}"), message);
    // Evaluation would take `else`; loading must still validate `then`.
    doc[field] = json!({"if": false, "then": expr, "else": fallback});
    rejects(&doc, &format!("{field}.then{suffix}"), message);
}

#[test]
fn document_shape_and_required_fields_are_checked_before_evaluation() {
    for value in [J::Null, json!(true), json!(1), json!("rule"), json!([])] {
        rejects(&value, "$", "rule must be a JSON object");
    }
    for text in ["", "{", "{} trailing", "[1,]"] {
        let err = Rule::from_json_str(text).unwrap_err();
        assert_eq!(err.path, "$");
        assert!(err.message.starts_with("invalid JSON:"));
    }
    for version in VERSIONS {
        accepts(&base(version));
        for key in [
            "rule_id",
            "rule_version",
            "schema_version",
            "unknown_policy",
            "publication_state",
        ] {
            let mut doc = base(version);
            doc.as_object_mut().unwrap().remove(key);
            rejects(&doc, "$", &format!("`{key}` must be a string"));
            for value in [J::Null, json!(42), json!(false), json!([]), json!({})] {
                doc[key] = value;
                rejects(&doc, "$", &format!("`{key}` must be a string"));
            }
        }
        for (key, message) in [
            ("inputs", "must be an object"),
            ("evidence_refs", "must be an array"),
            ("eligibility", "missing"),
            ("amount", "missing"),
        ] {
            let mut doc = base(version);
            doc.as_object_mut().unwrap().remove(key);
            rejects(&doc, key, message);
        }
        let mut doc = base(version);
        doc["unexpected"] = json!(null);
        rejects(&doc, "$", "unknown top-level key `unexpected`");
    }
}

#[test]
fn metadata_values_do_not_silently_default() {
    for version in VERSIONS {
        for (key, values, message) in [
            (
                "calendar",
                vec![json!("UTC"), J::Null, json!(1)],
                "only Asia/Seoul",
            ),
            (
                "publication_state",
                vec![json!("published"), json!("")],
                "must be fixture_only|candidate|released",
            ),
            (
                "schema_version",
                vec![json!("rule-0.3"), json!("")],
                "expected rule-0.1 or rule-0.2",
            ),
            (
                "unknown_policy",
                vec![json!("default_to_zero"), json!("")],
                "must be `use_three_valued_logic_never_default_to_zero`",
            ),
            (
                "rule_version",
                vec![json!(""), json!(" \t\n")],
                "must not be empty",
            ),
            (
                "release_id",
                vec![
                    json!(""),
                    json!(" \t\n"),
                    json!(1),
                    json!(false),
                    json!([]),
                    json!({}),
                ],
                "must be a non-empty string",
            ),
        ] {
            for value in values {
                let mut doc = base(version);
                doc[key] = value;
                rejects(&doc, key, message);
            }
        }
        let mut doc = base(version);
        doc.as_object_mut().unwrap().remove("calendar");
        accepts(&doc); // calendar is optional, but an explicit invalid value is not.
        for state in ["fixture_only", "candidate", "released"] {
            for release in [None, Some(J::Null)] {
                let mut doc = base(version);
                doc["publication_state"] = json!(state);
                if let Some(release) = release {
                    doc["release_id"] = release;
                }
                if state == "fixture_only" {
                    accepts(&doc);
                } else {
                    rejects(&doc, "release_id", "must name the release");
                }
                doc["release_id"] = json!("synthetic-release");
                accepts(&doc);
            }
        }
        if version == "rule-0.2" {
            for value in [J::Null, json!(1), json!("terminate"), json!({})] {
                let mut doc = base(version);
                doc["contract_effect"] = value;
                rejects(
                    &doc,
                    "contract_effect",
                    "must be one of none|void_refund_premium|terminated_pay_reserve",
                );
            }
        }
    }
}

#[test]
fn input_declarations_and_evidence_containers_require_their_declared_types() {
    for version in VERSIONS {
        for value in [J::Null, json!(1), json!("money_krw"), json!([])] {
            let mut doc = base(version);
            doc["inputs"] = value;
            rejects(&doc, "inputs", "must be an object of name -> type");
        }
        for value in [
            J::Null,
            json!(1),
            json!(true),
            json!({}),
            json!("float"),
            json!("money"),
        ] {
            let mut doc = base(version);
            doc["inputs"]["unused"] = value;
            rejects(
                &doc,
                "inputs.unused",
                "type must be bool|int|money_krw|date|string",
            );
        }
        for value in [J::Null, json!("clause"), json!({}), json!(1)] {
            let mut doc = base(version);
            doc["evidence_refs"] = value;
            rejects(&doc, "evidence_refs", "must be an array");
        }
        for value in [J::Null, json!(1), json!(true), json!([]), json!({})] {
            let mut doc = base(version);
            doc["evidence_refs"] = json!(["valid-first", value]);
            rejects(&doc, "evidence_refs", "must be strings");
        }
    }
}

#[test]
fn expression_objects_and_if_objects_have_exact_shapes() {
    for version in VERSIONS {
        for (expr, message) in [
            (J::Null, "null is not an expression"),
            (json!([]), "a bare array is not an expression"),
            (json!({}), "an operator object must have exactly one key"),
            (
                json!({"krw": 1, "str": "x"}),
                "an operator object must have exactly one key",
            ),
            (
                json!({"if": true, "then": {"krw": 1}}),
                "exactly if/then/else",
            ),
            (
                json!({"if": true, "else": {"krw": 1}}),
                "exactly if/then/else",
            ),
            (
                json!({"if": true, "then": {"krw": 1}, "else": {"krw": 2}, "extra": null}),
                "exactly if/then/else",
            ),
        ] {
            rejects_expr(version, "amount", expr, "", message);
        }
    }
}

#[test]
fn money_rate_and_explicit_input_literals_reject_invalid_values() {
    for version in VERSIONS {
        for value in [
            json!(-1),
            json!(1.5),
            json!("1"),
            J::Null,
            json!(true),
            json!(u64::MAX),
        ] {
            rejects_expr(
                version,
                "amount",
                json!({"krw": value}),
                ".krw",
                "must be a non-negative integer",
            );
        }
        for value in [
            json!("-0.5"),
            json!("1e2"),
            json!("NaN"),
            json!(""),
            json!(0.5),
            J::Null,
            json!({}),
        ] {
            rejects_expr(
                version,
                "eligibility",
                json!({"eq": [{"rate": value}, "0.5"]}),
                ".eq[0].rate",
                "must be a non-negative decimal string",
            );
        }
        for value in [json!("undeclared"), J::Null, json!(1), json!({})] {
            rejects_expr(
                version,
                "amount",
                json!({"input": value}),
                ".input",
                "must name a declared input",
            );
        }
        let mut doc = base(version);
        doc["amount"] = json!({"add": [{"krw": 0}, {"krw": i64::MAX}]});
        doc["eligibility"] = json!({"eq": [{"rate": "0.50"}, "0.5"]});
        accepts(&doc);
    }
}

fn array_operators() -> Vec<(&'static str, &'static str, J, usize, usize)> {
    vec![
        ("all", "eligibility", json!([true]), 1, 64),
        ("any", "eligibility", json!([true]), 1, 64),
        ("add", "amount", json!([{"krw": 1}, {"krw": 1}]), 2, 64),
        ("min", "amount", json!([{"krw": 1}, {"krw": 1}]), 2, 64),
        ("max", "amount", json!([{"krw": 1}, {"krw": 1}]), 2, 64),
        ("apply_cap", "amount", json!([{"krw": 1}, {"krw": 1}]), 2, 2),
        (
            "multiply_rate",
            "amount",
            json!(["amt", "0.5", {"rounding": "floor", "unit": 1}]),
            3,
            3,
        ),
        ("multiply_count", "amount", json!(["amt", 1]), 2, 2),
        (
            "subtract_floor0",
            "amount",
            json!(["amt", {"krw": 1}]),
            2,
            2,
        ),
        (
            "pro_rata",
            "amount",
            json!(["amt", 1, 2, {"rounding": "floor", "unit": 1}]),
            4,
            4,
        ),
        (
            "divide_count",
            "amount",
            json!(["amt", 2, {"rounding": "floor", "unit": 1}]),
            3,
            3,
        ),
    ]
}

#[test]
fn array_operator_arity_and_container_guards_reject_both_sides_of_the_bounds() {
    for version in VERSIONS {
        for (op, field, valid, min, max) in array_operators() {
            if version == "rule-0.1"
                && [
                    "multiply_count",
                    "subtract_floor0",
                    "pro_rata",
                    "divide_count",
                ]
                .contains(&op)
            {
                continue;
            }
            let mut doc = base(version);
            doc[field] = json!({op: valid});
            accepts(&doc);
            for bad in [J::Null, json!({}), json!(true), json!("args")] {
                rejects_expr(
                    version,
                    field,
                    json!({op: bad}),
                    &format!(".{op}"),
                    "operator arguments must be an array",
                );
            }
            let values = valid.as_array().unwrap();
            for len in [0, min - 1, max + 1] {
                let bad: Vec<J> = values.iter().cycle().take(len).cloned().collect();
                rejects_expr(
                    version,
                    field,
                    json!({op: bad}),
                    &format!(".{op}"),
                    &format!("expected {min}..={max} arguments, got {len}"),
                );
            }
            if max == 64 {
                doc[field] = json!({op: vec![values[0].clone(); 64]});
                accepts(&doc);
            }
        }
        for op in ["eq", "ne", "lt", "lte", "gt", "gte"] {
            for bad in [J::Null, json!([1]), json!([1, 2, 3])] {
                let message = if bad.is_array() {
                    "expected 2..=2 arguments"
                } else {
                    "operator arguments must be an array"
                };
                rejects_expr(
                    version,
                    "eligibility",
                    json!({op: bad}),
                    &format!(".{op}"),
                    message,
                );
            }
        }
    }
}

#[test]
fn date_and_band_operators_reject_wrong_arity_before_parsing_children() {
    for version in VERSIONS {
        for (op, valid, rhs, count) in [
            (
                "days_between",
                json!(["d1", "d2", {"inclusive_start": true, "inclusive_end": false}]),
                json!(1),
                3,
            ),
            (
                "date_add",
                json!(["d1", {"value": 1, "unit": "day"}]),
                json!("d2"),
                2,
            ),
            (
                "anniversary_band",
                json!(["d1", "d2", [[0, "1"]], {"boundary": "lower_inclusive"}]),
                json!("1"),
                4,
            ),
        ] {
            if version == "rule-0.1" && op == "anniversary_band" {
                continue;
            }
            let mut doc = base(version);
            doc["eligibility"] = json!({"eq": [{op: valid}, rhs]});
            accepts(&doc);
            for len in [0, count - 1, count + 1] {
                let bad: Vec<J> = valid
                    .as_array()
                    .unwrap()
                    .iter()
                    .cycle()
                    .take(len)
                    .cloned()
                    .collect();
                rejects_expr(
                    version,
                    "eligibility",
                    json!({"eq": [{op: bad}, rhs]}),
                    &format!(".eq[0].{op}"),
                    &format!("expected {count}..={count} arguments, got {len}"),
                );
            }
            rejects_expr(
                version,
                "eligibility",
                json!({"eq": [{op: null}, rhs]}),
                &format!(".eq[0].{op}"),
                "operator arguments must be an array",
            );
        }
    }
}

#[test]
fn every_rule_02_operator_is_gated_independently_of_input_declarations() {
    // In particular, max_over's version guard must be reached before checking
    // its input type; declaring a list in 0.1 would mask this guard entirely.
    for op in [
        "multiply_count",
        "subtract_floor0",
        "pro_rata",
        "divide_count",
        "anniversary_band",
        "max_over",
    ] {
        rejects_expr(
            "rule-0.1",
            "amount",
            json!({op: null}),
            &format!(".{op}"),
            "requires schema_version rule-0.2",
        );
    }
    let mut doc = base("rule-0.1");
    doc["inputs"]["events"] = json!("class_money_list");
    rejects(
        &doc,
        "inputs.events",
        "`class_money_list` requires schema_version rule-0.2",
    );
    for effect in [
        json!("none"),
        json!("void_refund_premium"),
        json!("terminated_pay_reserve"),
        J::Null,
    ] {
        let mut doc = base("rule-0.1");
        doc["contract_effect"] = effect;
        rejects(&doc, "contract_effect", "requires schema_version rule-0.2");
    }
}

fn rounded(op: &str, params: J) -> J {
    match op {
        "multiply_rate" => json!({op: ["amt", "0.5", params]}),
        "pro_rata" => json!({op: ["amt", 1, 2, params]}),
        "divide_count" => json!({op: ["amt", 2, params]}),
        _ => unreachable!(),
    }
}

#[test]
fn every_rounding_operator_rejects_invalid_parameters_and_accepts_all_allowed_pairs() {
    for version in VERSIONS {
        for op in ["multiply_rate", "pro_rata", "divide_count"] {
            if version == "rule-0.1" && op != "multiply_rate" {
                continue;
            }
            for (params, message) in [
                (J::Null, "last argument must be {rounding, unit}"),
                (json!([]), "last argument must be {rounding, unit}"),
                (json!({"unit": 1}), "rounding is required"),
                (
                    json!({"rounding": "nearest", "unit": 1}),
                    "rounding is required",
                ),
                (json!({"rounding": null, "unit": 1}), "rounding is required"),
                (json!({"rounding": 1, "unit": 1}), "rounding is required"),
                (json!({"rounding": "floor"}), "unit is required"),
                (
                    json!({"rounding": "floor", "unit": 1, "extra": null}),
                    "only rounding and unit are allowed",
                ),
            ] {
                rejects_expr(
                    version,
                    "amount",
                    rounded(op, params),
                    &format!(".{op}"),
                    message,
                );
            }
            for unit in [
                json!(0),
                json!(-1),
                json!(2),
                json!(10000),
                json!(1.0),
                json!("1"),
                J::Null,
                json!(true),
            ] {
                rejects_expr(
                    version,
                    "amount",
                    rounded(op, json!({"rounding": "floor", "unit": unit})),
                    &format!(".{op}"),
                    "unit is required: 1|10|100|1000",
                );
            }
            for rounding in ["floor", "ceil", "half_up", "half_even", "unspecified"] {
                for unit in [1, 10, 100, 1000] {
                    let mut doc = base(version);
                    doc["amount"] = rounded(op, json!({"rounding": rounding, "unit": unit}));
                    accepts(&doc);
                }
            }
        }
    }
}

#[test]
fn days_between_requires_boolean_inclusivity_and_a_closed_parameter_object() {
    for version in VERSIONS {
        for (params, message) in [
            (J::Null, "third argument must be"),
            (json!([]), "third argument must be"),
            (json!({}), "required booleans"),
            (json!({"inclusive_start": true}), "required booleans"),
            (json!({"inclusive_end": false}), "required booleans"),
            (
                json!({"inclusive_start": true, "inclusive_end": false, "extra": null}),
                "only inclusive_start and inclusive_end are allowed",
            ),
        ] {
            rejects_expr(
                version,
                "eligibility",
                json!({"gte": [{"days_between": ["d1", "d2", params]}, 0]}),
                ".gte[0].days_between",
                message,
            );
        }
        for key in ["inclusive_start", "inclusive_end"] {
            for value in [J::Null, json!(0), json!("true"), json!([])] {
                let mut params = json!({"inclusive_start": true, "inclusive_end": false});
                params[key] = value;
                rejects_expr(
                    version,
                    "eligibility",
                    json!({"gte": [{"days_between": ["d1", "d2", params]}, 0]}),
                    ".gte[0].days_between",
                    "required booleans",
                );
            }
        }
        for start in [false, true] {
            for end in [false, true] {
                let mut doc = base(version);
                doc["eligibility"] = json!({"gte": [{"days_between": ["d1", "d2", {"inclusive_start": start, "inclusive_end": end}]}, 0]});
                accepts(&doc);
            }
        }
    }
}

#[test]
fn date_add_parameter_types_units_and_month_end_values_are_checked() {
    for version in VERSIONS {
        for (params, message) in [
            (J::Null, "second argument must be"),
            (json!([]), "second argument must be"),
            (
                json!({"value": 1.0, "unit": "day"}),
                "value must be an integer",
            ),
            (
                json!({"value": "1", "unit": "day"}),
                "value must be an integer",
            ),
            (
                json!({"value": null, "unit": "day"}),
                "value must be an integer",
            ),
            (
                json!({"value": 1, "unit": "year"}),
                "unit must be day|calendar_month|calendar_year",
            ),
            (
                json!({"value": 1, "unit": null}),
                "unit must be day|calendar_month|calendar_year",
            ),
        ] {
            rejects_expr(
                version,
                "eligibility",
                json!({"eq": [{"date_add": ["d1", params]}, "d2"]}),
                ".eq[0].date_add",
                message,
            );
        }
        for unit in ["calendar_month", "calendar_year"] {
            for month_end in [J::Null, json!("rollover"), json!(true)] {
                rejects_expr(
                    version,
                    "eligibility",
                    json!({"eq": [{"date_add": ["d1", {"value": 1, "unit": unit, "month_end": month_end}]}, "d2"]}),
                    ".eq[0].date_add",
                    "requires month_end=\"clamp\"",
                );
            }
        }
    }
}

#[test]
fn anniversary_band_rejects_malformed_tables_and_boundary_containers() {
    let version = "rule-0.2";
    let band = |table: J, params: J| json!({"eq": [{"anniversary_band": ["d1", "d2", table, params]}, "1"]});
    let params = json!({"boundary": "lower_inclusive"});
    for (table, suffix, message) in [
        (J::Null, "[2]", "must be an array of [years, rate] pairs"),
        (json!([]), "[2]", "needs 1..=64 bands"),
        (
            json!((0..65).map(|year| json!([year, "1"])).collect::<Vec<_>>()),
            "[2]",
            "needs 1..=64 bands",
        ),
        (json!([null]), "[2][0]", "must be [years, rate]"),
        (json!([[0]]), "[2][0]", "must be [years, rate]"),
        (
            json!([[0, "1", "extra"]]),
            "[2][0]",
            "must be [years, rate]",
        ),
        (
            json!([[0, "1"], [301, "1"]]),
            "[2][1]",
            "years must be an integer in 0..=300",
        ),
        (
            json!([[0, "1"], [1, "-1"]]),
            "[2][1]",
            "value must be a decimal rate string",
        ),
    ] {
        rejects_expr(
            version,
            "eligibility",
            band(table, params.clone()),
            &format!(".eq[0].anniversary_band{suffix}"),
            message,
        );
    }
    for (params, message) in [
        (J::Null, "last argument must be {boundary}"),
        (json!([]), "last argument must be {boundary}"),
        (json!({"boundary": null}), "boundary is required"),
        (json!({"boundary": true}), "boundary is required"),
    ] {
        rejects_expr(
            version,
            "eligibility",
            band(json!([[0, "1"]]), params),
            ".eq[0].anniversary_band[3]",
            message,
        );
    }
    for boundary in ["lower_inclusive", "upper_inclusive"] {
        for years in [vec![0], (0..64).collect(), vec![0, 300]] {
            let table: Vec<J> = years.into_iter().map(|y| json!([y, "1"])).collect();
            let mut doc = base(version);
            doc["eligibility"] = band(json!(table), json!({"boundary": boundary}));
            accepts(&doc);
        }
    }
}

#[test]
fn max_over_requires_a_declared_list_and_lists_cannot_be_compared() {
    let mut doc = base("rule-0.2");
    doc["inputs"]["events"] = json!("class_money_list");
    doc["amount"] = json!({"max_over": "events"});
    accepts(&doc);
    for value in [
        json!("missing"),
        json!("amt"),
        J::Null,
        json!([]),
        json!({"input": "events"}),
    ] {
        doc["amount"] = json!({"max_over": value});
        rejects(
            &doc,
            "amount.max_over",
            "must name a declared class_money_list input",
        );
        doc["amount"] = json!({"if": false, "then": {"max_over": value}, "else": {"krw": 1}});
        rejects(
            &doc,
            "amount.then.max_over",
            "must name a declared class_money_list input",
        );
    }
    doc["amount"] = json!({"krw": 1});
    for op in ["eq", "ne", "lt", "lte", "gt", "gte"] {
        let expr = json!({op: ["events", "events"]});
        doc["eligibility"] = expr.clone();
        rejects(
            &doc,
            &format!("eligibility.{op}"),
            "lists cannot be compared",
        );
        doc["eligibility"] = json!({"if": false, "then": expr, "else": true});
        rejects(
            &doc,
            &format!("eligibility.then.{op}"),
            "lists cannot be compared",
        );
    }
}
