//! Audit 2: reversed dates must never become a negative duration that passes a threshold.
use onjeon_rules_engine::{AmountOut, EvalError, Payout, Rule, Tri};
use serde_json::{json, Value};

const FLAGS: [(bool, bool); 4] = [(false, false), (true, false), (false, true), (true, true)];

fn days(start: Value, end: Value, inclusive_start: bool, inclusive_end: bool) -> Value {
    json!({"days_between": [start, end, {"inclusive_start": inclusive_start, "inclusive_end": inclusive_end}]})
}

fn rule(version: &str, eligibility: Value) -> Rule {
    Rule::from_json(&json!({
        "rule_id": "days-between-audit", "rule_version": "1", "schema_version": version,
        "calendar": "Asia/Seoul", "inputs": {"start": "date", "end": "date"},
        "eligibility": eligibility, "amount": {"krw": 1},
        "unknown_policy": "use_three_valued_logic_never_default_to_zero",
        "evidence_refs": [], "publication_state": "fixture_only"
    }))
    .unwrap()
}

fn assert_reversed_error(error: EvalError, expected_path: &str) {
    match error {
        EvalError::Type { path, message } => {
            assert_eq!(path, expected_path);
            assert!(
                message.contains("first date on or before the second"),
                "{message}"
            );
            assert!(message.contains("day(s) earlier"), "{message}");
        }
        other => panic!("expected reversed-date Type error, got {other:?}"),
    }
}

#[test]
fn reversed_dates_cannot_satisfy_comparison_thresholds() {
    for version in ["rule-0.1", "rule-0.2"] {
        for (s, e) in FLAGS {
            for op in ["eq", "ne", "lt", "lte", "gt", "gte"] {
                for threshold in [0, 1, 90, 180] {
                    let rule = rule(
                        version,
                        json!({op: [days(json!("start"), json!("end"), s, e), threshold]}),
                    );
                    for (start, end) in [
                        ("2026-01-02", "2026-01-01"),
                        ("2026-06-30", "2026-01-01"),
                        ("2199-12-31", "1900-01-01"),
                    ] {
                        assert_reversed_error(
                            rule.evaluate(&json!({"start": start, "end": end}))
                                .unwrap_err(),
                            &format!("eligibility.{op}[0]"),
                        );
                    }
                }
            }
        }
    }
}

#[test]
fn reversed_literal_and_computed_dates_are_also_rejected() {
    for version in ["rule-0.1", "rule-0.2"] {
        for (s, e) in FLAGS {
            for start in [
                json!({"date": "2026-01-02"}),
                json!({"date_add": [{"date": "2026-01-01"}, {"value": 1, "unit": "day"}]}),
            ] {
                let rule = rule(
                    version,
                    json!({"lt": [days(start, json!({"date": "2026-01-01"}), s, e), 90]}),
                );
                // The rule is well typed; chronological order is checked when evaluated.
                assert_reversed_error(rule.evaluate(&json!({})).unwrap_err(), "eligibility.lt[0]");
            }
        }
    }
}

#[test]
fn forward_and_same_day_intervals_preserve_all_inclusive_boundaries() {
    for version in ["rule-0.1", "rule-0.2"] {
        // Expected values are in FLAGS order: neither, start only, end only, both.
        for (start, end, expected) in [
            ("2026-01-01", "2026-01-01", [0, 0, 0, 1]),
            ("2026-01-01", "2026-01-02", [0, 1, 1, 2]),
            ("2024-02-28", "2024-03-01", [1, 2, 2, 3]),
            ("2026-01-01", "2026-06-30", [179, 180, 180, 181]),
            ("1900-01-01", "1900-01-01", [0, 0, 0, 1]),
            ("2199-12-31", "2199-12-31", [0, 0, 0, 1]),
        ] {
            for ((s, e), expected) in FLAGS.into_iter().zip(expected) {
                let rule = rule(
                    version,
                    json!({"eq": [days(json!("start"), json!("end"), s, e), expected]}),
                );
                let inputs = json!({"start": start, "end": end});
                let result = rule.evaluate(&inputs).unwrap();
                assert_eq!(
                    result.eligibility,
                    Tri::True,
                    "{version}/{s}/{e}/{start}/{end}"
                );
                assert_eq!(
                    result.payout,
                    Payout::Payable {
                        amount: AmountOut::Exact { krw: 1 }
                    }
                );
                assert!(result.missing_inputs.is_empty());
                let trace = result
                    .trace
                    .iter()
                    .find(|entry| entry.op == "days_between")
                    .unwrap();
                assert_eq!(trace.path, "eligibility.eq[0]");
                assert_eq!(trace.result, expected.to_string());
                assert_eq!(
                    serde_json::to_vec(&result).unwrap(),
                    serde_json::to_vec(&rule.evaluate(&inputs).unwrap()).unwrap()
                );
            }
        }
    }
}

#[test]
fn missing_dates_stay_unknown_and_report_only_missing_endpoints() {
    for version in ["rule-0.1", "rule-0.2"] {
        for (s, e) in FLAGS {
            let rule = rule(
                version,
                json!({"lt": [days(json!("start"), json!("end"), s, e), 90]}),
            );
            for (inputs, missing) in [
                (json!({}), vec!["end", "start"]),
                (json!({"start": null, "end": null}), vec!["end", "start"]),
                (json!({"start": "2026-01-02"}), vec!["end"]),
                (json!({"start": "2026-01-02", "end": null}), vec!["end"]),
                (json!({"end": "2026-01-01"}), vec!["start"]),
                (json!({"start": null, "end": "2026-01-01"}), vec!["start"]),
            ] {
                let result = rule.evaluate(&inputs).unwrap();
                assert_eq!(result.eligibility, Tri::Unknown);
                assert_eq!(
                    result.payout,
                    Payout::Undetermined {
                        conditional_amount: AmountOut::Exact { krw: 1 }
                    }
                );
                assert_eq!(result.missing_inputs, missing);
                assert_eq!(
                    result
                        .trace
                        .iter()
                        .find(|entry| entry.op == "days_between")
                        .unwrap()
                        .result,
                    "unknown"
                );
            }
        }
    }
}
