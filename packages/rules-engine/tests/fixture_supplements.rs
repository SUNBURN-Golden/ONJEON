//! Boundary cases live with the engine while shared fixtures stay reusable by other tools.
mod common;
use common::*;
use onjeon_rules_engine::Rule;
use serde_json::json;
use std::path::{Path, PathBuf};

#[test]
fn every_supplement_extends_an_existing_table_without_changing_shared_cases() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/cases");
    let mut added = 0;
    for dir in [&root, &root.join("real")] {
        for entry in std::fs::read_dir(dir).unwrap() {
            let path = entry.unwrap().path();
            if path.is_dir() {
                continue;
            }
            let relative = path.strip_prefix(&root).unwrap();
            let original = load_json(&fixtures_dir().join(relative));
            let extra = load_json(&path);
            assert_eq!(extra.as_object().unwrap().len(), 1, "cases only");
            let mut combined = case_file(relative);
            let cases = combined["cases"].as_array_mut().unwrap();
            let original_cases = original["cases"].as_array().unwrap();
            assert_eq!(&cases[..original_cases.len()], original_cases);
            assert_eq!(
                &cases[original_cases.len()..],
                extra["cases"].as_array().unwrap()
            );
            added += cases.len() - original_cases.len();
            *cases = original_cases.clone();
            assert_eq!(
                combined, original,
                "base inputs and rule metadata preserved"
            );
        }
    }
    assert_eq!(added, 69, "all mutation boundary cases must remain loaded");
}

#[test]
fn supplemental_cases_inherit_base_inputs_and_apply_their_overrides() {
    let rule_id = "kyobo-small-cancer-skin";
    let file = case_file(Path::new("real/kyobo-small-cancer-skin.cases.json"));
    assert_eq!(file["rule_id"], rule_id);
    let (case, id, inputs) = real_cases()
        .into_iter()
        .find(|(case, ..)| case["id"] == "s16_odd_amount_year1_is_a_range")
        .unwrap();
    assert_eq!(id, rule_id);
    let mut expected_inputs = file["base"].clone();
    expected_inputs["rider_amount_krw"] = json!(10000001);
    assert_eq!(inputs, expected_inputs);
    assert_eq!(observe(&real_rules()[rule_id], &inputs), case["expect"]);
}

#[test]
#[should_panic(expected = "duplicate case ID existing")]
fn supplement_cannot_shadow_a_shared_case() {
    let mut file = json!({"cases": [{"id": "existing"}]});
    extend_case_file(
        &mut file,
        &json!({"cases": [{"id": "existing"}]}),
        Path::new("example.cases.json"),
    );
}

#[test]
#[should_panic(expected = "duplicate case ID repeated")]
fn duplicate_ids_within_a_supplement_are_rejected() {
    let mut file = json!({"cases": []});
    extend_case_file(
        &mut file,
        &json!({"cases": [{"id": "repeated"}, {"id": "repeated"}]}),
        Path::new("example.cases.json"),
    );
}

#[test]
fn wholelife_replacements_add_only_the_coverage_start_guard_and_kill_the_original_bug() {
    let rules = real_rules();
    let replacements = rule_replacements();
    let replacements = replacements["replacements"].as_object().unwrap();
    assert_eq!(replacements.len(), 2);
    for kind in ["disease", "accident"] {
        let id = format!("kyobo-wholelife-{kind}-death");
        let shared = load_json(&real_dir().join(format!("{id}.json")));
        let mut corrected = rules[&id].source_json().clone();
        let guard = corrected["eligibility"]["all"]
            .as_array_mut()
            .unwrap()
            .remove(0);
        assert_eq!(guard, json!({"gte": ["death_date", "coverage_start_date"]}));
        assert_eq!(corrected, shared, "{id}: no unrelated rule changes");
        assert_ne!(replacements[&id]["source"], replacements[&id]["supersedes"]);
        let original = Rule::from_json(&shared).unwrap();
        let mut regressions = 0;
        for (case, rule_id, inputs) in real_cases() {
            if rule_id != id {
                continue;
            }
            assert_eq!(observe(&rules[&id], &inputs), case["expect"]);
            if observe(&original, &inputs) != case["expect"] {
                regressions += 1;
            }
        }
        // Before contract, before a delayed coverage start, and unknown start.
        assert_eq!(regressions, 3, "{id}: original bug must remain detectable");
    }
}

#[test]
fn wholelife_missing_coverage_start_is_undetermined_like_null() {
    let rules = real_rules();
    let mut checked = 0;
    for (case, id, mut inputs) in real_cases() {
        if case["id"]
            .as_str()
            .unwrap()
            .ends_with("unknown_coverage_start")
        {
            assert!(inputs
                .as_object_mut()
                .unwrap()
                .remove("coverage_start_date")
                .unwrap()
                .is_null());
            assert_eq!(observe(&rules[&id], &inputs), case["expect"]);
            checked += 1;
        }
    }
    assert_eq!(checked, 2);
}
