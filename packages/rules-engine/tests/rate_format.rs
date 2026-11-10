//! Audit 5: decimal literals need digits on both sides of a decimal point.
use onjeon_rules_engine::{AmountOut, Payout, Rule};
use serde_json::{json, Value};

const INVALID_RATES: &[&str] = &[
    "5.",
    ".5",
    "0.",
    ".0",
    ".",
    "",
    "1..5",
    "1.2.3",
    "+5",
    "-5",
    " 5",
    "5 ",
    "5\n",
    "1e2",
    "５",
    "0.５",
    "٠.٥",
    "1000000000",
    "0.0000000001",
];

fn rule(version: &str, rate: Value) -> Value {
    json!({
        "rule_id": "rate-format", "rule_version": "1", "schema_version": version,
        "inputs": {}, "eligibility": true,
        "amount": {"multiply_rate": [{"krw": 1_000_000_000}, rate,
            {"rounding": "floor", "unit": 1}]},
        "unknown_policy": "use_three_valued_logic_never_default_to_zero",
        "evidence_refs": [], "publication_state": "fixture_only"
    })
}

fn band(rate: &str) -> Value {
    json!({"anniversary_band": [
        {"date": "2026-01-05"}, {"date": "2026-01-05"},
        [[0, rate]], {"boundary": "lower_inclusive"}
    ]})
}

fn rejects(doc: &Value, path: &str, message: &str) {
    let text = serde_json::to_string(doc).unwrap();
    // JSON escapes must not provide another way to load an invalid spelling.
    let escaped = text.replace('.', "\\u002e");
    assert_eq!(serde_json::from_str::<Value>(&escaped).unwrap(), *doc);
    for result in [
        Rule::from_json(doc),
        Rule::from_json_str(&text),
        Rule::from_json_str(&escaped),
    ] {
        let error = result.expect_err(&format!("must reject {doc}"));
        assert_eq!(error.path, path, "{doc}: {error}");
        assert!(error.message.contains(message), "{doc}: {error}");
    }
}

#[test]
fn incomplete_rate_literals_cannot_load_or_acquire_content_hashes() {
    for version in ["rule-0.1", "rule-0.2"] {
        for &rate in INVALID_RATES {
            for (expr, suffix) in [(json!(rate), ""), (json!({"rate": rate}), ".rate")] {
                let mut doc = rule(version, expr);
                rejects(&doc, &format!("amount.multiply_rate[1]{suffix}"), "decimal");
                // Even a branch that evaluation would skip must be validated.
                doc["amount"] = json!({"if": false, "then": doc["amount"], "else": {"krw": 1}});
                rejects(
                    &doc,
                    &format!("amount.then.multiply_rate[1]{suffix}"),
                    "decimal",
                );
            }
        }
    }
}

#[test]
fn anniversary_bands_reject_invalid_rates_in_all_rows() {
    for &rate in INVALID_RATES {
        let mut expr = band(rate);
        let doc = rule("rule-0.2", expr.clone());
        rejects(
            &doc,
            "amount.multiply_rate[1].anniversary_band[2][0]",
            "decimal rate",
        );
        // The future band is not selected for the fixed evaluation date.
        expr["anniversary_band"][2] = json!([[0, "0.5"], [1, rate]]);
        rejects(
            &rule("rule-0.2", expr),
            "amount.multiply_rate[1].anniversary_band[2][1]",
            "decimal rate",
        );
    }
}

#[test]
fn complete_rates_preserve_payouts_source_hashes_and_reload_determinism() {
    for version in ["rule-0.1", "rule-0.2"] {
        for (rate, krw) in [
            ("0", 0),
            ("1", 1_000_000_000),
            ("5", 5_000_000_000),
            ("5.0", 5_000_000_000),
            ("0.5", 500_000_000),
            ("0.50", 500_000_000),
            ("0005.00", 5_000_000_000),
            ("0.000000001", 1),
            ("999999999.999999999", 999_999_999_999_999_999),
        ] {
            let mut forms = vec![json!(rate), json!({"rate": rate})];
            if version == "rule-0.2" {
                forms.push(band(rate));
            }
            for expr in forms {
                let doc = rule(version, expr);
                let loaded = Rule::from_json(&doc).unwrap();
                let reloaded =
                    Rule::from_json_str(&serde_json::to_string_pretty(&doc).unwrap()).unwrap();
                assert_eq!(loaded.source_json(), &doc);
                assert_eq!(loaded.content_hash(), reloaded.content_hash());
                let result = loaded.evaluate(&json!({})).unwrap();
                assert_eq!(
                    result.payout,
                    Payout::Payable {
                        amount: AmountOut::Exact { krw }
                    }
                );
                assert_eq!(result.rule_content_hash, loaded.content_hash());
                assert_eq!(
                    serde_json::to_vec(&result).unwrap(),
                    serde_json::to_vec(&reloaded.evaluate(&json!({})).unwrap()).unwrap()
                );
            }
        }
    }
}

#[test]
fn invalid_rate_spellings_remain_valid_declared_input_names_and_strings() {
    for version in ["rule-0.1", "rule-0.2"] {
        for name in [".5", "5."] {
            let mut doc = rule(version, json!("0.5"));
            doc["inputs"] = json!({name: "money_krw"});
            doc["amount"]["multiply_rate"][0] = json!(name);
            doc["eligibility"] = json!({"eq": [{"str": name}, {"str": name}]});
            let loaded = Rule::from_json(&doc).unwrap();
            assert_eq!(
                loaded.evaluate(&json!({name: 100})).unwrap().payout,
                Payout::Payable {
                    amount: AmountOut::Exact { krw: 50 }
                }
            );
            // Explicit rate syntax cannot resolve to a declared input.
            doc["amount"]["multiply_rate"][1] = json!({"rate": name});
            rejects(&doc, "amount.multiply_rate[1].rate", "decimal");
        }
    }
}
