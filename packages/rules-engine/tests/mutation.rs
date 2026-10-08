//! Mutation tests: deliberately break the rule and prove the golden table notices.
//! A mutant that survives means the golden table cannot detect that kind of error.
mod common;
use common::*;
use onjeon_rules_engine::Rule;
use serde_json::{json, Value as J};

type Mutation = Box<dyn Fn(&mut J)>;

fn mutants() -> Vec<(&'static str, Mutation)> {
    vec![
        (
            "threshold 180 -> 179",
            Box::new(|r| r["amount"]["if"]["lt"][1] = json!(179)),
        ),
        (
            "threshold 180 -> 181",
            Box::new(|r| r["amount"]["if"]["lt"][1] = json!(181)),
        ),
        (
            "lt -> lte at boundary",
            Box::new(|r| {
                let v = r["amount"]["if"]["lt"].take();
                r["amount"]["if"] = json!({ "lte": v });
            }),
        ),
        (
            "gte 0 -> gt 0",
            Box::new(|r| {
                let v = r["eligibility"]["all"][0]["gte"].take();
                r["eligibility"]["all"][0] = json!({ "gt": v });
            }),
        ),
        (
            "drop exclusion condition",
            Box::new(|r| {
                r["eligibility"]["all"].as_array_mut().unwrap().remove(2);
            }),
        ),
        (
            "drop already-paid condition",
            Box::new(|r| {
                r["eligibility"]["all"].as_array_mut().unwrap().remove(3);
            }),
        ),
        (
            "invert exclusion (negation removed)",
            Box::new(|r| r["eligibility"]["all"][2]["eq"][1] = json!(true)),
        ),
        (
            "reduction rate 0.5 -> 0.6",
            Box::new(|r| r["amount"]["then"]["multiply_rate"][1] = json!("0.6")),
        ),
        (
            "swap then/else",
            Box::new(|r| {
                let t = r["amount"]["then"].take();
                let e = r["amount"]["else"].take();
                r["amount"]["then"] = e;
                r["amount"]["else"] = t;
            }),
        ),
        (
            "all -> any",
            Box::new(|r| {
                let v = r["eligibility"]["all"].take();
                r["eligibility"] = json!({ "any": v });
            }),
        ),
        (
            "unit change 1 -> 1000",
            Box::new(|r| r["amount"]["then"]["multiply_rate"][2]["unit"] = json!(1000)),
        ),
    ]
}

#[test]
fn every_mutant_is_killed_by_the_golden_table() {
    let cases = cases();
    let mut survivors = Vec::new();
    let all = mutants();
    let total = all.len();
    let mut loaded = 0;
    for (name, mutate) in all {
        let mut j = rule_json();
        mutate(&mut j);
        let rule = match Rule::from_json(&j) {
            Ok(r) => r,
            Err(_) => continue, // rejected at load time also counts as caught
        };
        loaded += 1;
        let killed = cases.iter().any(|c| match rule.evaluate(&c["inputs"]) {
            Ok(_) => !case_passes(&rule, c),
            Err(_) => true,
        });
        if !killed {
            survivors.push(name);
        }
    }
    assert_eq!(
        loaded, total,
        "every mutant should be a loadable rule so the golden table is what catches it"
    );
    assert!(
        survivors.is_empty(),
        "surviving mutants (golden table too weak): {survivors:?}"
    );
}
