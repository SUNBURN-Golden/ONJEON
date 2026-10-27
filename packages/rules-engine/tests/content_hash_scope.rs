//! Audit 2: `rule_content_hash` sorts object keys and drops the top-level `release_id`,
//! nothing else. These tests pin both halves so the README cannot call it "normalized".
use onjeon_rules_engine::Rule;
use serde_json::{json, Value as J};

fn base(schema: &str) -> J {
    json!({
        "rule_id": "hash-scope", "rule_version": "1", "schema_version": schema,
        "inputs": {"amt": "money_krw", "ok": "bool"},
        "eligibility": {"eq": ["ok", true]},
        "amount": {"multiply_rate": ["amt", "0.5", {"rounding": "floor", "unit": 1}]},
        "unknown_policy": "use_three_valued_logic_never_default_to_zero",
        "evidence_refs": ["clause-1", "clause-2"], "publication_state": "fixture_only"
    })
}

fn hash(j: &J) -> String {
    Rule::from_json(j).unwrap().content_hash().to_string()
}

fn hash_text(text: &str) -> String {
    hash(&serde_json::from_str(text).unwrap())
}

const TEXT: &str = r#"{"rule_id":"hash-scope","rule_version":"1","schema_version":"rule-0.1","inputs":{"amt":"money_krw","ok":"bool"},"eligibility":{"eq":["ok",true]},"amount":{"multiply_rate":["amt","0.5",{"rounding":"floor","unit":1}]},"unknown_policy":"use_three_valued_logic_never_default_to_zero","evidence_refs":["clause-1","clause-2"],"publication_state":"fixture_only"}"#;

// ---- what the hash ignores: JSON text form, key order, top-level release_id ----

#[test]
fn whitespace_key_order_and_string_escapes_do_not_change_the_hash() {
    let reordered = r#"{
        "publication_state" : "fixture_only",
        "evidence_refs" : [ "clause-1", "clause-2" ],
        "unknown_policy" : "use_three_valued_logic_never_default_to_zero",
        "amount" : { "multiply_rate" : [ "amt", "0.5", { "unit" : 1, "rounding" : "floor" } ] },
        "eligibility" : { "eq" : [ "ok", true ] },
        "inputs" : { "ok" : "bool", "amt" : "money_krw" },
        "schema_version" : "rule-0.1", "rule_version" : "1", "rule_id" : "hash-scope"
    }"#;
    assert_eq!(hash_text(TEXT), hash(&base("rule-0.1")));
    assert_eq!(hash_text(reordered), hash_text(TEXT));
}

#[test]
fn top_level_release_id_is_excluded_but_a_nested_one_is_hashed() {
    let mut released = base("rule-0.1");
    released["publication_state"] = json!("released");
    let mut a = released.clone();
    a["release_id"] = json!("rel-a");
    let mut b = released.clone();
    b["release_id"] = json!("rel-b");
    assert_eq!(hash(&a), hash(&b));

    let mut nested = base("rule-0.1");
    nested["example_kind"] = json!({"release_id": "x"});
    let mut nested2 = base("rule-0.1");
    nested2["example_kind"] = json!({"release_id": "y"});
    assert_ne!(hash(&nested), hash(&nested2));
}

// ---- what the hash does NOT normalize: values are hashed exactly as loaded ----

#[test]
fn unicode_forms_are_not_normalized() {
    let mut nfc = base("rule-0.1");
    nfc["evidence_refs"] = json!(["약관 제3조 \u{00e9}"]);
    let mut nfd = base("rule-0.1");
    nfd["evidence_refs"] = json!(["약관 제3조 e\u{0301}"]);
    assert_ne!(hash(&nfc), hash(&nfd));

    let mut syllable = base("rule-0.1");
    syllable["rule_id"] = json!("\u{d55c}"); // 한 (precomposed)
    let mut jamo = base("rule-0.1");
    jamo["rule_id"] = json!("\u{1112}\u{1161}\u{11ab}"); // ᄒ ᅡ ᆫ
    assert_ne!(hash(&syllable), hash(&jamo));
}

#[test]
fn string_whitespace_and_array_order_are_not_normalized() {
    let mut padded = base("rule-0.1");
    padded["rule_id"] = json!("hash-scope ");
    assert_ne!(hash(&padded), hash(&base("rule-0.1")));

    let mut swapped = base("rule-0.1");
    swapped["evidence_refs"] = json!(["clause-2", "clause-1"]);
    assert_ne!(hash(&swapped), hash(&base("rule-0.1")));

    let mut all_swapped = base("rule-0.1");
    all_swapped["eligibility"] = json!({"all": [{"eq": ["ok", true]}, true]});
    let mut all_orig = base("rule-0.1");
    all_orig["eligibility"] = json!({"all": [true, {"eq": ["ok", true]}]});
    assert_ne!(hash(&all_swapped), hash(&all_orig));
}

#[test]
fn equivalent_spellings_of_the_same_logic_hash_differently() {
    // Both forms load and evaluate identically; the hash still differs.
    let plain = base("rule-0.1");
    let mut explicit = base("rule-0.1");
    explicit["amount"] =
        json!({"multiply_rate": ["amt", {"rate": "0.5"}, {"rounding": "floor", "unit": 1}]});
    let mut decimal = base("rule-0.1");
    decimal["amount"] = json!({"multiply_rate": ["amt", "0.50", {"rounding": "floor", "unit": 1}]});
    let inputs = json!({"amt": 1001, "ok": true});
    let out = |j: &J| {
        let r = Rule::from_json(j).unwrap().evaluate(&inputs).unwrap();
        serde_json::to_value(r.payout).unwrap()
    };
    assert_eq!(out(&plain), out(&explicit));
    assert_eq!(out(&plain), out(&decimal));
    assert_ne!(hash(&plain), hash(&explicit));
    assert_ne!(hash(&plain), hash(&decimal));
    assert_ne!(hash(&explicit), hash(&decimal));
}

#[test]
fn omitted_defaults_are_not_filled_in() {
    let absent = base("rule-0.1");
    let mut calendar = base("rule-0.1");
    calendar["calendar"] = json!("Asia/Seoul");
    assert_ne!(hash(&absent), hash(&calendar));

    let absent02 = base("rule-0.2");
    let mut none02 = base("rule-0.2");
    none02["contract_effect"] = json!("none");
    let a = Rule::from_json(&absent02).unwrap();
    let n = Rule::from_json(&none02).unwrap();
    assert_eq!(a.contract_effect(), n.contract_effect());
    assert_ne!(a.content_hash(), n.content_hash());
}

#[test]
fn metadata_that_does_not_affect_evaluation_is_still_hashed() {
    let mut tagged = base("rule-0.1");
    tagged["example_kind"] = json!("synthetic_not_a_real_product");
    assert_ne!(hash(&tagged), hash(&base("rule-0.1")));
}
