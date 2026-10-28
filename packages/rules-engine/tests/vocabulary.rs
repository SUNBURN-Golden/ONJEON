//! The engine's serialized state names and DSL tokens must exist in the canonical vocabulary
//! (packages/schemas/vocabulary.json). This stops code and documents drifting apart.
use onjeon_rules_engine::rule::{InputType, PUBLICATION_STATES};
use onjeon_rules_engine::{AmountOut, Payout, Rule, Tri};
use serde_json::{json, Value as J};
use std::collections::BTreeSet;

fn axis(id: &str) -> BTreeSet<String> {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../schemas/vocabulary.json");
    let v: J = serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
    let a = v["axes"]
        .as_array()
        .unwrap()
        .iter()
        .find(|a| a["id"] == id)
        .unwrap_or_else(|| panic!("axis {id} missing from vocabulary.json"));
    a["values"]
        .as_array()
        .unwrap()
        .iter()
        .map(|x| x["code"].as_str().unwrap().to_string())
        .collect()
}

fn kind(v: J) -> String {
    v.get("kind")
        .and_then(J::as_str)
        .map(str::to_string)
        .unwrap_or_else(|| v.as_str().unwrap().to_string())
}

#[test]
fn tri_names_are_canonical() {
    let want = axis("tri");
    for t in [Tri::True, Tri::False, Tri::Unknown] {
        assert!(want.contains(&kind(serde_json::to_value(t).unwrap())));
    }
    assert_eq!(want.len(), 3);
}

#[test]
fn payout_names_are_canonical() {
    let want = axis("payout");
    let got: BTreeSet<String> = [
        Payout::NotPayable,
        Payout::Payable {
            amount: AmountOut::Unknown,
        },
        Payout::Undetermined {
            conditional_amount: AmountOut::Unknown,
        },
    ]
    .into_iter()
    .map(|p| kind(serde_json::to_value(p).unwrap()))
    .collect();
    assert_eq!(
        got, want,
        "engine payout kinds and vocabulary payout axis must match exactly"
    );
}

#[test]
fn amount_kind_names_are_canonical() {
    let want = axis("amount_kind");
    let got: BTreeSet<String> = [
        AmountOut::Exact { krw: 1 },
        AmountOut::Range {
            min_krw: 1,
            max_krw: 2,
        },
        AmountOut::Unknown,
    ]
    .into_iter()
    .map(|a| kind(serde_json::to_value(a).unwrap()))
    .collect();
    assert_eq!(got, want);
}

#[test]
fn publication_states_are_canonical() {
    let want = axis("publication_state");
    let got: BTreeSet<String> = PUBLICATION_STATES.iter().map(|s| s.to_string()).collect();
    assert_eq!(got, want);
}

fn doc() -> J {
    json!({
        "rule_id": "fixture-vocabulary", "rule_version": "1", "schema_version": "rule-0.2",
        "inputs": {"money": "money_krw"}, "eligibility": true, "amount": {"krw": 1},
        "unknown_policy": "use_three_valued_logic_never_default_to_zero",
        "evidence_refs": [], "publication_state": "fixture_only"
    })
}

// Exhaustive so adding an InputType requires updating its canonical spelling here.
fn input_name(ty: InputType) -> &'static str {
    match ty {
        InputType::Bool => "bool",
        InputType::Int => "int",
        InputType::MoneyKrw => "money_krw",
        InputType::Date => "date",
        InputType::Str => "string",
        InputType::ClassMoneyList => "class_money_list",
    }
}

#[test]
fn input_types_are_canonical_and_versioned() {
    let mut got = BTreeSet::new();
    for ty in [
        InputType::Bool,
        InputType::Int,
        InputType::MoneyKrw,
        InputType::Date,
        InputType::Str,
        InputType::ClassMoneyList,
    ] {
        let name = input_name(ty);
        got.insert(name.to_string());
        for version in ["rule-0.1", "rule-0.2"] {
            let mut d = doc();
            d["schema_version"] = json!(version);
            d["inputs"] = json!({"value": name});
            let result = Rule::from_json(&d);
            if ty == InputType::ClassMoneyList && version == "rule-0.1" {
                assert!(result
                    .unwrap_err()
                    .to_string()
                    .contains("requires schema_version rule-0.2"));
            } else {
                assert_eq!(result.unwrap().input_types()["value"], ty);
            }
        }
    }
    assert_eq!(got, axis("input_type"));
    let mut d = doc();
    d["inputs"] = json!({"value": "float"});
    assert!(Rule::from_json(&d).is_err());
}

#[test]
fn rounding_modes_are_canonical() {
    let modes = ["floor", "ceil", "half_up", "half_even", "unspecified"];
    assert_eq!(
        modes
            .map(str::to_string)
            .into_iter()
            .collect::<BTreeSet<_>>(),
        axis("rounding")
    );
    for version in ["rule-0.1", "rule-0.2"] {
        for mode in modes.into_iter().chain(["round", "FLOOR", ""]) {
            let mut d = doc();
            d["schema_version"] = json!(version);
            d["amount"] =
                json!({"multiply_rate": [{"krw": 1}, "0.5", {"rounding": mode, "unit": 1}]});
            assert_eq!(
                Rule::from_json(&d).is_ok(),
                modes.contains(&mode),
                "{version}: {mode}"
            );
        }
    }
}

