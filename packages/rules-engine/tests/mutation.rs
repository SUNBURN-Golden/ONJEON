//! Mutation tests: deliberately break the rule and prove the golden table notices.
//! A mutant that survives means the golden table cannot detect that kind of error.
//!
//! Two layers: `mutants()` are hand-written breaks of the synthetic fixture; `generic` derives
//! mutants mechanically from the rule JSON, so every rule (synthetic and every real rule in
//! `fixtures/rules/real`) is covered without writing a mutant per rule.
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

/// Generic mutators over any rule: they walk the expression trees (`eligibility`, `amount`) and
/// produce one mutant per site and mutator, so a new rule is covered with no new test code.
mod generic {
    use super::*;
    use std::collections::BTreeSet;

    #[derive(Clone, Debug)]
    enum Seg {
        Key(String),
        Idx(usize),
    }

    pub struct Mutant {
        pub desc: String,
        pub rule: J,
    }

    fn at<'a>(j: &'a mut J, path: &[Seg]) -> &'a mut J {
        path.iter().fold(j, |n, s| match s {
            Seg::Key(k) => &mut n[k.as_str()],
            Seg::Idx(i) => &mut n[*i],
        })
    }

    fn show(path: &[Seg]) -> String {
        path.iter()
            .map(|s| match s {
                Seg::Key(k) => format!(".{k}"),
                Seg::Idx(i) => format!("[{i}]"),
            })
            .collect()
    }

    fn push(path: &[Seg], s: Seg) -> Vec<Seg> {
        let mut p = path.to_vec();
        p.push(s);
        p
    }

    /// Paths of every expression node below `path` (including itself). Parameter objects such
    /// as `{rounding, unit}` or `{value, unit}` are not expressions and are not entered.
    fn expr_nodes(j: &J, path: Vec<Seg>, out: &mut Vec<Vec<Seg>>) {
        out.push(path.clone());
        let Some(map) = j.as_object() else { return };
        if map.contains_key("if") {
            for k in ["if", "then", "else"] {
                expr_nodes(&map[k], push(&path, Seg::Key(k.into())), out);
            }
            return;
        }
        let Some((op, args)) = map.iter().next() else {
            return;
        };
        let op_path = push(&path, Seg::Key(op.clone()));
        match op.as_str() {
            "input" | "rate" | "krw" | "date" => {}
            "not" => expr_nodes(args, op_path, out),
            "multiply_rate" | "date_add" | "days_between" => {
                // Only the leading expression operands; the last argument is a parameter object.
                let n = if op == "date_add" { 1 } else { 2 };
                for i in 0..n {
                    expr_nodes(&args[i], push(&op_path, Seg::Idx(i)), out);
                }
            }
            _ => {
                for (i, a) in args.as_array().into_iter().flatten().enumerate() {
                    expr_nodes(a, push(&op_path, Seg::Idx(i)), out);
                }
            }
        }
    }

    /// `"0.5"` -> `"0.6"` / `"0.4"`: the last decimal digit moved by one unit.
    fn bump_rate(s: &str, delta: i64) -> Option<String> {
        let frac = s.split_once('.').map_or(0, |(_, f)| f.len());
        let scaled: i64 = s.replace('.', "").parse().ok()?;
        let n = scaled + delta;
        if n < 0 {
            return None;
        }
        let digits = format!("{:0>w$}", n, w = frac + 1);
        let (i, f) = digits.split_at(digits.len() - frac);
        Some(if frac == 0 {
            i.to_string()
        } else {
            format!("{i}.{f}")
        })
    }

    /// Every mutation of the single node `n` (children untouched).
    fn mutate_node(n: &J, inputs: &BTreeSet<String>) -> Vec<(String, J)> {
        let mut out: Vec<(String, J)> = Vec::new();
        match n {
            J::Bool(b) => out.push((format!("bool literal {b} -> {}", !b), J::Bool(!b))),
            J::Number(x) => {
                if let Some(i) = x.as_i64() {
                    out.push((format!("int literal {i} -> {}", i - 1), json!(i - 1)));
                    out.push((format!("int literal {i} -> {}", i + 1), json!(i + 1)));
                }
            }
            J::String(s) if !inputs.contains(s) => {
                for d in [-1, 1] {
                    if let Some(r) = bump_rate(s, d) {
                        out.push((format!("rate literal {s} -> {r}"), json!(r)));
                    }
                }
            }
            J::Object(map) if map.contains_key("if") => {
                let mut m = n.clone();
                m["then"] = n["else"].clone();
                m["else"] = n["then"].clone();
                out.push(("swap if branches".into(), m));
            }
            J::Object(map) if map.len() == 1 => {
                let (op, args) = map.iter().next().unwrap();
                let wrap = |op: &str, a: J| json!({ op: a });
                match op.as_str() {
                    "eq" | "ne" | "lt" | "lte" | "gt" | "gte" => {
                        // Ordering operators are rejected for bool/string operands at load time,
                        // so only the equality pair is flipped there; the loader check below
                        // reports any other mutant that does not load.
                        let to: &[&str] = match op.as_str() {
                            "eq" => &["ne"],
                            "ne" => &["eq"],
                            "lt" => &["lte", "gt"],
                            "lte" => &["lt", "gte"],
                            "gt" => &["gte", "lt"],
                            _ => &["gt", "lte"],
                        };
                        for t in to {
                            out.push((format!("comparator {op} -> {t}"), wrap(t, args.clone())));
                        }
                    }
                    "rate" => {
                        let s = args.as_str().unwrap();
                        for d in [-1, 1] {
                            if let Some(r) = bump_rate(s, d) {
                                out.push((
                                    format!("rate literal {s} -> {r}"),
                                    wrap("rate", json!(r)),
                                ));
                            }
                        }
                    }
                    "krw" => {
                        let k = args.as_i64().unwrap();
                        if k > 0 {
                            out.push((format!("krw {k} -> {}", k - 1), wrap("krw", json!(k - 1))));
                        }
                        out.push((format!("krw {k} -> {}", k + 1), wrap("krw", json!(k + 1))));
                    }
                    "date_add" => {
                        let v = args[1]["value"].as_i64().unwrap();
                        for d in [-1, 1] {
                            let mut m = n.clone();
                            m["date_add"][1]["value"] = json!(v + d);
                            out.push((format!("date_add value {v} -> {}", v + d), m));
                        }
                    }
                    "multiply_rate" => {
                        let cur = args[2]["rounding"].as_str().unwrap();
                        for r in ["floor", "ceil", "half_up", "half_even", "unspecified"] {
                            if r != cur {
                                let mut m = n.clone();
                                m["multiply_rate"][2]["rounding"] = json!(r);
                                out.push((format!("rounding {cur} -> {r}"), m));
                            }
                        }
                    }
                    "all" | "any" => {
                        let other = if op == "all" { "any" } else { "all" };
                        out.push((format!("{op} -> {other}"), wrap(other, args.clone())));
                        let items = args.as_array().unwrap();
                        if items.len() >= 2 {
                            for i in 0..items.len() {
                                let mut rest = items.clone();
                                rest.remove(i);
                                out.push((
                                    format!("drop {op} child {i}"),
                                    wrap(op, J::Array(rest)),
                                ));
                            }
                        }
                    }
                    _ => {}
                }
            }
            _ => {}
        }
        out
    }

    /// All mutants of `rule`, each differing from it at exactly one site.
    pub fn mutants_of(rule: &J) -> Vec<Mutant> {
        let inputs: BTreeSet<String> = rule["inputs"]
            .as_object()
            .unwrap()
            .keys()
            .cloned()
            .collect();
        let mut out = Vec::new();
        for root in ["eligibility", "amount"] {
            let mut nodes = Vec::new();
            expr_nodes(&rule[root], vec![Seg::Key(root.into())], &mut nodes);
            for path in nodes {
                let mut probe = rule.clone();
                let node = at(&mut probe, &path).clone();
                for (what, new) in mutate_node(&node, &inputs) {
                    let mut r = rule.clone();
                    *at(&mut r, &path) = new;
                    out.push(Mutant {
                        desc: format!("{}: {what}", show(&path).trim_start_matches('.')),
                        rule: r,
                    });
                }
            }
        }
        out
    }

    /// Why the golden table notices `mutant`, or `None` if it survives.
    pub fn killed_by(mutant: &J, cases: &[(J, J)]) -> Option<String> {
        let rule = match Rule::from_json(mutant) {
            Ok(r) => r,
            Err(e) => return Some(format!("rejected at load: {e}")),
        };
        cases
            .iter()
            .find_map(|(case, inputs)| match rule.evaluate(inputs) {
                Err(e) => Some(format!("case {} errors: {e:?}", case["id"])),
                Ok(_) if observe(&rule, inputs) != case["expect"] => {
                    Some(format!("case {}", case["id"]))
                }
                Ok(_) => None,
            })
    }
}

