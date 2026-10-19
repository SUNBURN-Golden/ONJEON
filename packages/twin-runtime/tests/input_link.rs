//! Input-stage link check on the service side (C-26, 02_구현계약 §1.7): the golden
//! E1~E4 / S01 / S01b / T01 / U01 cases through `evaluate_request`. Every blocked chain
//! leaves the affected conclusion held and `engine_calls == 0`.

mod common;
use common::*;
use onjeon_twin_runtime::*;
use serde_json::json;

fn q1() -> Question {
    question("Q1")
}

fn base_q1() -> Outcome {
    outcome(&run(&release_snapshot(), &q1()))
}

/// input-link-other-company (golden E1, 재검토 R02 재현): a Hana sales configuration,
/// the Hyundai coverage. The requested `cov` is never trusted on its own: it is not in
/// the edition this configuration uses, so nothing links and the engine never runs.
#[test]
fn input_link_other_company() {
    let snap = release_snapshot();
    let mut q = q1();
    q.cov = "cov:hi_2_5";
    let out = run(&snap, &q);
    assert_eq!(outcome(&out), Outcome::Blocked);
    let b = blocked(&out);
    assert_eq!(b.reason, BlockReason::CovNotInEdition);
    // no rule is chosen for a blocked request
    assert!(out.rule.is_none() && out.filled.is_none());
}

/// input-link-other-edition (golden E2): a coverage that lives in another edition, on
/// the same sales configuration, is `cov_not_in_edition` with zero engine calls.
#[test]
fn input_link_other_edition() {
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
    let out = run(&candidate_snapshot(&a), &q);
    assert_eq!(blocked(&out).reason, BlockReason::CovNotInEdition);
}

/// input-link-multiple-candidates (golden E3): several sales configurations applicable
/// on the contract date is the only ambiguity that is `multiple_candidates`.
#[test]
fn input_link_multiple_candidates() {
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
    let out = run(&candidate_snapshot(&a), &q);
    let b = blocked(&out);
    assert_eq!(b.reason, BlockReason::MultipleCandidates);
    assert!(b.held[0].contains("복수"), "{:?}", b.held);
    // and config_select reports the same block with the competing ids
    let sel = config_select(&candidate_snapshot(&a), &q.configs, q.contract_date);
    match sel {
        ConfigSelection::Blocked(ConfigBlock::MultipleCandidates { candidates, .. }) => {
            assert!(candidates.contains(&"sc:synthetic_overlap".to_string()));
            assert!(candidates.contains(&HANA_NEW.to_string()));
        }
        other => panic!("expected multiple_candidates, got {other:?}"),
    }
}

/// input-link-order-independent (golden E4): reversing the candidate list, or the stored
/// assertion order, changes neither the outcomes nor the blocked reasons.
#[test]
fn input_link_order_independent() {
    let snap = release_snapshot();
    for id in ["Q1", "Q9", "Q10"] {
        let q = question(id);
        let mut rev = question(id);
        rev.configs.reverse();
        let (a, b) = (run(&snap, &q), run(&snap, &rev));
        assert_eq!(outcome(&a), outcome(&b), "{id}");
        assert_eq!(a.chain, b.chain, "{id}");
        assert_eq!(a.engine_calls, b.engine_calls, "{id}");
    }
    // reversed stored order too
    let mut a = abox();
    let hl = get(&a, "assertions", "a:hana_doc_link");
    push(
        &mut a,
        "assertions",
        with(&hl, &[("id", json!("a:aa_first"))]),
    );
    let mut rev_abox = a.clone();
    rev_abox.section_mut("assertions").reverse();
    let mut rq = q1();
    rq.configs.reverse();
    assert_eq!(
        run(&candidate_snapshot(&a), &q1()).chain,
        run(&candidate_snapshot(&rev_abox), &rq).chain
    );
}

/// input-link-multi-edition-config (golden S01·S01b, 재검토 e02755a 재현): one sales
/// configuration using several terms editions is normal, never `multiple_candidates`;
/// but an unapproved link of the requested edition holds the conclusion.
#[test]
fn input_link_multi_edition_config() {
    // (a) one more evidence assertion for the same (config, edition) link changes nothing
    let mut a = abox();
    let hl = get(&a, "assertions", "a:hana_doc_link");
    push(
        &mut a,
        "assertions",
        with(&hl, &[("id", json!("a:hana_doc_link_more_evidence"))]),
    );
    let out = run(&candidate_snapshot(&a), &q1());
    assert_eq!(outcome(&out), base_q1());
    assert_eq!(
        out.chain.linked().unwrap().link_assertions,
        ["a:hana_doc_link", "a:hana_doc_link_more_evidence"]
    );

    // (b) a second edition (e.g. 보통약관 + another 특약 판) on the same configuration is
    // not ambiguity; with the scope confirmed complete the conclusion stands.
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
    push(&mut a, "assertions", scope_complete(HANA_NEW, "accepted"));
    let out = run(&candidate_snapshot(&a), &q1());
    assert_eq!(outcome(&out), base_q1());
    assert_eq!(out.engine_calls, 1);

    // (c) an unapproved link of the requested edition holds the conclusion, engine 0 calls
    let mut a = abox();
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
    let out = run(&candidate_snapshot(&a), &q1());
    let b = blocked(&out);
    assert_eq!(b.reason, BlockReason::LinkUnapproved);
    assert_eq!(b.held, ["a:hana_doc_link_dup_hold:hold"]);
}