#[test]
fn duration_units_are_canonical() {
    let units = ["day", "calendar_month", "calendar_year"];
    assert_eq!(
        units
            .map(str::to_string)
            .into_iter()
            .collect::<BTreeSet<_>>(),
        axis("duration_unit")
    );
    for version in ["rule-0.1", "rule-0.2"] {
        for unit in units.into_iter().chain(["month", "year", "DAY", ""]) {
            let mut params = json!({"value": 1, "unit": unit});
            if unit != "day" {
                params["month_end"] = json!("clamp");
            }
            let mut d = doc();
            d["schema_version"] = json!(version);
            d["eligibility"] = json!({"eq": [
                {"date_add": [{"date": "2026-01-01"}, params]}, {"date": "2026-01-02"}
            ]});
            assert_eq!(
                Rule::from_json(&d).is_ok(),
                units.contains(&unit),
                "{version}: {unit}"
            );
        }
    }
}

#[test]
fn operator_allowlist_is_canonical_and_versioned() {
    // Each allowed key has a well-typed expression. Literal constructors and the
    // special three-key `if` form are part of the DSL; then/else are not operators.
    let cases = [
        ("all", json!({"all": [true]}), "bool", false),
        ("any", json!({"any": [true]}), "bool", false),
        ("not", json!({"not": false}), "bool", false),
        ("eq", json!({"eq": [1, 1]}), "bool", false),
        ("ne", json!({"ne": [1, 2]}), "bool", false),
        ("lt", json!({"lt": [1, 2]}), "bool", false),
        ("lte", json!({"lte": [1, 2]}), "bool", false),
        ("gt", json!({"gt": [2, 1]}), "bool", false),
        ("gte", json!({"gte": [2, 1]}), "bool", false),
        (
            "if",
            json!({"if": true, "then": {"krw": 1}, "else": {"krw": 0}}),
            "money",
            false,
        ),
        ("input", json!({"input": "money"}), "money", false),
        ("str", json!({"str": "surgery"}), "string", false),
        ("rate", json!({"rate": "0.5"}), "rate", false),
        ("krw", json!({"krw": 1}), "money", false),
        ("date", json!({"date": "2026-01-01"}), "date", false),
        (
            "multiply_rate",
            json!({"multiply_rate": [{"krw": 1}, "0.5", {"rounding": "floor", "unit": 1}]}),
            "money",
            false,
        ),
        (
            "add",
            json!({"add": [{"krw": 1}, {"krw": 2}]}),
            "money",
            false,
        ),
        (
            "min",
            json!({"min": [{"krw": 1}, {"krw": 2}]}),
            "money",
            false,
        ),
        (
            "max",
            json!({"max": [{"krw": 1}, {"krw": 2}]}),
            "money",
            false,
        ),
        (
            "apply_cap",
            json!({"apply_cap": [{"krw": 1}, {"krw": 2}]}),
            "money",
            false,
        ),
        (
            "days_between",
            json!({"days_between": [{"date": "2026-01-01"}, {"date": "2026-01-02"}, {"inclusive_start": true, "inclusive_end": false}]}),
            "int",
            false,
        ),
        (
            "date_add",
            json!({"date_add": [{"date": "2026-01-01"}, {"value": 1, "unit": "day"}]}),
            "date",
            false,
        ),
        (
            "multiply_count",
            json!({"multiply_count": [{"krw": 1}, 2]}),
            "money",
            true,
        ),
        (
            "subtract_floor0",
            json!({"subtract_floor0": [{"krw": 1}, {"krw": 2}]}),
            "money",
            true,
        ),
        (
            "pro_rata",
            json!({"pro_rata": [{"krw": 1}, 1, 2, {"rounding": "floor", "unit": 1}]}),
            "money",
            true,
        ),
        (
            "divide_count",
            json!({"divide_count": [{"krw": 1}, 2, {"rounding": "floor", "unit": 1}]}),
            "money",
            true,
        ),
        (
            "anniversary_band",
            json!({"anniversary_band": [{"date": "2026-01-01"}, {"date": "2026-01-02"}, [[0, "0.5"]], {"boundary": "lower_inclusive"}]}),
            "rate",
            true,
        ),
        ("max_over", json!({"max_over": "events"}), "money", true),
    ];
    let got = cases.iter().map(|(op, ..)| op.to_string()).collect();
    assert_eq!(axis("rule_operator"), got);
    for (op, expr, ty, v02_only) in cases {
        for version in ["rule-0.1", "rule-0.2"] {
            let mut d = doc();
            d["schema_version"] = json!(version);
            if op == "max_over" && version == "rule-0.2" {
                d["inputs"]["events"] = json!("class_money_list");
            }
            match ty {
                "bool" => d["eligibility"] = expr.clone(),
                "int" => d["eligibility"] = json!({"eq": [expr, 1]}),
                "string" => d["eligibility"] = json!({"eq": [expr, {"str": "surgery"}]}),
                "date" => d["eligibility"] = json!({"eq": [expr, {"date": "2026-01-01"}]}),
                "rate" => {
                    d["amount"] = json!({"multiply_rate": [{"krw": 1}, expr, {"rounding": "floor", "unit": 1}]})
                }
                "money" => d["amount"] = expr.clone(),
                _ => unreachable!(),
            }
            let result = Rule::from_json(&d);
            if v02_only && version == "rule-0.1" {
                let error = result.unwrap_err().to_string();
                assert!(
                    error.contains(&format!("operator `{op}` requires schema_version rule-0.2")),
                    "{error}"
                );
            } else {
                result.unwrap_or_else(|e| panic!("{version}: {op}: {e}"));
            }
        }
    }
    for op in ["multiply", "then", "else", "unknown_operator"] {
        let mut d = doc();
        d["amount"] = json!({op: [{"krw": 1}, {"krw": 2}]});
        assert!(Rule::from_json(&d).is_err(), "{op} must be rejected");
    }
}
