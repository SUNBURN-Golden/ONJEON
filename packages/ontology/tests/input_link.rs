//! Input-stage link check (C-26, 02_구현계약 §1.7): golden E1~E4 and the S01, S01b, T01, U01 regressions.
//! A blocked chain means zero engine calls.

mod common;
use common::*;
use onjeon_ontology::*;
use serde_json::json;

fn q1() -> Question {
    question("Q1")
}

fn blocked(v: &View, q: &Question) -> Blocked {
    let ans = answer(v, q);
    assert_eq!(ans.engine_calls, 0);
    ans.chain
        .blocked()
        .unwrap_or_else(|| panic!("expected blocked, got {:?}", ans.chain))
        .clone()
}

fn base_q1() -> Outcome {
    answer(&release_view(&abox(), CURRENT), &q1()).outcome
}

#[test]
fn e1_other_company_coverage_on_a_hana_configuration() {
    let v = release_view(&abox(), CURRENT);
    let mut q = q1();
    q.cov = "cov:hi_2_5";
    let b = blocked(&v, &q);
    assert_eq!(b.reason, BlockReason::CovNotInEdition);
}

#[test]
fn e2_coverage_of_another_edition_on_the_same_configuration() {
    let mut a = abox();
    push(
        &mut a,
        "nodes",
        json!({"id": "cov:synthetic_other_edition", "class": "CoverageOccurrence", "label": "자체 시험용 다른 판 담보"}),
    );
    push(
        &mut a,
        "assertions",
        json!({"id": "a:synthetic_in_other", "subject": "cov:synthetic_other_edition", "predicate": "in_edition", "object": "ted:hi_r2_5@2608",
        "criticality": "C0", "evidence": [{"ref": "hi2607#c_2_5_art1", "role": "basis"}], "value_state": "observed", "review_status": "accepted"}),
    );
    let mut q = q1();
    q.cov = "cov:synthetic_other_edition";
    assert_eq!(
        blocked(&candidate_view(&a).unwrap(), &q).reason,
        BlockReason::CovNotInEdition
    );
}

#[test]
fn e3_several_configurations_apply_on_the_contract_date() {
    let mut a = abox();
    push(
        &mut a,
        "nodes",
        json!({"id": "sc:synthetic_overlap", "class": "SalesConfiguration", "label": "자체 시험용 겹치는 판매 구성"}),
    );
    let hl = get(&a, "assertions", "a:hana_doc_link");
    push(
        &mut a,
        "assertions",
        with(
            &hl,
            &[
                ("id", json!("a:synthetic_overlap_link")),
                ("subject", json!("sc:synthetic_overlap")),
            ],
        ),
    );
    let mut q = q1();
    q.configs.push("sc:synthetic_overlap");
    let b = blocked(&candidate_view(&a).unwrap(), &q);
    assert_eq!(b.reason, BlockReason::MultipleCandidates);
    assert!(b.held[0].contains("복수"));
}

#[test]
fn e4_candidate_order_does_not_matter() {
    let v = release_view(&abox(), CURRENT);
    for id in ["Q1", "Q10"] {
        let q = question(id);
        let mut rev = question(id);
        rev.configs.reverse();
        assert_eq!(answer(&v, &q), answer(&v, &rev), "{id}");
    }
    let mut rev = q1();
    rev.configs.reverse();
    assert_eq!(answer(&v, &rev).outcome, Outcome::Payable(5_000_000));
    // the old sales configuration's link names no edition, so it cannot be shown unrelated
    let b = blocked(&v, &question("Q10"));
    assert_eq!(b.reason, BlockReason::ScopeUnknown);
    assert_eq!(b.held, ["a:hana_old_doc_link:scope_unknown"]);
}

#[test]
fn s01_extra_evidence_and_a_second_unrelated_edition_do_not_block() {
    let mut a = abox();
    let hl = get(&a, "assertions", "a:hana_doc_link");
    push(
        &mut a,
        "assertions",
        with(&hl, &[("id", json!("a:hana_doc_link_more_evidence"))]),
    );
    let more = answer(&candidate_view(&a).unwrap(), &q1());
    assert_eq!(more.outcome, base_q1());
    assert_eq!(
        more.chain.linked().unwrap().link_assertions,
        ["a:hana_doc_link", "a:hana_doc_link_more_evidence"]
    );

    let mut a = abox();
    let ed = get(&a, "terms_editions", HANA_ED);
    for id in ["ted:synthetic_main@2607", "ted:synthetic_rider2@2607"] {
        push(
            &mut a,
            "terms_editions",
            with(
                &ed,
                &[
                    ("id", json!(id)),
                    ("label", json!("자체 시험용 판")),
                    ("parts", json!([])),
                ],
            ),
        );
    }
    push(
        &mut a,
        "assertions",
        with(
            &hl,
            &[
                ("id", json!("a:synthetic_main_link")),
                ("object", json!("ted:synthetic_main@2607")),
            ],
        ),
    );
    push(
        &mut a,
        "assertions",
        with(
            &hl,
            &[
                ("id", json!("a:synthetic_rider2_link")),
                ("object", json!("ted:synthetic_rider2@2607")),
                ("review_status", json!("hold")),
                ("hold_reason", json!("reference_unresolved")),
            ],
        ),
    );
    push(
        &mut a,
        "assertions",
        scope_complete("sc:hana_2601_3d_v20260701", "accepted"),
    );
    assert_eq!(
        answer(&candidate_view(&a).unwrap(), &q1()).outcome,
        base_q1()
    );
}

