//! Shared helpers of the twin-runtime tests: the case A-box (`packages/ontology/tests/golden`,
//! the discussion material's case A-box — everything here reads it as `origin=fixture`
//! test data), the 11 questions of the reference, and the mutation builders the
//! link-check tests use.
#![allow(dead_code)]

use onjeon_twin_runtime::*;
use serde_json::{json, Map, Value};
use std::path::PathBuf;

pub const CURRENT: &str = "rel:case-r26";
pub const HANA_ED: &str = "ted:hana_r2_1@2607";
pub const HANA_NEW: &str = "sc:hana_2601_3d_v20260701";
pub const HANA_OLD: &str = "sc:hana_2601_3d_v20260101";

pub fn golden_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../ontology/tests/golden")
}

pub fn abox() -> onjeon_ontology::Abox {
    onjeon_ontology::Abox::from_dir(&golden_dir()).expect("golden A-box")
}

/// The frozen release `rel:case-r26` as a snapshot.
pub fn release_snapshot() -> Snapshot {
    Snapshot::release(&abox(), CURRENT).expect("release snapshot")
}

/// The unfrozen candidate view of `a` as a snapshot (mutations under test).
pub fn candidate_snapshot(a: &onjeon_ontology::Abox) -> Snapshot {
    Snapshot::candidate(a).expect("candidate snapshot")
}

/// The ontology-judged declaration the golden rules rely on: `dx_in_category` is the
/// membership of `dx_code` in the coverage's category as of `diagnosis_date`.
pub fn dx_outside() -> Vec<OutsideInput> {
    vec![OutsideInput {
        name: "dx_in_category".to_string(),
        judged_by: JudgedBy::Ontology,
        code_fact: Some("dx_code".to_string()),
        as_of_fact: Some("diagnosis_date".to_string()),
        category: None,
        anchor_fact: None,
        duration: None,
        anchor_day_counted: None,
        dates_facts: Vec::new(),
    }]
}

// ---------- questions (packages/ontology/tests/golden + reference_results.txt) ----------
pub struct Question {
    pub id: &'static str,
    pub configs: Vec<&'static str>,
    pub cov: &'static str,
    pub contract_date: &'static str,
    pub diagnosis_date: &'static str,
    pub dx_code: Option<&'static str>,
    pub assume: Value,
    pub expect: Outcome,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Outcome {
    Blocked,
    Payable(i64),
    NotPayable,
    Undetermined(Option<i64>),
}

fn hana_assume() -> Value {
    json!({"policy_end_date": "2046-08-20", "already_paid": false, "is_initial_contract": true, "renewal_date": null, "insured_amount_krw": 10000000})
}

fn hi_assume() -> Value {
    json!({"policy_end_date": "2126-08-20", "already_paid": false, "insured_amount_krw": 10000000})
}

pub fn questions() -> Vec<Question> {
    let q = |id, configs: Vec<&'static str>, cov, cd, dd, code, assume, expect| Question {
        id,
        configs,
        cov,
        contract_date: cd,
        diagnosis_date: dd,
        dx_code: code,
        assume,
        expect,
    };
    let h = "cov:hana_2_1";
    let hi = "cov:hi_2_5";
    vec![
        q(
            "Q1",
            vec![HANA_NEW, HANA_OLD],
            h,
            "2026-08-20",
            "2027-04-20",
            Some("C16"),
            hana_assume(),
            Outcome::Payable(5_000_000),
        ),
        q(
            "Q2",
            vec![HANA_NEW],
            h,
            "2026-08-20",
            "2028-08-20",
            Some("C16"),
            hana_assume(),
            Outcome::Payable(10_000_000),
        ),
        q(
            "Q3",
            vec![HANA_NEW],
            h,
            "2026-08-20",
            "2026-11-17",
            Some("C16"),
            hana_assume(),
            Outcome::NotPayable,
        ),
        q(
            "Q3b",
            vec![HANA_NEW],
            h,
            "2026-08-20",
            "2026-11-18",
            Some("C16"),
            hana_assume(),
            Outcome::Payable(5_000_000),
        ),
        q(
            "Q4",
            vec![HANA_NEW],
            h,
            "2026-08-20",
            "2027-04-20",
            Some("C50"),
            hana_assume(),
            Outcome::NotPayable,
        ),
        q(
            "Q5",
            vec![HANA_NEW],
            h,
            "2026-08-20",
            "2027-04-20",
            None,
            hana_assume(),
            Outcome::Undetermined(Some(5_000_000)),
        ),
        q(
            "Q6",
            vec!["sc:hi2607_general"],
            hi,
            "2026-08-20",
            "2027-04-20",
            Some("C16"),
            hi_assume(),
            Outcome::Payable(10_000_000),
        ),
        q(
            "Q7",
            vec!["sc:hi2607_general"],
            hi,
            "2026-08-20",
            "2027-04-20",
            Some("D00.2"),
            hi_assume(),
            Outcome::NotPayable,
        ),
        q(
            "Q8",
            vec!["sc:hi2607_general"],
            hi,
            "2026-08-20",
            "2027-04-20",
            Some("C50"),
            hi_assume(),
            Outcome::Payable(10_000_000),
        ),
        q(
            "Q9",
            vec!["sc:lotte_2604_type1"],
            "cov:lotte_general_dx",
            "2026-08-20",
            "2027-04-20",
            Some("C16"),
            json!({}),
            Outcome::Blocked,
        ),
        q(
            "Q10",
            vec![HANA_NEW, HANA_OLD],
            h,
            "2026-03-15",
            "2027-01-10",
            Some("C16"),
            json!({}),
            Outcome::Blocked,
        ),
    ]
}

