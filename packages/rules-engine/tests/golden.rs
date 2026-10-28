mod common;
use common::*;
use onjeon_rules_engine::Rule;
use serde_json::Value as J;

#[test]
fn golden_table_matches_expert_expectations() {
    let rule = Rule::from_json(&rule_json()).expect("fixture rule loads");
    let mut failures = Vec::new();
    for case in cases() {
        let observed = observe(&rule, &case["inputs"]);
        if observed != case["expect"] {
            failures.push(format!(
                "{}: expected {} but got {}",
                case["id"], case["expect"], observed
            ));
        }
    }
    assert!(
        failures.is_empty(),
        "golden failures:\n{}",
        failures.join("\n")
    );
}

#[test]
fn same_input_gives_byte_identical_output() {
    let rule = Rule::from_json(&rule_json()).unwrap();
    for case in cases() {
        let a = serde_json::to_string(&rule.evaluate(&case["inputs"]).unwrap()).unwrap();
        let b = serde_json::to_string(&rule.evaluate(&case["inputs"]).unwrap()).unwrap();
        assert_eq!(a, b, "result must be reproducible for {}", case["id"]);
    }
}

#[test]
fn trace_records_every_evaluated_node_and_hash_changes_with_input() {
    let rule = Rule::from_json(&rule_json()).unwrap();
    let r1 = rule.evaluate(&serde_json::json!({"elapsed_calendar_days": 0, "target_event": true, "excluded_X": false, "already_paid": false, "insured_amount_krw": 10000000})).unwrap();
    assert!(r1
        .trace
        .iter()
        .any(|t| t.path == "eligibility" && t.op == "all"));
    assert!(r1
        .trace
        .iter()
        .any(|t| t.op == "multiply_rate" && t.result == "5000000 KRW"));
    assert_eq!(r1.input_snapshot_hash.len(), 64);
    let r2 = rule.evaluate(&serde_json::json!({"elapsed_calendar_days": 1, "target_event": true, "excluded_X": false, "already_paid": false, "insured_amount_krw": 10000000})).unwrap();
    assert_ne!(r1.input_snapshot_hash, r2.input_snapshot_hash);
}

#[test]
fn synthetic_fixture_rule_is_fixture_only() {
    let rule = Rule::from_json(&rule_json()).unwrap();
    assert_eq!(rule.publication_state(), "fixture_only");
    assert_eq!(
        rule.source_json()["example_kind"],
        "synthetic_not_a_real_product"
    );
}

fn pinned_hash(file: &str) -> String {
    std::fs::read_to_string(fixtures_dir().join(file))
        .expect("pinned hash fixture")
        .trim()
        .to_string()
}

fn pinned_cases() -> serde_json::Map<String, J> {
    let golden = load_json(&fixtures_dir().join("fixture-rule-001.golden.json"));
    let mut pinned = golden["cases"]
        .as_object()
        .expect("golden cases object")
        .clone();
    // Keep the shared traces intact and extend them for the mutation suite's rounding case.
    let rounding: J = serde_json::from_str(include_str!(
        "fixtures/fixture-rule-001.rounding.golden.json"
    ))
    .expect("rounding golden fixture");
    for (id, value) in rounding["cases"]
        .as_object()
        .expect("rounding cases object")
    {
        assert!(
            pinned.insert(id.clone(), value.clone()).is_none(),
            "{id}: duplicate golden pin"
        );
    }
    // The shared fixture records the legacy display-based hash. This engine-owned
    // pin set replaces only hashes for the intentional snapshot-json-1 migration.
    let current: J = serde_json::from_str(include_str!(
        "fixtures/fixture-rule-001.snapshot-json-1.hashes.json"
    ))
    .expect("canonical snapshot hash pins");
    let hashes = current["hashes"].as_object().expect("hashes object");
    assert_eq!(
        pinned.keys().collect::<std::collections::BTreeSet<_>>(),
        hashes.keys().collect::<std::collections::BTreeSet<_>>()
    );
    for (id, value) in &mut pinned {
        value["input_snapshot_hash"] = hashes[id].clone();
    }
    pinned
}