/// `(rule JSON, [(case, full inputs)])` for the synthetic fixture and every real rule.
type RuleCases = (String, J, Vec<(J, J)>);

fn all_rules_with_cases() -> Vec<RuleCases> {
    let mut out = vec![(
        "fixture-rule-001".to_string(),
        rule_json(),
        cases()
            .into_iter()
            .map(|c| {
                let i = c["inputs"].clone();
                (c, i)
            })
            .collect(),
    )];
    let mut real: std::collections::BTreeMap<String, Vec<(J, J)>> = Default::default();
    for (case, rule_id, inputs) in real_cases() {
        real.entry(rule_id).or_default().push((case, inputs));
    }
    for (id, rule) in real_rules() {
        let cases = real.remove(&id).unwrap_or_default();
        out.push((id, rule.source_json().clone(), cases));
    }
    out
}

/// Mutants no golden case can tell apart from the original because they do not change
/// behaviour. Keyed by `(rule_id, description)`; each needs a reason. A stale entry (the mutant
/// no longer exists or is now killed) fails `allowlist_has_no_stale_entries`.
const EQUIVALENT: &[(&str, &str, &str)] = &[];

#[test]
fn generic_rate_literals_mutate_in_both_representations() {
    for (rate, bumped) in [
        ("0.5", vec!["0.4", "0.6"]),
        ("0.33", vec!["0.32", "0.34"]),
        ("1", vec!["0", "2"]),
        ("0", vec!["1"]),
    ] {
        for wrapped in [false, true] {
            let literal = |s: &str| {
                if wrapped {
                    json!({"rate": s})
                } else {
                    json!(s)
                }
            };
            let mut rule = rule_json();
            rule["eligibility"] = json!(true);
            rule["amount"] = json!({
                "multiply_rate": [{"krw": 100}, literal(rate), {"rounding": "floor", "unit": 1}]
            });
            if wrapped {
                // Explicit rate literals remain literals even when an input has the same name.
                rule["inputs"][rate] = json!("bool");
                rule["eligibility"] = json!(rate);
            }
            Rule::from_json(&rule).unwrap();
            let mutants: Vec<_> = generic::mutants_of(&rule)
                .into_iter()
                .filter(|m| m.desc.contains(": rate literal "))
                .collect();
            assert_eq!(mutants.len(), bumped.len(), "{rate}, wrapped={wrapped}");
            for (mutant, expected_rate) in mutants.iter().zip(bumped.iter()) {
                let mut expected = rule.clone();
                expected["amount"]["multiply_rate"][1] = literal(expected_rate);
                assert_eq!(
                    mutant.desc,
                    format!("amount.multiply_rate[1]: rate literal {rate} -> {expected_rate}")
                );
                assert_eq!(mutant.rule, expected, "only the rate literal should change");
                Rule::from_json(&mutant.rule).unwrap();
            }
        }
    }
}

