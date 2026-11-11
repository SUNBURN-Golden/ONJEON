//! fixture_only: migrated T-KN-02 r26, with the reference CLI for engine evaluation.
//! Keeping the engine behind its existing test CLI preserves the zone dependency rule.
#[path = "support/questions.rs"]
mod fixture_only;
use onjeon_knowledge::{KnowledgeError, KnowledgeRepository, ObservationAllowlist};
use onjeon_ontology::{
    check_constraints, membership, resolve_chain, view, Abox, Chain, CheckProfile,
};
use serde_json::{json, Value};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

#[test]
fn profile_historical_vs_service() {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../packages/fixtures/ontology");
    let abox = Abox::from_dir(&path).unwrap();
    let r26 = view(&abox, "rel:case-r26").unwrap();
    let historical = check_constraints(
        &r26,
        &CheckProfile::historical_fixture(Some(fixture_only::fixture_universe())),
    );
    assert!(historical.is_empty(), "{historical:?}");
    let questions = fixture_only::questions();
    assert_eq!(questions.len(), 11);
    let root = path.join("../../..").canonicalize().unwrap();
    let target = root.join("target/kn04_fixture_runner");
    let build = Command::new(env!("CARGO"))
        .args(["build", "--locked", "--manifest-path"])
        .arg(root.join("docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml"))
        .arg("--target-dir")
        .arg(&target)
        .output()
        .unwrap();
    assert!(
        build.status.success(),
        "{}",
        String::from_utf8_lossy(&build.stderr)
    );
    let mut jobs = Vec::new();
    for q in &questions {
        let chain = resolve_chain(&r26, &q.configs, q.contract_date, q.cov);
        let Chain::Linked(linked) = chain else {
            assert_eq!(q.expect, fixture_only::Outcome::Blocked, "{}", q.id);
            continue;
        };
        assert_ne!(q.expect, fixture_only::Outcome::Blocked, "{}", q.id);
        let m = q.dx_code.map(|code| {
            membership(
                &r26,
                linked.category.as_deref().unwrap(),
                code,
                Some(q.diagnosis_date),
            )
            .unwrap()
        });
        let dx = match m.map(|m| m.value.as_str()) {
            Some("true") => json!(true),
            Some("false") => json!(false),
            _ => Value::Null,
        };
        let rule: Value = serde_json::from_slice(&r26.rule_files[&linked.rule_path]).unwrap();
        let mut given = q.assume.as_object().cloned().unwrap();
        given.insert("contract_date".into(), json!(q.contract_date));
        given.insert("diagnosis_date".into(), json!(q.diagnosis_date));
        given.insert("dx_in_category".into(), dx);
        let inputs: serde_json::Map<String, Value> = rule["inputs"]
            .as_object()
            .unwrap()
            .keys()
            .map(|key| (key.clone(), given.get(key).cloned().unwrap_or(Value::Null)))
            .collect();
        jobs.push(json!({"case_id":q.id,"rule_path":path.join(linked.rule_path),"inputs":inputs}));
    }
    assert_eq!(jobs.len(), 9); // Q9/Q10 block before any engine call.
    let mut child = Command::new(target.join("debug/ontology-case-runner"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all(&serde_json::to_vec(&jobs).unwrap())
        .unwrap();
    let output = child.wait_with_output().unwrap();
    assert!(output.status.success());
    let answers: Vec<Value> = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(answers.len(), 9);
    for q in questions
        .iter()
        .filter(|q| q.expect != fixture_only::Outcome::Blocked)
    {
        let p = &answers.iter().find(|r| r["case_id"] == q.id).unwrap()["payout"];
        let amount = p
            .pointer("/amount/krw")
            .or_else(|| p.pointer("/conditional_amount/krw"))
            .and_then(Value::as_i64);
        let outcome = match p["kind"].as_str().unwrap() {
            "payable" => fixture_only::Outcome::Payable(amount.unwrap()),
            "not_payable" => fixture_only::Outcome::NotPayable,
            "undetermined" => fixture_only::Outcome::Undetermined(amount),
            _ => panic!("unexpected payout kind"),
        };
        assert_eq!(outcome, q.expect, "{}", q.id);
    }
    let service = check_constraints(
        &r26,
        &CheckProfile::service_conformance(Some(fixture_only::fixture_universe())),
    );
    assert!(!service.is_empty());
    let mut repo = KnowledgeRepository::new();
    for assertion in abox
        .section("assertions")
        .iter()
        .filter(|a| a["review_status"] == "accepted")
    {
        assert_eq!(
            repo.ingest_assertion(
                &path.join("abox_cases.json"),
                assertion.clone(),
                &ObservationAllowlist::default()
            ),
            Err(KnowledgeError::FixturePath)
        );
        assert_eq!(
            repo.ingest_assertion(
                Path::new("incoming/copy.json"),
                assertion.clone(),
                &ObservationAllowlist::default()
            ),
            Err(KnowledgeError::FixtureAccepted)
        );
        let mut copy = assertion.clone();
        copy["origin"] = "pipeline".into();
        assert_eq!(
            repo.ingest_assertion(
                Path::new("incoming/relabeled.json"),
                copy,
                &ObservationAllowlist::default()
            ),
            Err(KnowledgeError::AcceptedWithoutDecision)
        );
    }
    println!("r26: historical violations=0, questions=11/11, service and B1/B2/B3 rejected");
}
