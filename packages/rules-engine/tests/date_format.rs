//! Audit 2: date literals and evaluation inputs must use digits-only YYYY-MM-DD.
use onjeon_rules_engine::{AmountOut, EvalError, Payout, Rule};
use serde_json::{json, Value};

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
fn signed_date_literals_are_rejected_at_load() {
    for version in ["rule-0.1", "rule-0.2"] {
        for date in ["2024-+2-+9", "2024-+2-09", "2024-02-+9"] {
            let error = Rule::from_json(&rule(version, date)).unwrap_err();
            assert_eq!(error.path, "eligibility.eq[1].date");
            assert!(error.message.contains("valid YYYY-MM-DD date"));
        }
    }
}

#[test]
fn signed_date_inputs_are_rejected_at_evaluation() {
    for version in ["rule-0.1", "rule-0.2"] {
        let rule = Rule::from_json(&rule(version, "2024-02-09")).unwrap();
        for date in ["2024-+2-+9", "2024-+2-09", "2024-02-+9"] {
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
        for date in ["1900-01-01", "2024-02-09", "2024-02-29", "2199-12-31"] {
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
