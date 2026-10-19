//! `case-runner` end to end: stdin jobs → JSON results with the engine outcome and the
//! input-stage judgements; blocked jobs report `engine_calls: 0`. Legacy jobs (the
//! absorbed verifier runner) still evaluate straight through.

mod common;
use serde_json::Value;
use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Stdio};

fn workspace_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn run_cli(stdin: &str) -> (Value, String) {
    let mut child = Command::new(env!("CARGO_BIN_EXE_case-runner"))
        .current_dir(workspace_root())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("case-runner spawns");
    child
        .stdin
        .take()
        .unwrap()
        .write_all(stdin.as_bytes())
        .unwrap();
    let out = child.wait_with_output().unwrap();
    assert!(
        out.status.success(),
        "exit {:?}: {}",
        out.status,
        String::from_utf8_lossy(&out.stderr)
    );
    (
        serde_json::from_slice(&out.stdout).expect("stdout is json"),
        String::from_utf8_lossy(&out.stderr).to_string(),
    )
}

fn by_id<'a>(out: &'a Value, id: &str) -> &'a Value {
    out.as_array()
        .unwrap()
        .iter()
        .find(|j| j["case_id"] == id)
        .unwrap_or_else(|| panic!("{id}"))
}

#[test]
fn golden_jobs_through_the_cli() {
    let jobs = std::fs::read_to_string(
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/jobs.json"),
    )
    .unwrap();
    let (out, _) = run_cli(&jobs);
    // Q1: linked, one engine call, payable 5_000_000, one ontology judgement
    let q1 = by_id(&out, "Q1");
    assert_eq!(q1["outcome"], "evaluated");
    assert_eq!(q1["engine_calls"], 1);
    assert_eq!(q1["release_id"], common::CURRENT);
    assert_eq!(q1["chain"]["edition"], common::HANA_ED);
    assert_eq!(q1["engine"]["payout"]["amount"]["krw"], 5_000_000);
    assert_eq!(q1["judgements"].as_array().unwrap().len(), 1);
    assert!(q1["judgements"][0]["evidence_assertion_ids"]
        .as_array()
        .unwrap()
        .contains(&serde_json::json!("a:hana_cat_inc")));
    // Q2: payable 10_000_000; Q3: not_payable; Q5: undetermined 5_000_000
    assert_eq!(
        by_id(&out, "Q2")["engine"]["payout"]["amount"]["krw"],
        10_000_000
    );
    assert_eq!(by_id(&out, "Q3")["engine"]["payout"]["kind"], "not_payable");
    assert_eq!(
        by_id(&out, "Q5")["engine"]["payout"]["conditional_amount"]["krw"],
        5_000_000
    );
    // Q9/Q10: blocked before the engine
    for id in ["Q9", "Q10"] {
        let j = by_id(&out, id);
        assert_eq!(j["outcome"], "blocked", "{id}");
        assert_eq!(j["engine_calls"], 0, "{id}");
        assert_eq!(j["chain"]["reason"], "scope_unknown", "{id}");
        assert!(j.get("engine").is_none(), "{id}");
    }
    // the absorbed legacy job evaluates the rule file directly
    let legacy = by_id(&out, "legacy-hana");
    assert_eq!(legacy["outcome"], "evaluated");
    assert_eq!(legacy["engine"]["payout"]["amount"]["krw"], 5_000_000);
    assert_eq!(legacy["judgements"].as_array().unwrap().len(), 0);
}

#[test]
fn a_job_with_an_unknown_release_fails_without_affecting_others() {
    let (out, _) = run_cli(
        r#"[{"case_id":"bad","abox":"packages/ontology/tests/golden","release":"rel:nope",
            "configs":["sc:hi2607_general"],"cov":"cov:hi_2_5","contract_date":"2026-08-20"},
           {"case_id":"legacy-hana","rule_path":"packages/ontology/tests/golden/규칙/hana-2601-3d-cancer-dx.json",
            "inputs":{"contract_date":"2026-08-20","is_initial_contract":true,"renewal_date":null,
                      "diagnosis_date":"2027-04-20","policy_end_date":"2046-08-20",
                      "dx_in_category":true,"already_paid":false,"insured_amount_krw":10000000}}]"#,
    );
    assert_eq!(by_id(&out, "bad")["outcome"], "job_error");
    assert_eq!(by_id(&out, "legacy-hana")["outcome"], "evaluated");
}
