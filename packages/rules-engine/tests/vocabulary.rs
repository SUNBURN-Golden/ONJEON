//! The engine's serialized state names must exist in the canonical vocabulary
//! (packages/schemas/vocabulary.json). This stops code and documents drifting apart.
use onjeon_rules_engine::rule::PUBLICATION_STATES;
use onjeon_rules_engine::{AmountOut, Payout, Tri};
use serde_json::Value as J;
use std::collections::BTreeSet;

fn axis(id: &str) -> BTreeSet<String> {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../schemas/vocabulary.json");
    let v: J = serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
    let a = v["axes"]
        .as_array()
        .unwrap()
        .iter()
        .find(|a| a["id"] == id)
        .unwrap_or_else(|| panic!("axis {id} missing from vocabulary.json"));
    a["values"]
        .as_array()
        .unwrap()
        .iter()
        .map(|x| x["code"].as_str().unwrap().to_string())
        .collect()
}

fn kind(v: J) -> String {
    v.get("kind")
        .and_then(J::as_str)
        .map(str::to_string)
        .unwrap_or_else(|| v.as_str().unwrap().to_string())
}

#[test]
fn tri_names_are_canonical() {
    let want = axis("tri");
    for t in [Tri::True, Tri::False, Tri::Unknown] {
        assert!(want.contains(&kind(serde_json::to_value(t).unwrap())));
    }
    assert_eq!(want.len(), 3);
}

#[test]
fn payout_names_are_canonical() {
    let want = axis("payout");
    let got: BTreeSet<String> = [
        Payout::NotPayable,
        Payout::Payable {
            amount: AmountOut::Unknown,
        },
        Payout::Undetermined {
            conditional_amount: AmountOut::Unknown,
        },
    ]
    .into_iter()
    .map(|p| kind(serde_json::to_value(p).unwrap()))
    .collect();
    assert_eq!(
        got, want,
        "engine payout kinds and vocabulary payout axis must match exactly"
    );
}

#[test]
fn amount_kind_names_are_canonical() {
    let want = axis("amount_kind");
    let got: BTreeSet<String> = [
        AmountOut::Exact { krw: 1 },
        AmountOut::Range {
            min_krw: 1,
            max_krw: 2,
        },
        AmountOut::Unknown,
    ]
    .into_iter()
    .map(|a| kind(serde_json::to_value(a).unwrap()))
    .collect();
    assert_eq!(got, want);
}

#[test]
fn publication_states_are_canonical() {
    let want = axis("publication_state");
    let got: BTreeSet<String> = PUBLICATION_STATES.iter().map(|s| s.to_string()).collect();
    assert_eq!(got, want);
}
