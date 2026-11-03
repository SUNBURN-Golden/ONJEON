//! Load the proposal originals, not copies in packages/fixtures/ontology.
//! These are fixture_only design cases, never approved service rules.
use onjeon_rules_engine::{AmountOut, Payout, Rule, Tri};
use serde_json::{json, Value as J};
use std::collections::BTreeMap;
use std::path::PathBuf;

const NAMES: [&str; 2] = ["hana-2601-3d-cancer-dx.json", "hi2607-2-5-cancer-dx.json"];

fn ontology_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../docs/blueprint/proposals/온톨로지")
}

fn pins() -> BTreeMap<String, String> {
    serde_json::from_str(
        &std::fs::read_to_string(ontology_dir().join("rule_content_hashes.json")).unwrap(),
    )
    .unwrap()
}

fn load(name: &str) -> Rule {
    Rule::from_json_str(&std::fs::read_to_string(ontology_dir().join("규칙").join(name)).unwrap())
        .unwrap()
}

fn inputs(name: &str) -> J {
    let mut inputs = json!({
        "contract_date": "2026-01-01", "diagnosis_date": "2027-01-01",
        "policy_end_date": "2046-01-01", "dx_in_category": true,
        "already_paid": false, "insured_amount_krw": 10000001
    });
    if name.starts_with("hana") {
        inputs["is_initial_contract"] = json!(true);
        inputs["renewal_date"] = J::Null;
    }
    inputs
}

fn exact(krw: i64) -> Payout {
    Payout::Payable {
        amount: AmountOut::Exact { krw },
    }
}

#[test]
fn original_inventory_and_engine_content_hashes_are_pinned() {
    let mut files: Vec<_> = std::fs::read_dir(ontology_dir().join("규칙"))
        .unwrap()
        .map(|entry| entry.unwrap().path())
        .filter(|path| path.extension().is_some_and(|ext| ext == "json"))
        .map(|path| path.file_name().unwrap().to_str().unwrap().to_owned())
        .collect();
    files.sort();
    assert_eq!(files, NAMES, "review any rule addition/removal explicitly");
    let pins = pins();
    assert_eq!(pins.keys().map(String::as_str).collect::<Vec<_>>(), NAMES);
    for name in NAMES {
        let rule = load(name);
        assert_eq!(rule.content_hash(), pins[name], "{name}");
        assert_eq!(rule.publication_state(), "fixture_only");
        assert_eq!(
            rule.source_json()["example_kind"],
            "ontology_case_validation"
        );
        assert_eq!(rule.source_json()["schema_version"], "rule-0.1");
        let result = rule.evaluate(&inputs(name)).unwrap();
        assert_eq!(result.rule_content_hash, pins[name]);
        assert_eq!(result.rule_id, name.trim_end_matches(".json"));
        assert_eq!(result.rule_version, "v1-ontology-case");
        assert_eq!(result.schema_version, "rule-0.1");
        assert_eq!(result.release_id, None);
        assert_eq!(
            json!(result.evidence_refs),
            rule.source_json()["evidence_refs"]
        );
        assert!(!result.evidence_refs.is_empty());
        assert!(!result.trace.is_empty());
        assert_eq!(
            serde_json::to_vec(&result).unwrap(),
            serde_json::to_vec(&load(name).evaluate(&inputs(name)).unwrap()).unwrap(),
            "{name}: reloading must reproduce all result bytes"
        );
    }
}

#[test]
fn waiting_reduction_expiry_exclusion_and_renewal_boundaries() {
    for name in NAMES {
        let rule = load(name);
        let reduced = Payout::Payable {
            amount: AmountOut::Range {
                min_krw: 5000000,
                max_krw: 5000001,
            },
        };
        let early = if name.starts_with("hana") {
            reduced
        } else {
            exact(10000001)
        };
        for (date, payout) in [
            ("2026-03-31", Payout::NotPayable), // contract + 89 days
            ("2026-04-01", early.clone()),      // contract + 90 days, inclusive
            ("2026-12-31", early),
            ("2027-01-01", exact(10000001)), // one-year reduction ends
            ("2046-01-01", exact(10000001)), // last covered day, inclusive
            ("2046-01-02", Payout::NotPayable),
        ] {
            let mut input = inputs(name);
            input["diagnosis_date"] = json!(date);
            let result = rule.evaluate(&input).unwrap();
            assert_eq!(result.payout, payout, "{name}: {date}");
            assert!(result.missing_inputs.is_empty());
        }
        for (key, value) in [("already_paid", true), ("dx_in_category", false)] {
            let mut input = inputs(name);
            input[key] = json!(value);
            assert_eq!(
                rule.evaluate(&input).unwrap().payout,
                Payout::NotPayable,
                "{name}: {key}"
            );
        }
        if name.starts_with("hana") {
            for (date, payout) in [
                ("2026-01-31", Payout::NotPayable),
                ("2026-02-01", exact(10000001)),
            ] {
                let mut input = inputs(name);
                input["is_initial_contract"] = json!(false);
                input["renewal_date"] = json!("2026-02-01");
                input["diagnosis_date"] = json!(date);
                assert_eq!(
                    rule.evaluate(&input).unwrap().payout,
                    payout,
                    "renewal: {date}"
                );
            }
        }
    }
}

#[test]
fn unknown_inputs_remain_unknown_for_both_original_rules() {
    for name in NAMES {
        let rule = load(name);
        for key in ["dx_in_category", "insured_amount_krw"] {
            let mut null = inputs(name);
            null[key] = J::Null;
            let mut missing = null.clone();
            missing.as_object_mut().unwrap().remove(key);
            let result = rule.evaluate(&null).unwrap();
            assert_eq!(result, rule.evaluate(&missing).unwrap(), "{name}: {key}");
            assert_eq!(result.missing_inputs, [key]);
            if key == "dx_in_category" {
                assert_eq!(result.eligibility, Tri::Unknown);
                assert_eq!(
                    result.payout,
                    Payout::Undetermined {
                        conditional_amount: AmountOut::Exact { krw: 10000001 },
                    }
                );
            } else {
                assert_eq!(result.eligibility, Tri::True);
                assert_eq!(
                    result.payout,
                    Payout::Payable {
                        amount: AmountOut::Unknown
                    }
                );
            }
        }
    }
}

#[test]
fn same_version_logic_or_evidence_edits_break_the_pinned_hash() {
    for name in NAMES {
        let original = load(name);
        for key in ["amount", "evidence_refs"] {
            let mut edited = original.source_json().clone();
            edited[key] = if key == "amount" {
                json!({"krw": 1})
            } else {
                json!(["changed:clause"])
            };
            let changed = Rule::from_json(&edited).unwrap();
            assert_eq!(
                changed.source_json()["rule_version"],
                original.source_json()["rule_version"]
            );
            assert_ne!(changed.content_hash(), pins()[name], "{name}: {key}");
            assert_ne!(
                changed.evaluate(&inputs(name)).unwrap().rule_content_hash,
                pins()[name]
            );
        }
    }
}
