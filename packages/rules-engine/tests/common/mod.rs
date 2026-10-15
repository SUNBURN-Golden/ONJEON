#![allow(dead_code)]
use onjeon_rules_engine::Rule;
use serde_json::{json, Map, Value as J};
use std::collections::BTreeMap;
use std::path::PathBuf;

pub fn fixtures_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures/rules")
}

pub fn rule_json() -> J {
    let s = std::fs::read_to_string(fixtures_dir().join("fixture-rule-001.json"))
        .expect("rule fixture");
    let j: J = serde_json::from_str(&s).expect("valid json");
    assert_eq!(
        j["publication_state"], "fixture_only",
        "fixture-rule-001.json is synthetic and must never be publishable"
    );
    assert_eq!(
        j["example_kind"], "synthetic_not_a_real_product",
        "fixture-rule-001.json must keep its synthetic marker"
    );
    j
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

pub fn real_dir() -> PathBuf {
    fixtures_dir().join("real")
}

pub fn load_json(path: &PathBuf) -> J {
    serde_json::from_str(&std::fs::read_to_string(path).expect("readable")).expect("valid json")
}

/// Every rule in `fixtures/rules/real`, keyed by `rule_id`.
pub fn real_rules() -> BTreeMap<String, Rule> {
    let mut out = BTreeMap::new();
    for e in std::fs::read_dir(real_dir()).unwrap() {
        let p = e.unwrap().path();
        let name = p.file_name().unwrap().to_string_lossy().to_string();
        if name.ends_with(".json") && !name.ends_with(".cases.json") {
            let rule = Rule::from_json(&load_json(&p)).unwrap_or_else(|e| panic!("{name}: {e}"));
            out.insert(rule.rule_id().to_string(), rule);
        }
    }
    out
}

/// A case's `base` inputs with its per-case `set` overrides applied.
pub fn merged(base: &J, set: Option<&J>) -> J {
    let mut m: Map<String, J> = base.as_object().cloned().unwrap_or_default();
    if let Some(J::Object(s)) = set {
        for (k, v) in s {
            m.insert(k.clone(), v.clone());
        }
    }
    J::Object(m)
}

/// Every case of every `real/*.cases.json` as `(case, rule_id, full inputs)`.
pub fn real_cases() -> Vec<(J, String, J)> {
    let mut paths: Vec<PathBuf> = std::fs::read_dir(real_dir())
        .unwrap()
        .map(|e| e.unwrap().path())
        .filter(|p| p.to_string_lossy().ends_with(".cases.json"))
        .collect();
    paths.sort();
    let mut out = Vec::new();
    for p in paths {
        let file = load_json(&p);
        for case in file["cases"].as_array().unwrap() {
            let rule_id = case["rule"]
                .as_str()
                .or_else(|| file["rule_id"].as_str())
                .unwrap_or_else(|| panic!("{}: case {} names no rule", p.display(), case["id"]))
                .to_string();
            let inputs = merged(&file["base"], case.get("set"));
            out.push((case.clone(), rule_id, inputs));
        }
    }
    out
}
