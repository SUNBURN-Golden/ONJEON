//! Release freezing (K15) and the separation of reproduction from usage restriction: golden I1~I7.

mod common;
use common::*;
use onjeon_ontology::*;
use serde_json::json;

fn base() -> std::collections::BTreeMap<String, Answer> {
    answer_all(&release_view(&abox(), CURRENT))
}

fn n_frozen_assertions(a: &Abox) -> usize {
    a.releases
        .iter()
        .find(|r| r.id == CURRENT)
        .unwrap()
        .freeze
        .members["assertions"]
        .len()
}

/// test id: release-future-supersedes-frozen (golden I1)
#[test]
fn release_future_supersedes_frozen() {
    let mut a = abox();
    let old = get(&a, "assertions", "a:hana_doc_link");
    push(
        &mut a,
        "assertions",
        with(
            &old,
            &[
                ("id", json!("a:hana_doc_link_v2")),
                ("supersedes", json!("a:hana_doc_link")),
                ("review_status", json!("hold")),
                ("hold_reason", json!("reference_unresolved")),
                ("correction_reason", json!("출처 변경")),
            ],
        ),
    );
    let v = release_view(&a, CURRENT);
    assert_eq!(v.assertions.len(), n_frozen_assertions(&a));
    assert!(v.assertion("a:hana_doc_link_v2").is_none());
    assert!(check(&v).is_empty());
    // all 11 results and explanations are unchanged ...
    assert_eq!(answer_all(&v), base());
    // ... while the not-yet-frozen candidate already sees the correction
    let cand = answer(&candidate_view(&a).unwrap(), &question("Q1"));
    assert_eq!(cand.outcome, Outcome::Blocked);
    assert_eq!(cand.engine_calls, 0);
}

#[test]
fn i2_in_place_edit_is_k15() {
    let mut a = abox();
    set(
        &mut a,
        "assertions",
        "a:hana_cov_def",
        "note",
        json!("제자리 수정"),
    );
    let vs = check(&release_view(&a, CURRENT));
    assert_eq!(codes(&vs), ["K15"]);
    assert_eq!(
        vs[0].message,
        "구성원 내용이 제자리에서 바뀜(내용 해시 불일치)"
    );
}

#[test]
fn i3_deleted_member_is_k15() {
    let mut a = abox();
    a.section_mut("assertions")
        .retain(|x| x["id"] != "a:hi_doc_link");
    let vs = check(&release_view(&a, CURRENT));
    assert!(
        !vs.is_empty() && vs.iter().all(|v| v.code == "K15"),
        "{vs:?}"
    );
    assert!(vs
        .iter()
        .any(|v| v.message.contains("구성원이 저장소에 없음")));
}

#[test]
fn i4_swapped_rule_file_is_k15() {
    let mut a = abox();
    with_bad_rule(&mut a);
    let vs = check(&release_view(&a, CURRENT));
    assert!(
        vs.iter()
            .any(|v| v.code == "K15" && v.message == "규칙 파일 해시가 고정값과 다름"),
        "{vs:?}"
    );
    // same path, other bytes
    let mut b = abox();
    b.rule_files
        .get_mut("규칙/hana-2601-3d-cancer-dx.json")
        .unwrap()
        .push(b' ');
    let vs = check(&release_view(&b, CURRENT));
    assert!(vs.iter().any(|v| v.code == "K15"), "{vs:?}");
}

#[test]
fn i5_replaced_reference_nodes_and_links_do_not_change_the_frozen_release() {
    let mut a = abox();
    let c44 = get(&a, "nodes", "codes:c44");
    push(
        &mut a,
        "nodes",
        with(
            &c44,
            &[
                ("id", json!("codes:c44@v2")),
                ("ranges", json!(["C44", "C16"])),
                ("label", json!("C44(자체 시험용 가상 개정)")),
            ],
        ),
    );
    let exc = get(&a, "assertions", "a:hana_cat_exc_c44");
    push(
        &mut a,
        "assertions",
        with(
            &exc,
            &[
                ("id", json!("a:hana_cat_exc_c44_v2")),
                ("object", json!("codes:c44@v2")),
                ("supersedes", json!("a:hana_cat_exc_c44")),
                ("correction_reason", json!("해석 개선")),
            ],
        ),
    );
    let hw = get(&a, "nodes", "cond:hi_waiting");
    push(
        &mut a,
        "nodes",
        with(
            &hw,
            &[
                ("id", json!("cond:hi_waiting@v2")),
                ("duration", json!({"value": 30, "unit": "day"})),
            ],
        ),
    );
    let hc = a
        .section("assertions")
        .iter()
        .find(|x| x["predicate"] == "has_condition" && x["object"] == "cond:hi_waiting")
        .unwrap()
        .clone();
    let hc_id = hc["id"].as_str().unwrap().to_string();
    push(
        &mut a,
        "assertions",
        with(
            &hc,
            &[
                ("id", json!(format!("{hc_id}_v2"))),
                ("object", json!("cond:hi_waiting@v2")),
                ("supersedes", json!(hc_id)),
                ("correction_reason", json!("해석 개선")),
            ],
        ),
    );
    let hl = get(&a, "assertions", "a:hi_doc_link");
    let mut time = hl["time"].clone();
    time["valid_to"] = json!("2026-08-10");
    push(
        &mut a,
        "assertions",
        with(
            &hl,
            &[
                ("id", json!("a:hi_doc_link_v2")),
                ("time", time),
                ("supersedes", json!("a:hi_doc_link")),
                ("correction_reason", json!("출처 변경")),
            ],
        ),
    );

    let v = release_view(&a, CURRENT);
    assert!(check(&v).is_empty());
    assert_eq!(answer_all(&v), base());
    let cand = answer_all(&candidate_view(&a).unwrap());
    assert_eq!(
        cand["Q1"].outcome,
        Outcome::NotPayable,
        "C16 now excluded by the replaced code set"
    );
    assert_eq!(
        cand["Q6"].outcome,
        Outcome::Blocked,
        "the replaced link ends before the contract date"
    );
}

