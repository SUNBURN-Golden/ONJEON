//! Pre-chain gates and the contract's block-reason surface:
//!
//! - K15 release-integrity findings stop the run before the chain — a member edited in
//!   place or a swapped rule file is blocked immediately, never merely reported.
//! - A malformed `contract_date` is rejected, not lexicographically compared.
//! - The `Blocked` reason is always one of the contract's ten (§1.7): the ontology
//!   checker's internal `simulate_blocked` surfaces as `link_unapproved`.

mod common;
use common::*;
use onjeon_twin_runtime::*;
use serde_json::json;

fn q1() -> Question {
    question("Q1")
}

/// K15: editing a member of the frozen release in place produces an integrity finding;
/// `evaluate_request` stops before the chain with zero engine calls.
#[test]
fn integrity_findings_stop_the_run_before_the_chain() {
    let mut a = declared_abox();
    set(
        &mut a,
        "assertions",
        "a:hana_doc_link",
        "value_state",
        json!("tampered"),
    );
    let snap = Snapshot::release(&a, DECLARED_REL).expect("snapshot reads");
    assert!(!snap.integrity_findings().is_empty());
    let out = run(&snap, &q1());
    assert!(!out.integrity_findings.is_empty());
    assert!(out.chain.is_none());
    assert_eq!(out.engine_calls, 0);
    assert!(out.eval.is_none() && out.filled.is_none());
}

/// K15: a swapped rule file is the same class of finding — it can never reach the engine.
#[test]
fn a_swapped_rule_file_is_an_integrity_block_not_an_evaluation() {
    let mut a = declared_abox();
    let hi = a.rule_files["규칙/hi2607-2-5-cancer-dx.json"].clone();
    a.rule_files
        .insert("규칙/hana-2601-3d-cancer-dx.json".into(), hi);
    let snap = Snapshot::release(&a, DECLARED_REL).expect("snapshot reads");
    let out = run(&snap, &q1());
    assert!(!out.integrity_findings.is_empty());
    assert_eq!(out.engine_calls, 0);
    assert!(out.chain.is_none());
}

/// A contract date that is not a date is rejected before selection — never fed to the
/// lexicographic `valid_on` compare.
#[test]
fn a_malformed_contract_date_is_rejected() {
    let snap = declared_snapshot();
    for bad in ["not-a-date", "2026-13-40", "08/20/2026"] {
        let mut q = q1();
        q.contract_date = bad;
        let out = run(&snap, &q);
        assert_eq!(out.engine_calls, 0, "{bad}");
        assert!(out.chain.is_none(), "{bad}");
        assert!(out.request_error.is_some(), "{bad}");
        assert!(out.eval.is_none(), "{bad}");
    }
}

/// A coverage linked into the edition but with no `implemented_by` rule is `no_rule`
/// (one of the contract's ten reasons), with zero engine calls.
#[test]
fn a_coverage_without_a_rule_is_no_rule() {
    let mut a = declared_abox();
    push(
        &mut a,
        "nodes",
        json!({"id": "cov:synthetic_norule", "class": "CoverageOccurrence", "label": "자체 시험용 무룰 담보"}),
    );
    push(
        &mut a,
        "assertions",
        json!({"id": "a:synthetic_norule_in_ed", "subject": "cov:synthetic_norule", "predicate": "in_edition", "object": "ted:hana_r2_1@2607",
        "criticality": "C0", "evidence": [{"ref": "hana_2601_3d#c_2_1_art1_1", "role": "basis"}], "value_state": "observed", "review_status": "accepted"}),
    );
    let mut q = q1();
    q.cov = "cov:synthetic_norule";
    let out = run(&candidate_snapshot(&a), &q);
    let b = blocked(&out);
    assert_eq!(b.reason, BlockReason::NoRule);
}

/// The ontology checker's `simulate_blocked` (unaccepted C0 claims in the coverage's
/// scope) is not a contract reason — it surfaces as `link_unapproved`, the assertion
/// ids kept in `held`.
#[test]
fn unapproved_claims_in_scope_hold_as_link_unapproved() {
    let mut a = declared_abox();
    // an unaccepted C0 claim about the requested coverage itself
    push(
        &mut a,
        "assertions",
        json!({"id": "a:synthetic_cov_hold", "subject": "cov:hana_2_1", "predicate": "pays", "object": "money:1000000",
        "criticality": "C0", "evidence": [{"ref": "hana_2601_3d#c_2_1_art1_1", "role": "basis"}], "value_state": "observed", "review_status": "hold"}),
    );
    let out = run(&candidate_snapshot(&a), &q1());
    let b = blocked(&out);
    assert_eq!(b.reason, BlockReason::LinkUnapproved);
    assert!(b.held.iter().any(|h| h.contains("a:synthetic_cov_hold")));
}