#[test]
fn s01b_unapproved_duplicate_link_of_the_requested_edition_blocks() {
    let mut a = abox();
    let hl = get(&a, "assertions", "a:hana_doc_link");
    push(
        &mut a,
        "assertions",
        with(
            &hl,
            &[
                ("id", json!("a:hana_doc_link_dup_hold")),
                ("review_status", json!("hold")),
                ("hold_reason", json!("reference_unresolved")),
            ],
        ),
    );
    let b = blocked(&candidate_view(&a).unwrap(), &q1());
    assert_eq!(b.reason, BlockReason::LinkUnapproved);
    assert_eq!(b.held, ["a:hana_doc_link_dup_hold:hold"]);
}

#[test]
fn t01_unknown_scope_blocks_unrelated_rider_passes_competing_edition_blocks_order_independent() {
    let hl = get(&abox(), "assertions", "a:hana_doc_link");
    // a link whose edition is unknown cannot be shown unrelated
    let mut a = abox();
    push(
        &mut a,
        "assertions",
        with(
            &hl,
            &[
                ("id", json!("a:unknown_scope_link")),
                ("object", json!(null)),
                ("review_status", json!("hold")),
                ("hold_reason", json!("reference_unresolved")),
            ],
        ),
    );
    let b = blocked(&candidate_view(&a).unwrap(), &q1());
    assert_eq!(b.reason, BlockReason::ScopeUnknown);
    assert!(b.held[0].contains("scope_unknown"));
    // an unrelated rider with a confirmed "all applications checked" claim passes
    let mut a = abox();
    let ed = get(&a, "terms_editions", HANA_ED);
    push(
        &mut a,
        "terms_editions",
        with(
            &ed,
            &[
                ("id", json!("ted:synthetic_rider3@2607")),
                ("label", json!("자체 시험용 다른 특약 판")),
                ("parts", json!([])),
            ],
        ),
    );
    push(
        &mut a,
        "assertions",
        with(
            &hl,
            &[
                ("id", json!("a:synthetic_rider3_link")),
                ("object", json!("ted:synthetic_rider3@2607")),
                ("review_status", json!("hold")),
                ("hold_reason", json!("reference_unresolved")),
            ],
        ),
    );
    push(
        &mut a,
        "assertions",
        scope_complete("sc:hana_2601_3d_v20260701", "accepted"),
    );
    assert_eq!(
        answer(&candidate_view(&a).unwrap(), &q1()).outcome,
        base_q1()
    );
    // the coverage defined in two editions the configuration uses
    let mut a = abox();
    push(
        &mut a,
        "terms_editions",
        with(
            &ed,
            &[
                ("id", json!("ted:synthetic_compete@2607")),
                ("label", json!("자체 시험용 경쟁 판")),
            ],
        ),
    );
    push(
        &mut a,
        "assertions",
        with(
            &hl,
            &[
                ("id", json!("a:synthetic_compete_link")),
                ("object", json!("ted:synthetic_compete@2607")),
            ],
        ),
    );
    let inc = get(&a, "assertions", "a:hana_cov_in_edition");
    push(
        &mut a,
        "assertions",
        with(
            &inc,
            &[
                ("id", json!("a:synthetic_cov_in_compete")),
                ("object", json!("ted:synthetic_compete@2607")),
            ],
        ),
    );
    let b = blocked(&candidate_view(&a).unwrap(), &q1());
    assert_eq!(b.reason, BlockReason::CompetingEditions);
    assert!(b.held[0].contains("판 후보 복수"));
    // stored order and candidate order do not change the result
    let mut a = abox();
    push(
        &mut a,
        "assertions",
        with(&hl, &[("id", json!("a:hana_doc_link_more"))]),
    );
    push(
        &mut a,
        "assertions",
        with(
            &hl,
            &[
                ("id", json!("a:aa_unknown_scope_first")),
                ("object", json!(null)),
                ("review_status", json!("hold")),
            ],
        ),
    );
    let fwd = blocked(&candidate_view(&a).unwrap(), &q1());
    let mut b = a.clone();
    b.section_mut("assertions").reverse();
    let mut rq = q1();
    rq.configs.reverse();
    assert_eq!(fwd, blocked(&candidate_view(&b).unwrap(), &rq));
}