/// input-link-unknown-scope-hold (golden T01, 재검토 10f470c 재현): a link that does not
/// say which edition it means cannot be shown unrelated to the requested coverage, so
/// the conclusion holds as `scope_unknown` even with zero constraint violations.
#[test]
fn input_link_unknown_scope_hold() {
    let mut a = abox();
    let hl = get(&a, "assertions", "a:hana_doc_link");
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
    let out = run(&candidate_snapshot(&a), &q1());
    let b = blocked(&out);
    assert_eq!(b.reason, BlockReason::ScopeUnknown);
    assert_eq!(b.held, ["a:unknown_scope_link:scope_unknown"]);
    assert!(
        out.rule.is_none(),
        "no rule is chosen when scope is unknown"
    );

    // the golden Q9/Q10 are scope_unknown for the same reason on the frozen release
    let snap = release_snapshot();
    for (id, held) in [("Q9", "a:lotte_doc_link"), ("Q10", "a:hana_old_doc_link")] {
        let out = run(&snap, &question(id));
        let b = blocked(&out);
        assert_eq!(b.reason, BlockReason::ScopeUnknown, "{id}");
        assert_eq!(b.held, [format!("{held}:scope_unknown")], "{id}");
    }
}

/// input-link-unrelated-rider-allowed (golden T01·U01): an edition can be skipped only
/// when both (가) an approved `application_scope_complete` says the configuration's
/// applications were all checked and (나) no `applies_to` reaches the requested coverage
/// from that edition. Then even a held link of that edition does not block.
#[test]
fn input_link_unrelated_rider_allowed() {
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
    let hl = get(&a, "assertions", "a:hana_doc_link");
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
    push(&mut a, "assertions", scope_complete(HANA_NEW, "accepted"));
    let out = run(&candidate_snapshot(&a), &q1());
    assert_eq!(outcome(&out), base_q1());
    assert_eq!(out.engine_calls, 1);
}

/// input-link-competing-editions-hold (golden T01): the requested coverage defined in
/// two editions the configuration uses is `competing_editions`; order changes nothing.
#[test]
fn input_link_competing_editions_hold() {
    let mut a = abox();
    let ed = get(&a, "terms_editions", HANA_ED);
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
    let hl = get(&a, "assertions", "a:hana_doc_link");
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
    let out = run(&candidate_snapshot(&a), &q1());
    let b = blocked(&out);
    assert_eq!(b.reason, BlockReason::CompetingEditions);
    assert!(b.held[0].contains("판 후보 복수"), "{:?}", b.held);
    let mut rq = q1();
    rq.configs.reverse();
    assert_eq!(out.chain, run(&candidate_snapshot(&a), &rq).chain);
}

fn with_other_main(applies: Option<&str>, complete: Option<&str>) -> Snapshot {
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
        push(&mut a, "assertions", scope_complete(HANA_NEW, st));
    }
    candidate_snapshot(&a)
}

/// input-link-other-edition-applies-hold (재검토 U01): another edition applies a
/// condition to the requested coverage and the rule's basis does not cover that edition —
/// definition site (`in_edition`) and application (`applies_to`) are different things.
#[test]
fn input_link_other_edition_applies_hold() {
    // the rule does not cover the applying edition → applies_from_other_edition_unmodeled
    let out = run(&with_other_main(Some("accepted"), Some("accepted")), &q1());
    let b = blocked(&out);
    assert_eq!(b.reason, BlockReason::AppliesFromOtherEditionUnmodeled);
    assert_eq!(
        b.held,
        ["ted:synthetic_main@2607:applies_from_other_edition_unmodeled"]
    );
    // an unapproved applies_to is held as unverified application scope
    let out = run(&with_other_main(Some("hold"), Some("accepted")), &q1());
    let b = blocked(&out);
    assert_eq!(b.reason, BlockReason::ApplicationScopeUnverified);
    assert_eq!(b.held, ["a:synthetic_main_applies:applies_unconfirmed"]);
}

/// input-link-application-scope-unverified-hold (재검토 U01): without an approved
/// `application_scope_complete` (the service default), a second edition on the
/// configuration cannot be skipped — a different edition id alone proves nothing.
#[test]
fn input_link_application_scope_unverified_hold() {
    // no application_scope_complete at all → application_scope_unverified, engine 0 calls
    let out = run(&with_other_main(None, None), &q1());
    let b = blocked(&out);
    assert_eq!(b.reason, BlockReason::ApplicationScopeUnverified);
    assert_eq!(b.held, [format!("{HANA_NEW}:application_scope_unverified")]);
    // a held completeness claim does not count either
    let out = run(&with_other_main(None, Some("hold")), &q1());
    assert_eq!(
        blocked(&out).reason,
        BlockReason::ApplicationScopeUnverified
    );
    // and with the completeness claim approved, the unrelated edition is skipped
    let out = run(&with_other_main(None, Some("accepted")), &q1());
    assert_eq!(outcome(&out), base_q1());
    assert_eq!(out.engine_calls, 1);
}
