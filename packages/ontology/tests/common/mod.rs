//! Shared helpers of the golden tests: the case A-box, the 11 questions, the rules-engine glue and the
//! synthetic-record builders the reference self-tests use. Everything here is test-only data
//! (`tests/golden/` is the discussion material's case A-box, `origin=fixture`).
#![allow(dead_code)]

use onjeon_contracts::Tri;
use onjeon_ontology::*;
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::path::PathBuf;

pub const CURRENT: &str = "rel:case-r26";
pub const HANA_ED: &str = "ted:hana_r2_1@2607";

pub fn golden_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/golden")
}

pub fn abox() -> Abox {
    Abox::from_dir(&golden_dir()).expect("golden A-box")
}

/// Universe of the reference checker: C00~C97, D00~D48, D47.0~D47.9, C16.2, D00.2. Test-only: not an official KCD list.
pub fn fixture_universe() -> CodeUniverse {
    let mut codes: Vec<String> = (0..98).map(|n| format!("C{n:02}")).collect();
    codes.extend((0..49).map(|n| format!("D{n:02}")));
    codes.extend((0..10).map(|k| format!("D47.{k}")));
    codes.extend(["C16.2".to_string(), "D00.2".to_string()]);
    CodeUniverse::new("KCD", "fixture-universe", codes).unwrap()
}

pub fn historical() -> CheckProfile {
    CheckProfile::historical_fixture(Some(fixture_universe()))
}

pub fn codes(vs: &[Violation]) -> Vec<&str> {
    vs.iter().map(|v| v.code.as_str()).collect()
}

pub fn check(v: &View) -> Vec<Violation> {
    check_constraints(v, &historical())
}

pub fn check_candidate(a: &Abox) -> Vec<Violation> {
    check(&candidate_view(a).unwrap())
}

pub fn release_view(a: &Abox, rel: &str) -> View {
    view(a, rel).unwrap()
}

// ---------- JSON helpers ----------
pub fn set(a: &mut Abox, section: &str, id: &str, key: &str, val: Value) {
    a.find_mut(section, id)
        .unwrap_or_else(|| panic!("{id}"))
        .as_object_mut()
        .unwrap()
        .insert(key.to_string(), val);
}

pub fn unset(a: &mut Abox, section: &str, id: &str, key: &str) {
    a.find_mut(section, id)
        .unwrap()
        .as_object_mut()
        .unwrap()
        .remove(key);
}

