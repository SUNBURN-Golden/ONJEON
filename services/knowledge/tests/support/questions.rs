//! fixture_only: the reference r26 questions and synthetic universe.
use onjeon_ontology::CodeUniverse;
use serde_json::{json, Value};
pub fn fixture_universe() -> CodeUniverse {
    let mut codes: Vec<String> = (0..98).map(|n| format!("C{n:02}")).collect();
    codes.extend((0..49).map(|n| format!("D{n:02}")));
    codes.extend((0..10).map(|k| format!("D47.{k}")));
    codes.extend(["C16.2".to_string(), "D00.2".to_string()]);
    CodeUniverse::new("KCD", "fixture-universe", codes).unwrap()
}

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
