//! Correction-chain (판) behaviour — includes the required test `need-criteria-versioned`.

mod common;

use common::*;
use onjeon_contracts::{AssertionOrigin, CorrectionReason, CriterionSourceKind};
use onjeon_criteria::*;

/// `need-criteria-versioned` (T-KN-12 필수 시험):
/// 1. 기준 항목을 v1→v2로 정정하면 v1이 지워지지 않고 v2가 supersedes로 잇는다.
/// 2. 출처 없는 기준 판은 release에 들어가지 못한다.
/// 3. 기준 판이 '기본 필요액' 값을 담으면 D-08 기록 없이는 거부된다(기본값 후보 적재 과제의 경로만).
#[test]
fn need_criteria_versioned() {
    // (1) 정정은 새 판 + supersedes. 옛 판은 지워지지 않는다.
    let mut s = CriterionStore::new();
    s.insert_criterion(criterion("crit:a", CriterionKind::PriorityRule))
        .unwrap();
    s.insert_version(version("crit:a", 1)).unwrap();
    let mut v2 = version("crit:a", 2);
    v2.supersedes = Some("crit:a@1".into());
    v2.correction_reason = Some(CorrectionReason::SourceChanged);
    s.insert_version(v2).unwrap();

    assert!(s.version("crit:a@1").is_some(), "v1 stays in the store");
    assert_eq!(s.tip("crit:a").unwrap().id, "crit:a@2");
    assert_eq!(
        s.version("crit:a@2").unwrap().supersedes.as_deref(),
        Some("crit:a@1"),
        "v2 links back to v1"
    );
    assert_eq!(s.superseded_ids(), vec!["crit:a@1".to_string()]);

    // (2) 출처 없는 기준 판은 저장소에 못 들어오고 릴리스에도 못 들어간다.
    let mut bare = version("crit:a", 3);
    bare.supersedes = Some("crit:a@2".into());
    bare.correction_reason = Some(CorrectionReason::SourceChanged);
    bare.sources.clear();
    let e = s.insert_version(bare).unwrap_err();
    assert!(matches!(e, CriteriaError::NoSource { .. }), "{e}");

    // (3) 기본 필요액 값은 기준 판에 담기지 않는다 — D-08 적용 승인 기록(T-KN-14)과
    // 기본값 후보 경로(T-KN-13, data/criteria/defaults/)가 아니면 거부.
    for key in ["default_need_amount", "defaults", "defaultValue"] {
        let text = file_json(&serde_json::json!({
            "versions": [{ "version": 1, key: 12_000_000 }]
        }));
        let mut st = CriterionStore::new();
        let e = load_str(&text, &mut st).unwrap_err();
        assert!(
            matches!(e, CriteriaError::DefaultOutsideGate { .. }),
            "key {key}: {e}"
        );
    }
}

#[test]
fn correction_pairs_supersedes_and_reason() {
    let mut s = store_with(1);
    // supersedes 없이 version 2
    let mut v = version("crit:a", 2);
    v.supersedes = None;
    v.correction_reason = None;
    assert!(matches!(
        s.insert_version(v).unwrap_err(),
        CriteriaError::Supersedes { .. }
    ));
    // supersedes 있는데 reason 없음
    let mut v = version("crit:a", 2);
    v.correction_reason = None;
    assert!(matches!(
        s.insert_version(v).unwrap_err(),
        CriteriaError::Supersedes { .. }
    ));
    // reason 있는데 supersedes 없음
    let mut v = version("crit:a", 2);
    v.supersedes = None;
    v.correction_reason = Some(CorrectionReason::ErrorCorrection);
    assert!(matches!(
        s.insert_version(v).unwrap_err(),
        CriteriaError::Supersedes { .. }
    ));
}

#[test]
fn first_version_carries_no_supersedes() {
    let mut s = CriterionStore::new();
    s.insert_criterion(criterion("crit:a", CriterionKind::QuestionRule))
        .unwrap();
    let mut v = version("crit:a", 1);
    v.supersedes = Some("crit:a@0".into());
    v.correction_reason = Some(CorrectionReason::ErrorCorrection);
    assert!(matches!(
        s.insert_version(v).unwrap_err(),
        CriteriaError::Supersedes { .. }
    ));
}