#[test]
fn i6_in_place_edit_of_a_reference_node_is_k15() {
    let mut a = abox();
    set(
        &mut a,
        "nodes",
        "codes:c44",
        "ranges",
        json!(["C44", "C16"]),
    );
    let vs = check(&release_view(&a, CURRENT));
    assert_eq!(codes(&vs), ["K15"]);
}

#[test]
fn i7_notice_restricts_service_not_reproduction() {
    let mut a = abox();
    a.release_notices = vec![ReleaseNotice {
        id: "notice:t1".into(),
        release: CURRENT.into(),
        affects: vec!["cov:hana_2_1".into()],
        affects_sales_configs: vec![],
        state: "restricted".into(),
        reason: "자체 시험: r26의 하나 2-1 해석 오류 확인".into(),
        lifted_at: None,
    }];
    let v = release_view(&a, CURRENT);
    assert!(v.integrity.is_empty());
    assert_eq!(answer_all(&v), base());
    let q1 = service_allowed(CURRENT, "cov:hana_2_1", &a.release_notices);
    assert!(!q1.allowed);
    assert_eq!(q1.notices[0].id, "notice:t1");
    assert!(service_allowed(CURRENT, "cov:hi_2_5", &a.release_notices).allowed);
    assert!(service_allowed("rel:case-r25", "cov:hana_2_1", &a.release_notices).allowed);
    // narrowed by sales configuration, and lifted notices restrict nothing
    let mut n = a.release_notices[0].clone();
    n.affects_sales_configs = vec!["sc:hana_2601_3d_v20260701".into()];
    assert!(
        !service_allowed_for(
            CURRENT,
            "cov:hana_2_1",
            Some("sc:hana_2601_3d_v20260701"),
            &[n.clone()]
        )
        .allowed
    );
    assert!(
        service_allowed_for(
            CURRENT,
            "cov:hana_2_1",
            Some("sc:hana_2601_3d_v20260101"),
            &[n.clone()]
        )
        .allowed
    );
    n.lifted_at = Some("2026-10-20".into());
    assert!(service_allowed(CURRENT, "cov:hana_2_1", &[n]).allowed);
}

#[test]
fn freeze_is_order_independent_and_hash_covers_rule_files() {
    let a = abox();
    let rel = a.releases.iter().find(|r| r.id == CURRENT).unwrap().clone();
    let mut shuffled = rel.freeze.members.clone();
    for ids in shuffled.values_mut() {
        ids.reverse();
    }
    let f = freeze(&a, &shuffled, "stage").unwrap();
    assert_eq!(f.content_sha256, rel.freeze.content_sha256);
    assert_eq!(f.members, rel.freeze.members);
    assert_eq!(f.input_stage_edition.as_deref(), Some("stage"));
    let mut b = abox();
    b.rule_files
        .get_mut("규칙/hana-2601-3d-cancer-dx.json")
        .unwrap()
        .push(b'\n');
    assert_ne!(
        freeze(&b, &shuffled, "stage").unwrap().content_sha256,
        rel.freeze.content_sha256
    );
    // a release never lists ids the store lacks silently: the missing rule file hashes to null
    let mut c = abox();
    c.rule_files.clear();
    assert!(freeze(&c, &shuffled, "stage")
        .unwrap()
        .rule_files
        .values()
        .all(Option::is_none));
}

#[test]
fn unknown_release_is_an_error() {
    assert!(matches!(
        view(&abox(), "rel:nope"),
        Err(OntologyError::Unknown(_))
    ));
}