#[test]
fn wrapped_real_rule_rates_preserve_mutation_coverage() {
    let (_, rule, cases) = all_rules_with_cases()
        .into_iter()
        .find(|(id, ..)| id == "kb-driver-lawyer-fee")
        .unwrap();
    let original_mutants = generic::mutants_of(&rule);
    let mut wrapped = rule.clone();
    for level in wrapped["amount"]["add"].as_array_mut().unwrap() {
        let rate = &mut level["then"]["min"][0]["multiply_rate"][1];
        *rate = json!({"rate": rate.take()});
    }
    let baseline = Rule::from_json(&wrapped).unwrap();
    for (case, inputs) in &cases {
        assert_eq!(observe(&baseline, inputs), case["expect"]);
    }
    let wrapped_mutants = generic::mutants_of(&wrapped);
    let rate_descriptions = |mutants: &[generic::Mutant]| -> Vec<String> {
        mutants
            .iter()
            .filter(|m| m.desc.contains(": rate literal "))
            .map(|m| m.desc.clone())
            .collect()
    };
    let original_rates = rate_descriptions(&original_mutants);
    assert_eq!(
        original_rates.len(),
        6,
        "three sites need two rate mutants each"
    );
    assert_eq!(rate_descriptions(&wrapped_mutants), original_rates);
    assert_eq!(wrapped_mutants.len(), original_mutants.len());
    for mutant in &wrapped_mutants {
        Rule::from_json(&mutant.rule).unwrap_or_else(|e| panic!("{}: {e}", mutant.desc));
        assert!(
            generic::killed_by(&mutant.rule, &cases).is_some(),
            "wrapped rule mutant survived: {}",
            mutant.desc
        );
    }
    eprintln!(
        "lawyer-fee rule: {} mutants in each representation, including 6 rate mutants; all killed",
        wrapped_mutants.len()
    );
}

