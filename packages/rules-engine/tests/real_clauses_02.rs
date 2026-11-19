//! Execute the current V1 clause encodings with the same public loader and evaluator as v0.1.
mod common;
use common::{load_json, merged, validate_case_keys};
use onjeon_rules_engine::{ContractEffectOut, EvalError, Rule};
use serde_json::json;
use std::collections::BTreeSet;
use std::path::Path;

const DIR: &str = "packages/rules-engine/tests/fixtures/real-0.2";

// Pin coverage independently of the files on disk. Each named operator must actually execute.
const CLAUSES: &[(&str, &str, usize, &str)] = &[
    ("kb-driver-fine", "kb_driver#c_fine_art3", 9, "pro_rata"),
    (
        "kb-driver-lawyer-fee",
        "kb_driver#c_lawyer_11_12",
        7,
        "divide_count",
    ),
    (
        "kb-driver-injury-hospital-daily",
        "kb_driver#c_care_art1",
        7,
        "multiply_count",
    ),
    (
        "kyobo-silson-outpatient",
        "kyobo_silson#c_art3_outpatient",
        7,
        "subtract_floor0",
    ),
    (
        "kyobo-cancer-simultaneous-surgery",
        "kyobo_cancer#c_surg_art5_3",
        7,
        "max_over",
    ),
    (
        "kyobo-wholelife-disease-death",
        "kyobo_wholelife#c_annex1_disease",
        10,
        "anniversary_band",
    ),
    (
        "kyobo-cancer-death-reserve",
        "kyobo_cancer#c_main_annex1_note2",
        4,
        "contract_effect",
    ),
];

#[test]
fn real_02_clauses_match_their_sources_cases_and_executed_operators() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let dir = root.join(DIR);
    let expected_files: BTreeSet<_> = CLAUSES
        .iter()
        .flat_map(|(id, ..)| [format!("{id}.json"), format!("{id}.cases.json")])
        .collect();
    let files: BTreeSet<_> = dir
        .read_dir()
        .unwrap()
        .map(|entry| entry.unwrap().file_name().into_string().unwrap())
        .collect();
    assert_eq!(files, expected_files);
    for &(id, primary_ref, count, operator) in CLAUSES {
        let file = format!("{DIR}/{id}.json");
        let source = std::fs::read_to_string(root.join(&file)).unwrap();
        let rule = Rule::from_json_str(&source).unwrap_or_else(|err| panic!("{id}: {err}"));
        assert_eq!(rule.rule_id(), id);
        assert_eq!(rule.schema_version(), "rule-0.2");
        assert_eq!(rule.publication_state(), "fixture_only");
        assert_eq!(
            rule.source_json()["example_kind"],
            "real_clause_design_validation"
        );
        assert!(
            rule.evidence_refs().iter().any(|r| r == primary_ref),
            "{id}"
        );
        let (family, _) = primary_ref.split_once('#').unwrap();
        let encoded =
            load_json(&root.join(format!("docs/blueprint/validation/encoded/{family}.json")));
        let entries: Vec<_> = encoded["rules"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|entry| entry["rule_id"] == id)
            .collect();
        assert_eq!(
            entries.len(),
            1,
            "{id} must resolve to one current encoding"
        );
        assert_eq!(entries[0]["file"], file);
        assert_eq!(entries[0]["cases"], count);

        let case_path = dir.join(format!("{id}.cases.json"));
        let table = load_json(&case_path);
        validate_case_keys(&table, true, &case_path);
        assert_eq!(table["rule_id"], id);
        assert_eq!(table["rule_content_hash"], rule.content_hash());
        let cases = table["cases"].as_array().unwrap();
        assert_eq!(cases.len(), count);
        let mut case_ids = BTreeSet::new();
        let mut exercised = false;
        for case in cases {
            let name = case["id"].as_str().unwrap();
            assert!(case_ids.insert(name), "{id}: duplicate {name}");
            assert!(
                case.get("rule").is_none(),
                "{id}/{name}: one rule per table"
            );
            let inputs = merged(&table["base"], Some(&case["set"]));
            let result = rule
                .evaluate(&inputs)
                .unwrap_or_else(|err| panic!("{id}/{name}: {err}"));
            let mut actual = json!({
                "eligibility": result.eligibility,
                "payout": result.payout,
                "missing_inputs": result.missing_inputs
            });
            if !result.amount_issues.is_empty() {
                actual["amount_issues"] = json!(result.amount_issues);
            }
            if result.contract_effect != ContractEffectOut::None {
                actual["contract_effect"] = json!(result.contract_effect);
            }
            assert_eq!(actual, case["expect"], "{id}/{name}");
            assert_eq!(result.rule_content_hash, rule.content_hash());
            assert_eq!(result.evidence_refs, rule.evidence_refs());
            exercised |= result.trace.iter().any(|entry| entry.op == operator)
                || (operator == "contract_effect"
                    && matches!(result.contract_effect, ContractEffectOut::Applies { .. }));
        }
        assert!(exercised, "{id} never exercised {operator}");
    }
}

#[test]
fn kb_fine_prorates_only_excess_liability_and_rejects_a_precomputed_share() {
    let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/real-0.2");
    let source = std::fs::read_to_string(dir.join("kb-driver-fine.json")).unwrap();
    let rule = Rule::from_json_str(&source).unwrap();
    let mut inputs = load_json(&dir.join("kb-driver-fine.cases.json"))["base"].clone();
    inputs["fine_final_krw"] = json!(30_000_000);
    inputs["has_other_contracts"] = json!(true);
    // At equality the amount alone cannot distinguish a division from paying the standalone cap.
    for (other, prorated) in [(9_999_999, false), (10_000_000, false), (10_000_001, true)] {
        inputs["other_contracts_liability_krw"] = json!(other);
        let result = rule.evaluate(&inputs).unwrap();
        assert_eq!(
            result.trace.iter().any(|entry| entry.op == "pro_rata"),
            prorated
        );
    }
    let err = rule
        .evaluate(&json!({"pro_rata_amount_krw": 1}))
        .unwrap_err();
    assert!(matches!(err, EvalError::UnknownInput(name) if name == "pro_rata_amount_krw"));
}

#[test]
fn wholelife_anniversary_table_preserves_existing_clause_cases() {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures/real-0.2/kyobo-wholelife-disease-death.json");
    let rule = Rule::from_json_str(&std::fs::read_to_string(path).unwrap()).unwrap();
    let mut covered = BTreeSet::new();
    for (case, id, inputs) in common::real_cases() {
        if id == rule.rule_id() {
            assert_eq!(
                common::observe(&rule, &inputs),
                case["expect"],
                "{}",
                case["id"]
            );
            covered.insert(case["id"].as_str().unwrap().to_owned());
        }
    }
    assert!(covered.contains("w34_g13_pending_leap_day_self_harm_two_years"));
}