fn with_other_main(applies: Option<&str>, complete: Option<&str>) -> View {
    let mut a = abox();
    let ed = get(&a, "terms_editions", HANA_ED);
    push(
        &mut a,
        "terms_editions",
        with(
            &ed,
            &[
                ("id", json!("ted:synthetic_main@2607")),
                ("label", json!("자체 시험용 보통약관 판")),
                ("parts", json!([])),
            ],
        ),
    );
    let hl = get(&a, "assertions", "a:hana_doc_link");
    push(
        &mut a,
        "assertions",
        with(
            &hl,
            &[
                ("id", json!("a:synthetic_main_link2")),
                ("object", json!("ted:synthetic_main@2607")),
            ],
        ),
    );
    if let Some(st) = applies {
        push(
            &mut a,
            "assertions",
            json!({"id": "a:synthetic_main_applies", "subject": "ted:synthetic_main@2607", "predicate": "applies_to", "object": "cov:hana_2_1",
            "criticality": "C0", "evidence": [{"ref": "hana_2601_3d#c_2_1_art1_1", "role": "basis"}], "value_state": "observed", "review_status": st, "origin": "fixture"}),
        );
    }
    if let Some(st) = complete {
        push(
            &mut a,
            "assertions",
            scope_complete("sc:hana_2601_3d_v20260701", st),
        );
    }
    candidate_view(&a).unwrap()
}

#[test]
fn u01_definition_site_and_application_relation_are_different() {
    assert_eq!(
        answer(&with_other_main(None, Some("accepted")), &q1()).outcome,
        base_q1()
    );
    // a different edition id alone proves nothing
    assert_eq!(
        blocked(&with_other_main(None, None), &q1()).reason,
        BlockReason::ApplicationScopeUnverified
    );
    assert_eq!(
        blocked(&with_other_main(None, Some("hold")), &q1()).reason,
        BlockReason::ApplicationScopeUnverified
    );
    // another edition adds a condition the rule does not cover
    let b = blocked(&with_other_main(Some("accepted"), Some("accepted")), &q1());
    assert_eq!(b.reason, BlockReason::AppliesFromOtherEditionUnmodeled);
    assert_eq!(
        b.held,
        ["ted:synthetic_main@2607:applies_from_other_edition_unmodeled"]
    );
    let b = blocked(&with_other_main(Some("hold"), Some("accepted")), &q1());
    assert_eq!(b.held, ["a:synthetic_main_applies:applies_unconfirmed"]);
}

#[test]
fn q9_and_q10_are_blocked_with_a_reason() {
    let v = release_view(&abox(), CURRENT);
    let b = blocked(&v, &question("Q9"));
    assert_eq!(b.reason, BlockReason::ScopeUnknown);
    assert_eq!(b.held, ["a:lotte_doc_link:scope_unknown"]);
    // the old sales configuration's link names no edition, so it cannot be shown unrelated
    let b = blocked(&v, &question("Q10"));
    assert_eq!(b.reason, BlockReason::ScopeUnknown);
    assert_eq!(b.held, ["a:hana_old_doc_link:scope_unknown"]);
}

#[test]
fn simulate_is_blocked_by_open_conflict_and_missing_rule() {
    let mut a = abox();
    push(
        &mut a,
        "conflicts",
        json!({"id": "conf:t", "assertions": ["a:hana_cov_in_edition"], "state": "open"}),
    );
    let v = candidate_view(&a).unwrap();
    let (ok, why) = simulate_allowed(&v, "cov:hana_2_1");
    assert!(!ok);
    assert_eq!(why, ["미해소 충돌"]);
    assert_eq!(blocked(&v, &q1()).reason, BlockReason::SimulateBlocked);
    // a resolved conflict does not block
    set(&mut a, "conflicts", "conf:t", "state", json!("resolved"));
    assert!(simulate_allowed(&candidate_view(&a).unwrap(), "cov:hana_2_1").0);
    // no accepted implemented_by
    let mut a = abox();
    set(
        &mut a,
        "assertions",
        "a:hana_rule",
        "review_status",
        json!("hold"),
    );
    let b = blocked(&candidate_view(&a).unwrap(), &q1());
    assert!(b.held.iter().any(|h| h == "implemented_by 없음"));
}