#[test]
fn generic_mutants_are_killed_on_every_rule() {
    let mut survivors = Vec::new();
    let mut total = 0;
    let mut per_kind = std::collections::BTreeSet::new();
    for (id, rule, cases) in all_rules_with_cases() {
        let baseline = Rule::from_json(&rule).unwrap();
        for (case, inputs) in &cases {
            assert_eq!(
                observe(&baseline, inputs), case["expect"],
                "{id}: the unmutated rule must pass its own case {} or mutation results mean nothing",
                case["id"]
            );
        }
        assert!(
            !cases.is_empty(),
            "{id}: no golden cases, every mutant would survive"
        );
        for m in generic::mutants_of(&rule) {
            assert!(
                Rule::from_json(&m.rule).is_ok(),
                "{id}: mutant `{}` must load so the golden table, not the loader, is what catches it",
                m.desc
            );
            total += 1;
            per_kind.insert(
                m.desc
                    .split(": ")
                    .nth(1)
                    .unwrap()
                    .split(' ')
                    .next()
                    .unwrap()
                    .to_string(),
            );
            let allowed = EQUIVALENT.iter().any(|(r, d, _)| *r == id && *d == m.desc);
            if generic::killed_by(&m.rule, &cases).is_none() && !allowed {
                survivors.push(format!("{id} :: {}", m.desc));
            }
        }
    }
    assert!(
        survivors.is_empty(),
        "{} of {total} mutants survive (golden cases too weak):\n{}",
        survivors.len(),
        survivors.join("\n")
    );
    assert!(
        total >= 300,
        "expected hundreds of generated mutants over 8 rules, got {total}"
    );
    for kind in [
        "comparator",
        "int",
        "krw",
        "rate",
        "date_add",
        "rounding",
        "drop",
        "all",
        "any",
        "swap",
        "bool",
    ] {
        assert!(
            per_kind.contains(kind),
            "mutator `{kind}` generated nothing; got {per_kind:?}"
        );
    }
}

#[test]
fn harness_reports_a_surviving_mutant() {
    // Negative control: a no-op "mutant" and a mutant that changes only a non-behavioural
    // field must survive, or `killed_by` is too eager and the test above proves nothing.
    let rule = rule_json();
    let cases: Vec<(J, J)> = cases()
        .into_iter()
        .map(|c| {
            let i = c["inputs"].clone();
            (c, i)
        })
        .collect();
    assert_eq!(
        generic::killed_by(&rule, &cases),
        None,
        "identical rule must survive"
    );
    let mut harmless = rule.clone();
    harmless["evidence_refs"] = json!(["synthetic-clause-001", "synthetic-clause-002"]);
    assert_eq!(
        generic::killed_by(&harmless, &cases),
        None,
        "evidence-only change must survive"
    );
    let mut broken = rule;
    broken["amount"]["if"]["lt"][1] = json!(179);
    assert!(
        generic::killed_by(&broken, &cases).is_some(),
        "a real break must be killed"
    );
}

#[test]
fn allowlist_has_no_stale_entries() {
    let rules = all_rules_with_cases();
    for (id, desc, reason) in EQUIVALENT {
        assert!(
            !reason.trim().is_empty(),
            "{id} :: {desc}: an equivalent mutant needs a reason"
        );
        let (_, rule, cases) = rules
            .iter()
            .find(|(r, ..)| r == id)
            .unwrap_or_else(|| panic!("unknown rule {id}"));
        let m = generic::mutants_of(rule)
            .into_iter()
            .find(|m| &m.desc == desc)
            .unwrap_or_else(|| panic!("{id} :: {desc}: no such mutant any more"));
        assert!(
            generic::killed_by(&m.rule, cases).is_none(),
            "{id} :: {desc} is now killed; remove it from EQUIVALENT"
        );
    }
}