#[test]
fn supersedes_is_the_directly_previous_version() {
    let mut s = store_with(2);
    // v3가 v1을 건너뛰고 v1을 대체 → 거부
    let mut v = version("crit:a", 3);
    v.supersedes = Some("crit:a@1".into());
    assert!(matches!(
        s.insert_version(v).unwrap_err(),
        CriteriaError::Supersedes { .. }
    ));
    // 다른 기준의 판을 대체 → 거부
    s.insert_criterion(criterion("crit:b", CriterionKind::ReferenceStat))
        .unwrap();
    let mut v = version("crit:a", 3);
    v.supersedes = Some("crit:b@1".into());
    assert!(matches!(
        s.insert_version(v).unwrap_err(),
        CriteriaError::Supersedes { .. }
    ));
    // 아직 저장되지 않은 판을 대체 → 거부
    let mut v = version("crit:a", 4);
    v.supersedes = Some("crit:a@3".into());
    assert!(matches!(
        s.insert_version(v).unwrap_err(),
        CriteriaError::Supersedes { .. }
    ));
}

#[test]
fn duplicate_ids_are_rejected() {
    let mut s = store_with(1);
    assert!(matches!(
        s.insert_criterion(criterion("crit:a", CriterionKind::QuestionRule))
            .unwrap_err(),
        CriteriaError::Duplicate { .. }
    ));
    assert!(matches!(
        s.insert_version(version("crit:a", 1)).unwrap_err(),
        CriteriaError::Duplicate { .. }
    ));
    // 존재하지 않는 기준의 판
    assert!(matches!(
        s.insert_version(version("crit:ghost", 1)).unwrap_err(),
        CriteriaError::UnknownCriterion { .. }
    ));
}

#[test]
fn version_id_must_match_criterion_and_number() {
    let mut s = store_with(1);
    let mut v = version("crit:a", 2);
    v.id = "crit:a@9".into();
    assert!(matches!(
        s.insert_version(v).unwrap_err(),
        CriteriaError::Id { .. }
    ));
    // 비정규 형식(선행 0)
    let mut v = version("crit:a", 2);
    v.id = "crit:a@02".into();
    assert!(matches!(
        s.insert_version(v).unwrap_err(),
        CriteriaError::Id { .. }
    ));
    assert!(CriterionStore::is_version_id("crit:a@2"));
    assert!(!CriterionStore::is_version_id("crit:a@02"));
    assert!(!CriterionStore::is_version_id("crit:a"));
    assert_eq!(
        CriterionStore::criterion_of("crit:a@2"),
        Some("crit:a".to_string())
    );
}

#[test]
fn correction_chain_loads_from_files() {
    let text = file_json(&serde_json::json!({
        "versions": [
            {
                "version": 1,
                "valid_from": "2026-10-20",
                "sources": [{"ref": OBS_REF, "evidence_kind": "public_statistic"}],
                "rationale": "첫 판",
                "recorded_at": "2026-10-20T00:00:00Z",
                "origin": "pipeline"
            },
            {
                "version": 2,
                "valid_from": "2026-10-21",
                "supersedes": "crit:file-a@1",
                "correction_reason": "source_changed",
                "sources": [{"ref": CLAUSE_REF, "evidence_kind": "terms_fact"}],
                "rationale": "출처 갱신",
                "recorded_at": "2026-10-21T00:00:00Z",
                "origin": "pipeline"
            }
        ]
    }));
    let mut s = CriterionStore::new();
    load_str(&text, &mut s).unwrap();
    assert_eq!(s.tip("crit:file-a").unwrap().id, "crit:file-a@2");
    assert!(s.version("crit:file-a@1").is_some());
    assert_eq!(
        s.version("crit:file-a@2").unwrap().correction_reason,
        Some(CorrectionReason::SourceChanged)
    );
}

#[test]
fn fixture_versions_load_but_stay_marked() {
    // 시험 전용 자료는 origin=fixture로만 온다 — fixture 판은 적재되지만 표식이 유지된다.
    let mut s = CriterionStore::new();
    load_str(&file_json(&serde_json::json!({})), &mut s).unwrap();
    assert_eq!(
        s.version("crit:file-a@1").unwrap().origin,
        AssertionOrigin::Fixture
    );
    assert_eq!(
        s.version("crit:file-a@1").unwrap().sources[0].evidence_kind,
        CriterionSourceKind::PublicStatistic
    );
}
