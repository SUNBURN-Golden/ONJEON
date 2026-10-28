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
    for case in cases() {
        assert_reproducible(
            &rule_json(),
            &rule_json(),
            &case["inputs"],
            case["id"].as_str().unwrap(),
        );
    }
}

/// Write raw JSON rather than rebuilding a Map: the default BTreeMap would sort a
/// reversed insertion sequence before it ever reached the rule/input loader.
/// Object keys are permuted recursively, including objects inside arrays; array
/// elements retain their order because expression operand order is meaningful.
fn ordered_json(value: &J, reverse: bool) -> String {
    match value {
        J::Object(map) => {
            let mut keys: Vec<_> = map.keys().collect();
            keys.sort();
            if reverse {
                keys.reverse();
            }
            let entries: Vec<_> = keys
                .into_iter()
                .map(|key| {
                    format!(
                        "{}:{}",
                        serde_json::to_string(key).unwrap(),
                        ordered_json(&map[key], reverse)
                    )
                })
                .collect();
            format!("{{{}}}", entries.join(","))
        }
        J::Array(items) => format!(
            "[{}]",
            items
                .iter()
                .map(|v| ordered_json(v, reverse))
                .collect::<Vec<_>>()
                .join(",")
        ),
        _ => serde_json::to_string(value).unwrap(),
    }
}

fn result_bytes(rule: &Rule, inputs: &J) -> Vec<u8> {
    // Compare the entire public result: trace, blockers, versions, evidence and both
    // hashes as well as eligibility/payout. `observe` deliberately omits audit fields.
    serde_json::to_vec(&rule.evaluate(inputs).unwrap()).unwrap()
}

fn assert_reproducible(source: &J, reloaded: &J, inputs: &J, id: &str) {
    let rule = Rule::from_json(source).unwrap();
    let expected = result_bytes(&rule, inputs);
    assert_eq!(
        expected,
        result_bytes(&rule, inputs),
        "{id}: repeat evaluation"
    );
    assert_eq!(source, reloaded, "{id}: disk reload changed source");
    assert_eq!(
        expected,
        result_bytes(&Rule::from_json(reloaded).unwrap(), inputs),
        "{id}: reload"
    );

    // Exercise rule and input ordering independently, so coupled order-dependent
    // bugs cannot cancel each other out. Parse fresh JSON and load a fresh Rule.
    assert_ne!(
        ordered_json(source, false),
        ordered_json(source, true),
        "{id}: rule permutation must change wire bytes"
    );
    // The synthetic all-unknown case has no keys to permute.
    if inputs.as_object().unwrap().len() > 1 {
        assert_ne!(
            ordered_json(inputs, false),
            ordered_json(inputs, true),
            "{id}: input permutation must change wire bytes"
        );
    }
    for reverse_rule in [false, true] {
        for reverse_input in [false, true] {
            let rule_json: J = serde_json::from_str(&ordered_json(reloaded, reverse_rule)).unwrap();
            let input_json: J = serde_json::from_str(&ordered_json(inputs, reverse_input)).unwrap();
            assert_eq!(
                &rule_json, source,
                "{id}: permutation must preserve rule values"
            );
            assert_eq!(
                &input_json, inputs,
                "{id}: permutation must preserve input values"
            );
            assert_eq!(
                expected,
                result_bytes(&Rule::from_json(&rule_json).unwrap(), &input_json),
                "{id}: rule reversed={reverse_rule}, input reversed={reverse_input}"
            );
        }
    }
}

#[test]
fn real_results_are_byte_identical_after_disk_reload_and_key_permutation() {
    let rules = real_rules();
    assert_eq!(
        rules.keys().map(String::as_str).collect::<Vec<_>>(),
        REAL_RULE_IDS,
        "real rule inventory must stay at seven audited rules"
    );
    let mut per_rule = std::collections::BTreeMap::<String, usize>::new();
    for (case, rule_id, inputs) in real_cases() {
        // Read the fixture files again, rather than clone or re-evaluate the Rule.
        let reloaded = real_rules();
        assert_reproducible(
            rules[&rule_id].source_json(),
            reloaded[&rule_id].source_json(),
            &inputs,
            case["id"].as_str().unwrap(),
        );
        *per_rule.entry(rule_id).or_default() += 1;
    }
    assert_eq!(
        per_rule.keys().collect::<Vec<_>>(),
        rules.keys().collect::<Vec<_>>()
    );
    assert_eq!(
        per_rule.values().sum::<usize>(),
        105,
        "all real cases must execute"
    );
    println!("I18 reloaded/key-permuted cases by rule: {per_rule:?}; 4 independent order combinations per case");
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

/// Every real rule's `rule_content_hash` is pinned in `real.content_hashes.json`, so an edit to
/// a published-style rule cannot change what a result claims to have run without a visible diff.
#[test]
fn real_rule_content_hashes_are_pinned() {
    let pinned = load_json(&fixtures_dir().join("real.content_hashes.json"));
    let pinned = pinned["hashes"].as_object().expect("hashes object");
    let rules = real_rules();
    assert_eq!(
        rules.keys().map(String::as_str).collect::<Vec<_>>(),
        REAL_RULE_IDS,
        "real rule inventory must stay at seven audited rules"
    );
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
            "{id}: rule_content_hash changed; update real.content_hashes.json only if intended"
        );
    }
    // Check every result, including unknown/not-payable paths. Missing cases must
    // fail coverage rather than silently skip a rule through `if let Some`.
    let mut per_rule = std::collections::BTreeMap::<String, usize>::new();
    for (case, id, inputs) in real_cases() {
        let got = rules[&id].evaluate(&inputs).unwrap();
        assert_eq!(
            Some(got.rule_content_hash.as_str()),
            pinned[&id].as_str(),
            "{id}/{}: result hash",
            case["id"]
        );
        *per_rule.entry(id).or_default() += 1;
    }
    assert_eq!(
        per_rule.keys().collect::<Vec<_>>(),
        rules.keys().collect::<Vec<_>>()
    );
    assert_eq!(
        per_rule.values().sum::<usize>(),
        105,
        "all real cases must execute"
    );
    println!("Pinned content hashes checked on every result: {per_rule:?}");
}