pub fn question(id: &str) -> Question {
    questions().into_iter().find(|q| q.id == id).unwrap()
}

/// The flat facts of a question: assumptions ∪ dates ∪ code ∪ contract_date.
pub fn facts_of(q: &Question) -> Map<String, Value> {
    let mut m = q.assume.as_object().cloned().unwrap_or_default();
    m.insert("contract_date".into(), json!(q.contract_date));
    m.insert("diagnosis_date".into(), json!(q.diagnosis_date));
    m.insert(
        "dx_code".into(),
        q.dx_code.map_or(Value::Null, |c| json!(c)),
    );
    m
}

/// Runs one question against the snapshot end to end.
pub fn run(snap: &Snapshot, q: &Question) -> RequestOutcome {
    evaluate_request(
        snap,
        &Request {
            candidates: &q.configs,
            contract_date: q.contract_date,
            coverage: q.cov,
            outside: &dx_outside(),
            facts: &facts_of(q),
        },
    )
}

/// The engine outcome a `RequestOutcome` reports.
pub fn outcome(out: &RequestOutcome) -> Outcome {
    let Some(Ok(r)) = &out.eval else {
        return Outcome::Blocked;
    };
    let payout = serde_json::to_value(&r.payout).unwrap();
    let krw = |p: &Value| {
        p.pointer("/amount/krw")
            .or_else(|| p.pointer("/conditional_amount/krw"))
            .and_then(Value::as_i64)
    };
    match payout["kind"].as_str().unwrap() {
        "payable" => Outcome::Payable(krw(&payout).unwrap()),
        "undetermined" => Outcome::Undetermined(krw(&payout)),
        "not_payable" => Outcome::NotPayable,
        other => panic!("payout kind {other}"),
    }
}

/// The blocked part of the outcome; asserts the engine ran zero times.
pub fn blocked(out: &RequestOutcome) -> Blocked {
    assert_eq!(out.engine_calls, 0);
    assert!(out.eval.is_none(), "eval ran on a blocked chain");
    out.chain
        .blocked()
        .unwrap_or_else(|| panic!("expected blocked, got {:?}", out.chain))
        .clone()
}

// ---------- A-box mutation helpers ----------
pub fn set(a: &mut onjeon_ontology::Abox, section: &str, id: &str, key: &str, val: Value) {
    a.find_mut(section, id)
        .unwrap_or_else(|| panic!("{id}"))
        .as_object_mut()
        .unwrap()
        .insert(key.to_string(), val);
}

pub fn get(a: &onjeon_ontology::Abox, section: &str, id: &str) -> Value {
    a.find(section, id)
        .unwrap_or_else(|| panic!("{id}"))
        .clone()
}

/// `base` with the listed keys replaced.
pub fn with(base: &Value, kv: &[(&str, Value)]) -> Value {
    let mut v = base.clone();
    for (k, x) in kv {
        v.as_object_mut()
            .unwrap()
            .insert((*k).to_string(), x.clone());
    }
    v
}

pub fn push(a: &mut onjeon_ontology::Abox, section: &str, v: Value) {
    a.section_mut(section).push(v);
}

/// `application_scope_complete` on a sales configuration, with a review status.
pub fn scope_complete(sc: &str, status: &str) -> Value {
    json!({"id": "a:synthetic_scope_complete", "subject": sc, "predicate": "application_scope_complete", "value": true,
        "criticality": "C0", "evidence": [{"ref": "hana_listing#2601_3d_v20260701", "role": "observation"}],
        "value_state": "observed", "review_status": status, "origin": "fixture"})
}