/// The golden table also pins the audit fields: per-case `trace` and `input_snapshot_hash`
/// (traces in the shared/local golden fixtures, hashes in the snapshot-json-1 pin set)
/// and `rule_content_hash`
/// (in `fixture-rule-001.content_hash`). `expect` stays outcome-only.
#[test]
fn golden_table_pins_trace_and_hashes() {
    let rule = Rule::from_json(&rule_json()).unwrap();
    let pinned = pinned_cases();
    let rule_hash = pinned_hash("fixture-rule-001.content_hash");
    let all = cases();
    assert_eq!(
        pinned.len(),
        all.len(),
        "golden fixtures must pin exactly the cases in cases.json"
    );
    let mut failures = Vec::new();
    for case in &all {
        let id = case["id"].as_str().unwrap();
        let Some(want) = pinned.get(id) else {
            failures.push(format!("{id}: no pinned trace/hash"));
            continue;
        };
        let got = observe_full(&rule, &case["inputs"]);
        let mut expected = case["expect"].clone();
        expected["trace"] = want["trace"].clone();
        expected["input_snapshot_hash"] = want["input_snapshot_hash"].clone();
        expected["rule_content_hash"] = J::String(rule_hash.clone());
        if got != expected {
            failures.push(format!("{id}: expected {expected} but got {got}"));
        }
    }
    assert!(
        failures.is_empty(),
        "golden trace/hash failures:\n{}",
        failures.join("\n")
    );
}

#[test]
fn pinned_input_snapshot_hashes_are_distinct_per_distinct_input() {
    let pinned = pinned_cases();
    let mut by_hash: std::collections::BTreeMap<String, String> = Default::default();
    for case in cases() {
        let id = case["id"].as_str().unwrap().to_string();
        let h = pinned[&id]["input_snapshot_hash"]
            .as_str()
            .unwrap_or_else(|| panic!("{id}: missing pinned input_snapshot_hash"))
            .to_string();
        assert_eq!(h.len(), 64, "{id}");
        if let Some(prev) = by_hash.insert(h, id.clone()) {
            let inputs =
                |n: &str| cases().into_iter().find(|c| c["id"] == n).unwrap()["inputs"].clone();
            assert_eq!(
                inputs(&prev),
                inputs(&id),
                "{prev} and {id} share a hash but differ in inputs"
            );
        }
    }
}

/// Every real rule's `rule_content_hash` is pinned in the shared hashes or replacement catalog, so an edit to
/// a published-style rule cannot change what a result claims to have run without a visible diff.
#[test]
fn real_rule_content_hashes_are_pinned() {
    let mut pinned = load_json(&fixtures_dir().join("real.content_hashes.json"));
    let pinned = pinned["hashes"].as_object_mut().expect("hashes object");
    for (id, replacement) in rule_replacements()["replacements"].as_object().unwrap() {
        assert_eq!(pinned[id], replacement["previous_content_hash"]);
        pinned.insert(id.clone(), replacement["content_hash"].clone());
    }
    let rules = real_rules();
    let have: Vec<&String> = rules.keys().collect();
    let want: Vec<&String> = pinned.keys().collect();
    assert_eq!(
        have, want,
        "pinned set must equal the rules in fixtures/rules/real"
    );
    for (id, rule) in &rules {
        assert_eq!(
            Some(rule.content_hash()),
            pinned[id].as_str(),
            "{id}: rule_content_hash changed; update the shared pin or replacement catalog only if intended"
        );
        // The result reports the same hash that is pinned.
        let case = real_cases().into_iter().find(|(_, r, _)| r == id);
        if let Some((_, _, inputs)) = case {
            let got = observe_full(rule, &inputs);
            assert_eq!(got["rule_content_hash"], pinned[id], "{id}");
        }
    }
}
