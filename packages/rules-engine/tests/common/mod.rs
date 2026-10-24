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
    let v = case_file(std::path::Path::new("fixture-rule-001.cases.json"));
    v["cases"].as_array().expect("cases array").clone()
}

/// Extend a shared case table with engine-owned boundary cases. Supplements inherit the
/// shared file's base inputs and rule ID; their expectations remain hand-authored.
pub fn case_file(relative: &std::path::Path) -> J {
    let mut file = load_json(&fixtures_dir().join(relative));
    let supplement = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures/cases")
        .join(relative);
    if supplement.exists() {
        let extra = load_json(&supplement);
        extend_case_file(&mut file, &extra, relative);
    }
    file
}

pub fn extend_case_file(file: &mut J, extra: &J, relative: &std::path::Path) {
    let cases = file["cases"].as_array_mut().expect("cases array");
    let mut ids: std::collections::BTreeSet<String> = cases
        .iter()
        .map(|c| c["id"].as_str().expect("case ID").to_string())
        .collect();
    for case in extra["cases"].as_array().expect("supplement cases array") {
        let id = case["id"].as_str().expect("supplement case ID");
        assert!(
            ids.insert(id.to_string()),
            "{}: duplicate case ID {id}",
            relative.display()
        );
        cases.push(case.clone());
    }
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

/// `observe` plus the audit fields a regression could silently change: the evaluation
/// `trace`, `rule_content_hash` and `input_snapshot_hash`.
pub fn observe_full(rule: &Rule, inputs: &J) -> J {
    let r = rule
        .evaluate(inputs)
        .expect("evaluation must not error on fixture inputs");
    let mut out = observe(rule, inputs);
    out["trace"] = serde_json::to_value(&r.trace).unwrap();
    out["rule_content_hash"] = json!(r.rule_content_hash);
    out["input_snapshot_hash"] = json!(r.input_snapshot_hash);
    out
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
        let file = case_file(p.strip_prefix(fixtures_dir()).unwrap());
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
