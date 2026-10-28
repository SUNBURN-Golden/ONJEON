//! Audits 2/3: dates must use zero-padded ASCII YYYY-MM-DD, with no signed aliases.
use onjeon_rules_engine::{AmountOut, EvalError, Payout, Rule};
use serde_json::{json, Value};

const NON_CANONICAL_DATES: &[&str] = &[
    "2026-+1-+5",
    "2026-+1-05",
    "2026-01-+5",
    "2024-+2-+9",
    "2024-+2-09",
    "2024-02-+9",
    "+202-01-05",
    "2026-1-5",
    "2026-1-05",
    "2026-01-5",
    "2026-001-05",
    "2026/01/05",
    "2026- 1-05",
    "2026-01-5 ",
    "2026-01-05\n",
    "２０２６-０１-０５",
    "2026-٠١-٠٥",
];

fn rule(version: &str, date: &str) -> Value {
    json!({
        "rule_id": "date-format", "rule_version": "1", "schema_version": version,
        "calendar": "Asia/Seoul", "inputs": {"event_date": "date"},
        "eligibility": {"eq": ["event_date", {"date": date}]},
        "amount": {"krw": 1},
        "unknown_policy": "use_three_valued_logic_never_default_to_zero",
        "evidence_refs": [], "publication_state": "fixture_only"
    })
}

#[test]
fn non_canonical_date_literals_are_rejected_at_load() {
    for version in ["rule-0.1", "rule-0.2"] {
        for &date in NON_CANONICAL_DATES {
            let error = Rule::from_json(&rule(version, date)).unwrap_err();
            assert_eq!(error.path, "eligibility.eq[1].date");
            assert!(error.message.contains("valid YYYY-MM-DD date"));
        }
    }
}

#[test]
fn non_canonical_date_inputs_are_rejected_at_evaluation() {
    for version in ["rule-0.1", "rule-0.2"] {
        let rule = Rule::from_json(&rule(version, "2024-02-09")).unwrap();
        for &date in NON_CANONICAL_DATES {
            let error = rule.evaluate(&json!({"event_date": date})).unwrap_err();
            assert!(
                matches!(error, EvalError::BadInput { ref name, .. } if name == "event_date"),
                "{version}: {date}: {error}"
            );
        }
    }
}

#[test]
fn canonical_date_literals_and_inputs_still_evaluate() {
    for version in ["rule-0.1", "rule-0.2"] {
        for date in [
            "1900-01-01",
            "2024-02-09",
            "2024-02-29",
            "2026-01-05",
            "2199-12-31",
        ] {
            let rule = Rule::from_json(&rule(version, date)).unwrap();
            assert_eq!(
                rule.evaluate(&json!({"event_date": date})).unwrap().payout,
                Payout::Payable {
                    amount: AmountOut::Exact { krw: 1 }
                }
            );
        }
    }
}

#[test]
fn date_aliases_cannot_produce_alternate_rule_hashes() {
    for version in ["rule-0.1", "rule-0.2"] {
        let canonical = Rule::from_json(&rule(version, "2026-01-05")).unwrap();
        let source = canonical.source_json().clone();
        let text = serde_json::to_string_pretty(&source).unwrap();
        let reloaded = Rule::from_json_str(&text).unwrap();
        assert_eq!(reloaded.content_hash(), canonical.content_hash());
        let result = reloaded
            .evaluate(&json!({"event_date": "2026-01-05"}))
            .unwrap();
        assert_eq!(result.rule_content_hash, canonical.content_hash());

        // Changing only the date's spelling must fail validation, rather than
        // create the same executable logic with a different content hash.
        for &date in NON_CANONICAL_DATES {
            let mut alias = source.clone();
            alias["eligibility"]["eq"][1]["date"] = json!(date);
            let text = serde_json::to_string(&alias).unwrap();
            for encoded in [text.clone(), text.replace('+', "\\u002b")] {
                let error = Rule::from_json_str(&encoded).unwrap_err();
                assert_eq!(error.path, "eligibility.eq[1].date");
                assert!(error.message.contains("valid YYYY-MM-DD date"));
            }
        }
        assert_eq!(canonical.source_json(), &source);
    }
}
