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

fn declared_abox_rel() -> String {
    "packages/twin-runtime/tests/fixtures/declared_abox".to_string()
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
    assert_eq!(q1["release_id"], common::DECLARED_REL);
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

/// The judged-input declaration is the rule artifact's, not the job's (C-08): a job
/// cannot add judged inputs (`outside` is not a job field) and cannot skip them by
/// smuggling the judged input in as a fact — `dx_in_category: false` in `facts` is
/// ignored and the membership judgement decides.
#[test]
fn a_job_cannot_declare_or_bypass_judged_inputs() {
    let dir = declared_abox_rel();
    let rel = common::DECLARED_REL;
    let jobs = serde_json::json!([
        {"case_id": "declare", "abox": dir, "release": rel,
         "configs": ["sc:hana_2601_3d_v20260701"], "cov": "cov:hana_2_1",
         "contract_date": "2026-08-20", "facts": {"diagnosis_date": "2027-04-20", "dx_code": "C16"},
         "outside": [{"name": "dx_in_category", "judged_by": "ontology", "code_fact": "dx_code"}]},
        {"case_id": "smuggle", "abox": dir, "release": rel,
         "configs": ["sc:hana_2601_3d_v20260701"], "cov": "cov:hana_2_1",
         "contract_date": "2026-08-20",
         "facts": {"diagnosis_date": "2027-04-20", "dx_code": "C16", "dx_in_category": false},
         "assume": {"policy_end_date": "2046-08-20", "already_paid": false,
                    "is_initial_contract": true, "renewal_date": null, "insured_amount_krw": 10000000}},
        {"case_id": "bad-date", "abox": dir, "release": rel,
         "configs": ["sc:hana_2601_3d_v20260701"], "cov": "cov:hana_2_1",
         "contract_date": "not-a-date",
         "facts": {"diagnosis_date": "2027-04-20", "dx_code": "C16"}},
    ]);
    let (out, _) = run_cli(&jobs.to_string());
    // outside is rejected outright — the declaration never crosses the wire
    assert_eq!(by_id(&out, "declare")["outcome"], "job_error");
    // the fact saying false is overridden by the artefact's ontology judgement (C16 ∈ category)
    let smuggle = by_id(&out, "smuggle");
    assert_eq!(smuggle["outcome"], "evaluated");
    assert_eq!(smuggle["engine"]["payout"]["amount"]["krw"], 5_000_000);
    assert_eq!(smuggle["inputs"]["dx_in_category"], true);
    assert_eq!(smuggle["judgements"][0]["value"], "true");
    // a malformed contract date is rejected before the chain, never compared as text
    let bad = by_id(&out, "bad-date");
    assert_eq!(bad["outcome"], "request_error");
    assert_eq!(bad["engine_calls"], 0);
}

/// A `rule_path` that is present but not a string is still a legacy job — and it is a
/// `job_error`, not a panic: one bad job never stops the rest of the batch.
#[test]
fn a_malformed_rule_path_fails_without_affecting_others() {
    let (out, _) = run_cli(
        r#"[{"case_id":"null-path","rule_path":null},
           {"case_id":"num-path","rule_path":5},
           {"case_id":"obj-path","rule_path":{}},
           {"case_id":"legacy-hana","rule_path":"packages/ontology/tests/golden/규칙/hana-2601-3d-cancer-dx.json",
            "inputs":{"contract_date":"2026-08-20","is_initial_contract":true,"renewal_date":null,
                      "diagnosis_date":"2027-04-20","policy_end_date":"2046-08-20",
                      "dx_in_category":true,"already_paid":false,"insured_amount_krw":10000000}}]"#,
    );
    for id in ["null-path", "num-path", "obj-path"] {
        let j = by_id(&out, id);
        assert_eq!(j["outcome"], "job_error", "{id}");
        assert_eq!(j["engine_calls"], 0, "{id}");
    }
    assert_eq!(by_id(&out, "legacy-hana")["outcome"], "evaluated");
}

/// K15: a member edited in place after the freeze is an integrity finding — the job is
/// blocked before the chain and the engine never sees the tampered bytes.
#[test]
fn integrity_findings_block_the_job_before_the_engine() {
    let mut a = common::declared_abox();
    common::set(
        &mut a,
        "assertions",
        "a:hana_doc_link",
        "value_state",
        serde_json::json!("tampered"),
    );
    let dir = std::env::var("CARGO_TARGET_TMPDIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| std::env::temp_dir())
        .join("tampered_abox");
    common::write_abox_dir(&a, &dir);
    let jobs = serde_json::json!([
        {"case_id": "tampered", "abox": dir, "release": common::DECLARED_REL,
         "configs": ["sc:hana_2601_3d_v20260701"], "cov": "cov:hana_2_1",
         "contract_date": "2026-08-20",
         "facts": {"diagnosis_date": "2027-04-20", "dx_code": "C16"}},
    ]);
    let (out, _) = run_cli(&jobs.to_string());
    let j = by_id(&out, "tampered");
    assert_eq!(j["outcome"], "integrity_blocked");
    assert_eq!(j["engine_calls"], 0);
    assert!(j["integrity_findings"].as_array().unwrap()[0]["code"] == "K15");
    assert!(j.get("chain").is_none());
    assert!(j.get("engine").is_none());
}
