//! The 11 golden questions of `packages/ontology/tests/golden` through the twin-runtime
//! pipeline on `rel:case-r26`: same input-stage judgements, same engine outcomes, and
//! zero engine calls on the blocked questions (Q9, Q10).

mod common;
use common::*;
use onjeon_twin_runtime::*;
use serde_json::json;

#[test]
fn the_eleven_questions_match_the_reference() {
    let snap = release_snapshot();
    let qs = questions();
    assert_eq!(qs.len(), 11);
    for q in &qs {
        let out = run(&snap, q);
        assert_eq!(outcome(&out), q.expect, "{}", q.id);
        assert_eq!(
            out.engine_calls,
            usize::from(q.expect != Outcome::Blocked),
            "{}",
            q.id
        );
    }
}

#[test]
fn q9_and_q10_never_reach_the_engine() {
    let snap = release_snapshot();
    for id in ["Q9", "Q10"] {
        let out = run(&snap, &question(id));
        assert_eq!(out.engine_calls, 0, "{id}");
        assert!(out.eval.is_none(), "{id}");
        assert_eq!(blocked(&out).reason, BlockReason::ScopeUnknown, "{id}");
    }
}

#[test]
fn an_unconfirmed_edition_holds_before_the_engine() {
    // swapping one realizes fingerprint for a value no review covered leaves the edition
    // identity unconfirmed: the input stage does not compute on it.
    let mut a = abox();
    let seg = get(&a, "segments", "seg:hana_annex1");
    let mut seg = seg;
    seg["fingerprint"] = json!({"rule": "fp-0.1", "sha256": "f".repeat(64)});
    set(
        &mut a,
        "segments",
        "seg:hana_annex1",
        "fingerprint",
        seg["fingerprint"].clone(),
    );
    let out = run(&candidate_snapshot(&a), &q1());
    let b = blocked(&out);
    assert_eq!(b.reason, BlockReason::EditionIdentityUnconfirmed);
    assert_eq!(out.engine_calls, 0);
    assert!(out.judgements.is_empty());
}

fn q1() -> Question {
    question("Q1")
}

#[test]
fn the_membership_judgement_carries_its_evidence() {
    let snap = release_snapshot();
    let out = run(&snap, &q1());
    assert_eq!(out.judgements.len(), 1);
    let j = &out.judgements[0];
    assert_eq!(j.input_name, "dx_in_category");
    assert_eq!(j.value, onjeon_contracts::Tri::True);
    assert_eq!(j.judged_by, JudgedBy::Ontology);
    assert_eq!(j.judged_as_of.as_deref(), Some("2027-04-20"));
    assert!(j
        .evidence_assertion_ids
        .contains(&"a:hana_cat_inc".to_string()));
    assert!(j.code_system_refs.contains(&"codes:c44".to_string()));
}
