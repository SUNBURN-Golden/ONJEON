#![allow(dead_code)]
use onjeon_rules_engine::Rule;
use serde_json::{json, Value as J};
use std::path::PathBuf;

pub fn fixtures_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures/rules")
}

pub fn rule_json() -> J {
    let s = std::fs::read_to_string(fixtures_dir().join("fixture-rule-001.json"))
        .expect("rule fixture");
    serde_json::from_str(&s).expect("valid json")
}

pub fn cases() -> Vec<J> {
    let s = std::fs::read_to_string(fixtures_dir().join("fixture-rule-001.cases.json"))
        .expect("cases fixture");
    let v: J = serde_json::from_str(&s).expect("valid json");
    v["cases"].as_array().expect("cases array").clone()
}

/// Observed result in the same shape as the `expect` block of a case.
pub fn observe(rule: &Rule, inputs: &J) -> J {
    let r = rule
        .evaluate(inputs)
        .expect("evaluation must not error on fixture inputs");
    json!({
        "eligibility": serde_json::to_value(r.eligibility).unwrap().as_str().unwrap().to_string(),
        "payout": serde_json::to_value(&r.payout).unwrap(),
        "missing_inputs": r.missing_inputs,
    })
}

pub fn case_passes(rule: &Rule, case: &J) -> bool {
    observe(rule, &case["inputs"]) == case["expect"]
}
