//! Criteria releases (불변, `crel:` 별도 ID)와 변경 목록.

mod common;

use common::*;
use onjeon_contracts::CorrectionReason;
use onjeon_criteria::*;

#[test]
fn release_id_is_separate_from_knowledge_release() {
    // 기준 릴리스는 지식 릴리스(`rel:`)와 별도 ID 공간(`crel:`)을 갖는다.
    let s = store_with(1);
    freeze(&s, "crel:20261020-1", "2026-10-20T01:00:00Z").unwrap();
    for bad in [
        "rel:20261020-1",    // 지식 릴리스 공간
        "crel:20261020",     // 번호 없음
        "crel:2026-10-20-1", // 날짜 형식
        "crel:x-1",
        "",
    ] {
        assert!(
            matches!(
                freeze(&s, bad, "2026-10-20T01:00:00Z").unwrap_err(),
                CriteriaError::BadReleaseId { .. }
            ),
            "id {bad}"
        );
    }
    assert!(is_release_id("crel:20261020-12"));
}

#[test]
fn freeze_lists_tip_versions_sorted_and_is_deterministic() {
    let mut s = store_with(2);
    s.insert_criterion(criterion("crit:b", CriterionKind::ReferenceStat))
        .unwrap();
    s.insert_version(version("crit:b", 1)).unwrap();

    let r1 = freeze(&s, "crel:20261020-1", "2026-10-20T01:00:00Z").unwrap();
    // 판 목록은 각 기준의 tip(최신 판) — 정정된 옛 판(crit:a@1)은 들어가지 않는다.
    assert_eq!(
        r1.members.criterion_versions,
        vec!["crit:a@2".to_string(), "crit:b@1".to_string()]
    );
    // 같은 저장소·같은 시각이면 같은 릴리스(내용 해시 결정적).
    let r2 = freeze(&s, "crel:20261020-1", "2026-10-20T01:00:00Z").unwrap();
    assert_eq!(r1, r2);
    verify(&s, &r1).unwrap();
}

#[test]
fn freeze_rejects_fixture_versions() {
    let mut s = CriterionStore::new();
    load_str(&file_json(&serde_json::json!({})), &mut s).unwrap();
    let e = freeze(&s, "crel:20261020-1", "2026-10-20T01:00:00Z").unwrap_err();
    match e {
        CriteriaError::FixtureInRelease { version_id } => {
            assert_eq!(version_id, "crit:file-a@1");
        }
        other => panic!("{other}"),
    }
}

#[test]
fn verify_catches_member_loss_and_in_place_edits() {
    let s = store_with(2);
    let rel = freeze(&s, "crel:20261020-1", "2026-10-20T01:00:00Z").unwrap();

    // 구성원 누락(삭제) → 무결성 실패. 파일 저장소에는 삭제가 없으므로
    // "빠진 구성원"은 더 작은 저장소로 재현한다.
    let smaller = store_with(1);
    let e = verify(&smaller, &rel).unwrap_err();
    match e {
        CriteriaError::ReleaseIntegrity { findings, .. } => {
            assert!(findings
                .iter()
                .any(|f| f.kind == "missing_member" && f.member_id == "crit:a@2"));
        }
        other => panic!("{other}"),
    }

    // 제자리 변경(내용 해시 불일치): 같은 id·다른 내용의 저장소를 수작업으로 만든다.
    let mut tampered = store_with(1);
    let mut v2 = version("crit:a", 2);
    v2.rationale = "바뀐 이유".into();
    tampered.insert_version(v2).unwrap();
    let e = verify(&tampered, &rel).unwrap_err();
    match e {
        CriteriaError::ReleaseIntegrity { findings, .. } => {
            assert!(findings.iter().any(|f| f.kind == "hash_mismatch"));
        }
        other => panic!("{other}"),
    }

    // 릴리스에 없는 자료가 저장소에 더 있어도 검증은 통과한다 — 릴리스는 판 목록만 읽는다.
    let mut bigger = store_with(2);
    bigger
        .insert_criterion(criterion("crit:later", CriterionKind::QuestionRule))
        .unwrap();
    bigger.insert_version(version("crit:later", 1)).unwrap();
    verify(&bigger, &rel).unwrap();
}

#[test]
fn release_file_round_trips() {
    let s = store_with(1);
    let rel = freeze(&s, "crel:20261020-1", "2026-10-20T01:00:00Z").unwrap();
    let text = serde_json::to_string_pretty(&rel).unwrap();
    let back: CriteriaRelease = serde_json::from_str(&text).unwrap();
    assert_eq!(rel, back);
    verify(&s, &back).unwrap();
}

#[test]
fn change_list_marks_added_corrected_removed() {
    let old_store = {
        let mut s = store_with(1);
        s.insert_criterion(criterion("crit:b", CriterionKind::ReferenceStat))
            .unwrap();
        s.insert_version(version("crit:b", 1)).unwrap();
        s
    };
    let old = freeze(&old_store, "crel:20261020-1", "2026-10-20T01:00:00Z").unwrap();

    // 정정(a@1→a@2), 추가(crit:c), 제거(crit:b가 판 목록에서 빠짐)
    let new_store = {
        let mut s = store_with(2);
        s.insert_criterion(criterion("crit:c", CriterionKind::QuestionRule))
            .unwrap();
        s.insert_version(version("crit:c", 1)).unwrap();
        s
    };
    let new = freeze(&new_store, "crel:20261021-1", "2026-10-21T01:00:00Z").unwrap();

    let list = diff_releases(&old, &new, Some(&new_store));
    let by_id = |id: &str| list.entries.iter().find(|e| e.criterion_id == id).unwrap();

    let a = by_id("crit:a");
    assert_eq!(a.kind, ChangeKind::Corrected);
    assert_eq!(a.before.as_deref(), Some("crit:a@1"));
    assert_eq!(a.after.as_deref(), Some("crit:a@2"));
    assert_eq!(a.correction_reason, Some(CorrectionReason::ErrorCorrection));

    assert_eq!(by_id("crit:c").kind, ChangeKind::Added);
    let b = by_id("crit:b");
    assert_eq!(b.kind, ChangeKind::Removed);
    assert_eq!(b.before.as_deref(), Some("crit:b@1"));

    // 영향 조회 입력: 어떤 결론이 영향받는지 찾을 때 쓰는 옛 판 id 목록.
    assert_eq!(
        list.affected_version_ids(),
        vec!["crit:a@1".to_string(), "crit:b@1".to_string()]
    );
    assert_eq!(list.from_release.as_deref(), Some("crel:20261020-1"));
    assert_eq!(list.to_release.as_deref(), Some("crel:20261021-1"));
}

#[test]
fn diff_to_tips_reports_corrections_since_release() {
    let s = store_with(1);
    let rel = freeze(&s, "crel:20261020-1", "2026-10-20T01:00:00Z").unwrap();

    // 릴리스 뒤 정정이 오면 — 변경 목록이 개인 영역의 영향 확인 입력이 된다.
    let mut s2 = store_with(1);
    s2.insert_version(version("crit:a", 2)).unwrap();
    let list = diff_to_tips(&s2, &rel);
    assert_eq!(list.entries.len(), 1);
    assert_eq!(list.entries[0].kind, ChangeKind::Corrected);
    assert_eq!(list.affected_version_ids(), vec!["crit:a@1".to_string()]);

    // 정정이 없으면 변경도 없다.
    let quiet = diff_to_tips(&s, &rel);
    assert!(quiet.entries.is_empty());
}