pub fn get(a: &Abox, section: &str, id: &str) -> Value {
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

pub fn push(a: &mut Abox, section: &str, v: Value) {
    a.section_mut(section).push(v);
}

pub fn realizes(sid: &str, ed: &str, by: &str) -> Value {
    json!({"id": format!("a:realizes_{}", sid.split(':').nth(1).unwrap()), "subject": sid, "predicate": "realizes", "object": ed,
        "criticality": "C0", "evidence": [{"ref": sid, "role": "observation"}], "value_state": "observed",
        "review_status": "accepted", "origin": "fixture", "decision": {"by": by}})
}

pub fn scope_complete(sc: &str, status: &str) -> Value {
    json!({"id": "a:synthetic_scope_complete", "subject": sc, "predicate": "application_scope_complete", "value": true,
        "criticality": "C0", "evidence": [{"ref": "hana_listing#2601_3d_v20260701", "role": "observation"}],
        "value_state": "observed", "review_status": status, "origin": "fixture"})
}

pub fn raw_asset(id: &str, label: &str, sha: &str) -> Value {
    json!({"id": id, "class": "RawAsset", "observed_label": label, "org": "org:hana_nonlife", "sha256": sha, "source": "합성", "observed_at": null})
}

/// Adds a synthetic raw file holding all three parts of the Hana 2-1 edition (body, annex 1, annex 12),
/// each realizing the edition. `change` swaps one segment's fingerprint for a different `fp-0.1` value.
pub fn repack(a: &mut Abox, tag: &str, change: Option<&str>) {
    let sha = tag.chars().next().unwrap().to_string().repeat(64);
    push(
        a,
        "raw_assets",
        raw_asset(
            &format!("raw:synthetic_{tag}"),
            &format!("자체 시험용 합성 원본({tag})"),
            &sha,
        ),
    );
    for (k, sid) in ["seg:hana_r2_1", "seg:hana_annex1", "seg:hana_annex12"]
        .iter()
        .enumerate()
    {
        let nid = format!("seg:synthetic_{tag}_{k}");
        let mut seg = with(
            &get(a, "segments", sid),
            &[
                ("id", json!(nid)),
                ("raw_asset", json!(format!("raw:synthetic_{tag}"))),
                ("pages", json!([10 + k, 10 + k])),
            ],
        );
        if change == Some(*sid) {
            seg["fingerprint"] = json!({"rule": "fp-0.1", "sha256": "f".repeat(64)});
        }
        push(a, "segments", seg);
        push(
            a,
            "assertions",
            realizes(&nid, HANA_ED, "fixture_assumption"),
        );
    }
}

// ---------- questions ----------
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

const HANA_NEW: &str = "sc:hana_2601_3d_v20260701";
const HANA_OLD: &str = "sc:hana_2601_3d_v20260101";

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

/// One answered question: the link-check result, the judgement, the engine outcome (calls counted) and the
/// explanation lines (evidence chain down to page and file). Equal answers ⇒ equal results and explanations.
#[derive(Debug, Clone, PartialEq)]
pub struct Answer {
    pub chain: Chain,
    pub membership: Option<Judgement>,
    pub outcome: Outcome,
    pub engine_calls: usize,
    pub explanation: Vec<String>,
}

pub fn answer(v: &View, q: &Question) -> Answer {
    let chain = resolve_chain(v, &q.configs, q.contract_date, q.cov);
    let Chain::Linked(l) = &chain else {
        let explanation = explain_blocked(v, q, chain.blocked().unwrap());
        return Answer {
            chain,
            membership: None,
            outcome: Outcome::Blocked,
            engine_calls: 0,
            explanation,
        };
    };
    let cat = l.category.as_deref().expect("category");
    let m = q
        .dx_code
        .map(|c| membership(v, cat, c, Some(q.diagnosis_date)).unwrap());
    let dx_in = match m.as_ref().map(|j| j.value) {
        Some(Tri::True) => json!(true),
        Some(Tri::False) => json!(false),
        _ => Value::Null,
    };
    let rule_bytes = &v.rule_files[&l.rule_path];
    let rule_json: Value = serde_json::from_slice(rule_bytes).unwrap();
    let mut given = q.assume.as_object().cloned().unwrap_or_default();
    given.insert("contract_date".into(), json!(q.contract_date));
    given.insert("diagnosis_date".into(), json!(q.diagnosis_date));
    given.insert("dx_in_category".into(), dx_in);
    let inputs: serde_json::Map<String, Value> = rule_json["inputs"]
        .as_object()
        .unwrap()
        .keys()
        .map(|k| (k.clone(), given.get(k).cloned().unwrap_or(Value::Null)))
        .collect();
    let rule = onjeon_rules_engine::Rule::from_json_str(std::str::from_utf8(rule_bytes).unwrap())
        .expect("rule loads");
    let ev = rule
        .evaluate(&Value::Object(inputs))
        .expect("rule evaluates");
    let payout = serde_json::to_value(&ev.payout).unwrap();
    let krw = |p: &Value| {
        p.pointer("/amount/krw")
            .or_else(|| p.pointer("/conditional_amount/krw"))
            .and_then(Value::as_i64)
    };
    let outcome = match payout["kind"].as_str().unwrap() {
        "payable" => Outcome::Payable(krw(&payout).unwrap()),
        "undetermined" => Outcome::Undetermined(krw(&payout)),
        "not_payable" => Outcome::NotPayable,
        other => panic!("payout kind {other}"),
    };
    let mut lines = vec![format!(
        "rule {} {} hash {} inputs {}",
        ev.rule_id, ev.rule_version, ev.rule_content_hash, ev.input_snapshot_hash
    )];
    lines.extend(explain_linked(v, l, m.as_ref(), &ev.evidence_refs));
    Answer {
        chain,
        membership: m,
        outcome,
        engine_calls: 1,
        explanation: lines,
    }
}

pub fn answer_all(v: &View) -> BTreeMap<String, Answer> {
    questions()
        .iter()
        .map(|q| (q.id.to_string(), answer(v, q)))
        .collect()
}

fn where_clause(v: &View, clause: &str) -> String {
    let c = v.raw["clauses"]
        .iter()
        .find(|c| c["id"] == clause)
        .unwrap_or_else(|| panic!("{clause}"));
    let seg = v.segment(c["segment"].as_str().unwrap()).unwrap();
    let raw = v.raw["raw_assets"]
        .iter()
        .find(|r| Some(r["id"].as_str().unwrap()) == seg.raw_asset.as_deref())
        .unwrap();
    let ed = v
        .terms_clauses()
        .get(clause)
        .cloned()
        .unwrap_or_else(|| "본문 판 미연결".into());
    let fp = seg.fingerprint.as_ref().unwrap();
    format!(
        "{} · 판 {} · 구획 {}({}) 지문 {} · 원본 sha256 {} PDF {}쪽",
        c["path"].as_str().unwrap(),
        ed,
        seg.id,
        seg.doc_role,
        &fp.sha256[..12],
        &raw["sha256"].as_str().unwrap()[..12],
        c["pdf_page"]
    )
}

fn explain_linked(
    v: &View,
    l: &Linked,
    m: Option<&Judgement>,
    evidence_refs: &[String],
) -> Vec<String> {
    let mut out = vec![format!(
        "판매본 {} · 판 {} · 연결 {:?} · 규칙 주장 {}",
        l.sales_config, l.edition, l.link_assertions, l.rule_assertion
    )];
    if let Some(m) = m {
        for t in &m.trail {
            let a = v.assertion(&t.assertion_id).unwrap();
            for e in a.evidence.iter().filter(|e| e.role == "basis") {
                out.push(format!(
                    "{} ← 주장 {} → {}",
                    t.message,
                    a.id,
                    where_clause(v, &e.target)
                ));
            }
        }
    }
    for r in evidence_refs {
        let backing: Vec<&str> = v
            .current()
            .filter(|a| {
                a.evidence
                    .iter()
                    .any(|e| e.target == *r && e.role == "basis")
            })
            .map(|a| a.id.as_str())
            .collect();
        out.push(format!(
            "근거 {r} → 주장 {} → {}",
            backing.join(","),
            where_clause(v, r)
        ));
    }
    out
}

fn explain_blocked(v: &View, q: &Question, b: &Blocked) -> Vec<String> {
    let mut out = vec![format!("막은 것: {} {:?}", b.reason.as_str(), b.held)];
    let cur: Vec<&Assertion> = v.current().collect();
    let mut about: Vec<String> = vec![q.cov.to_string()];
    about.extend(b.sales_config.clone());
    about.extend(
        cur.iter()
            .filter(|a| a.subject == q.cov && a.predicate == "uses_definition")
            .filter_map(|a| a.object.clone()),
    );
    for g in v.raw["gaps"]
        .iter()
        .filter(|g| about.iter().any(|x| g["about"] == *x))
    {
        out.push(format!(
            "공백 {}: {} · {} · {}",
            g["id"], g["question"], g["knowledge_state"], g["needed_evidence"]
        ));
    }
    out
}

/// A copy of the golden A-box where the Hana rule file names an extra, unsupported evidence ref.
pub fn with_bad_rule(a: &mut Abox) {
    let mut rule: Value =
        serde_json::from_slice(&a.rule_files["규칙/hana-2601-3d-cancer-dx.json"]).unwrap();
    rule["evidence_refs"]
        .as_array_mut()
        .unwrap()
        .push(json!("hana_2601_3d#c_2_1_art5"));
    a.rule_files.insert(
        "규칙/_tmp_bad.json".into(),
        serde_json::to_vec(&rule).unwrap(),
    );
    set(
        a,
        "assertions",
        "a:hana_rule",
        "rule_path",
        json!("규칙/_tmp_bad.json"),
    );
}
