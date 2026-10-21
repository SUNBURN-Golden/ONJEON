//! File-format and loader validation for `data/criteria/criteria/*.json`.

mod common;

use common::*;
use onjeon_criteria::*;

#[test]
fn valid_file_loads() {
    let mut s = CriterionStore::new();
    let id = load_str(&file_json(&serde_json::json!({})), &mut s).unwrap();
    assert_eq!(id, "crit:file-a");
    let c = s.criterion("crit:file-a").unwrap();
    assert_eq!(c.kind, CriterionKind::QuestionRule);
    assert_eq!(c.scope.situations, vec!["필요성 판단".to_string()]);
}

#[test]
fn unknown_fields_are_rejected() {
    // 알 수 없는 키는 성공으로 처리하지 않는다(어휘 규칙 4와 같은 방향).
    let text = file_json(&serde_json::json!({
        "versions": [{ "version": 1, "payload": {"need_krw": 1} }]
    }));
    let mut s = CriterionStore::new();
    assert!(matches!(
        load_str(&text, &mut s).unwrap_err(),
        CriteriaError::Shape(_)
    ));
}

fn base_doc() -> serde_json::Value {
    serde_json::from_str(&file_json(&serde_json::json!({}))).unwrap()
}

#[test]
fn scope_must_be_present_and_nonempty() {
    // situations 키가 아예 없는 파일 → 역직렬화·범위 검사 중 하나가 거부한다.
    let mut doc = base_doc();
    doc["criterion"]["scope"]
        .as_object_mut()
        .unwrap()
        .remove("situations");
    let mut s = CriterionStore::new();
    let e = load_str(&doc.to_string(), &mut s).unwrap_err();
    assert!(
        matches!(e, CriteriaError::Shape(_) | CriteriaError::Scope { .. }),
        "{e}"
    );

    for situations in [serde_json::json!([]), serde_json::json!([" "])] {
        let mut doc = base_doc();
        doc["criterion"]["scope"]["situations"] = situations;
        let mut s = CriterionStore::new();
        let e = load_str(&doc.to_string(), &mut s).unwrap_err();
        assert!(
            matches!(e, CriteriaError::Scope { .. } | CriteriaError::Shape(_)),
            "{e}"
        );
    }
}

#[test]
fn sources_require_a_ref_of_the_right_kind() {
    // 허용: raw:sha256:<64>, clause:<seg...>, obs:src:<...>
    for good in [RAW_REF, OBS_REF, CLAUSE_REF] {
        let text = file_json(&serde_json::json!({
            "versions": [{ "version": 1, "sources": [{"ref": good, "evidence_kind": "terms_fact"}] }]
        }));
        let mut s = CriterionStore::new();
        load_str(&text, &mut s).unwrap_or_else(|e| panic!("ref {good}: {e}"));
    }
    // 그 외 근거 참조 종류나 임의 문자열은 거부
    for bad in [
        "ted:01H8X4K7J8M9N0P1Q2R3S4T5V6",
        "assertion:01H8X4K7J8M9N0P1Q2R3S4T5V6",
        "premium:01H8X4K7J8M9N0P1Q2R3S4T5V6",
        "raw:sha256:nothex",
        "clause:not-a-clause",
        "obs:not-an-obs",
        "https://example.com/x",
        "",
    ] {
        let text = file_json(&serde_json::json!({
            "versions": [{ "version": 1, "sources": [{"ref": bad, "evidence_kind": "terms_fact"}] }]
        }));
        let mut s = CriterionStore::new();
        let e = load_str(&text, &mut s).unwrap_err();
        assert!(
            matches!(
                e,
                CriteriaError::BadSourceRef { .. } | CriteriaError::NoSource { .. }
            ),
            "ref {bad}: {e}"
        );
    }
}

#[test]
fn sources_are_required_and_deduped() {
    // 출처 없음 — sources 키가 아예 없을 때와 빈 목록일 때 둘 다 거부.
    for variant in {
        let mut a = base_doc();
        a["versions"][0].as_object_mut().unwrap().remove("sources");
        let mut b = base_doc();
        b["versions"][0]["sources"] = serde_json::json!([]);
        [a, b]
    } {
        let mut s = CriterionStore::new();
        let e = load_str(&variant.to_string(), &mut s).unwrap_err();
        assert!(matches!(e, CriteriaError::NoSource { .. }), "{e}");
    }
    // 같은 출처 두 번 → (version, ref) 기본키 위반과 같음
    let text = file_json(&serde_json::json!({
        "versions": [{ "version": 1, "sources": [
            {"ref": RAW_REF, "evidence_kind": "terms_fact"},
            {"ref": RAW_REF, "evidence_kind": "statute"}
        ] }]
    }));
    let mut s = CriterionStore::new();
    assert!(matches!(
        load_str(&text, &mut s).unwrap_err(),
        CriteriaError::DuplicateSource { .. }
    ));
}

#[test]
fn evidence_kind_comes_from_the_vocabulary() {
    // 어휘 밖 값은 역직렬화 실패다(성공 기본값 없음).
    let text = file_json(&serde_json::json!({
        "versions": [{ "version": 1, "sources": [{"ref": RAW_REF, "evidence_kind": "guess"}] }]
    }));
    let mut s = CriterionStore::new();
    assert!(matches!(
        load_str(&text, &mut s).unwrap_err(),
        CriteriaError::Shape(_)
    ));
    for kind in [
        "public_statistic",
        "statute",
        "regulator_notice",
        "terms_fact",
        "editorial",
    ] {
        let text = file_json(&serde_json::json!({
            "versions": [{ "version": 1, "sources": [{"ref": RAW_REF, "evidence_kind": kind}] }]
        }));
        let mut s = CriterionStore::new();
        load_str(&text, &mut s).unwrap_or_else(|e| panic!("kind {kind}: {e}"));
    }
}

#[test]
fn kinds_are_the_four_contract_values() {
    for (kind, ok) in [
        ("priority_rule", true),
        ("reference_stat", true),
        ("applicability_rule", true),
        ("question_rule", true),
        ("score_rule", false),
    ] {
        let text = file_json(&serde_json::json!({"criterion": {"kind": kind}}));
        let mut s = CriterionStore::new();
        let r = load_str(&text, &mut s);
        assert_eq!(r.is_ok(), ok, "kind {kind}: {r:?}");
    }
}

#[test]
fn dates_are_real_and_ordered() {
    for (from, to, ok) in [
        ("2026-10-20", None, true),
        ("2026-10-20", Some("2026-10-20"), true),
        ("2026-13-01", None, false),
        ("2026-10-32", None, false),
        ("2026-10-20", Some("2026-10-19"), false),
        ("20-10-20", None, false),
    ] {
        let mut v = serde_json::json!({ "version": 1, "valid_from": from });
        if let Some(t) = to {
            v["valid_to"] = serde_json::json!(t);
        }
        let text = file_json(&serde_json::json!({ "versions": [v] }));
        let mut s = CriterionStore::new();
        let r = load_str(&text, &mut s);
        assert_eq!(r.is_ok(), ok, "{from}..{to:?}: {r:?}");
    }
    // recorded_at은 RFC 3339여야 한다
    let text = file_json(&serde_json::json!({
        "versions": [{ "version": 1, "recorded_at": "2026-10-20" }]
    }));
    let mut s = CriterionStore::new();
    assert!(matches!(
        load_str(&text, &mut s).unwrap_err(),
        CriteriaError::BadTime { .. }
    ));
}

#[test]
fn private_zone_ids_never_enter_public_criteria() {
    // K8: contract:/person:/upload:/del:/consent:/assume: 접두어는 어느 문자열에도 못 온다.
    for over in [
        serde_json::json!({"criterion": {"label": "contract:abc 를 본다"}}),
        serde_json::json!({"criterion": {"scope": {"situations": ["person:x 상황"], "subjects": ["전체"]}}}),
        serde_json::json!({"versions": [{ "version": 1, "rationale": "assume:01 참조" }]}),
        serde_json::json!({"versions": [{ "version": 1, "sources": [{"ref": "obs:src:o/c/1/2026-10-09T04:22:22Z/0123456789abcdef", "evidence_kind": "editorial"}], "rationale": "del:x" }]}),
    ] {
        let mut s = CriterionStore::new();
        let e = load_str(&file_json(&over), &mut s).unwrap_err();
        assert!(matches!(e, CriteriaError::PrivateId { .. }), "{e}");
    }
}

#[test]
fn default_like_keys_are_refused_anywhere() {
    // 기본 필요액·기본값 후보는 이 경로의 것이 아니다(T-KN-13의 defaults/ 경로 + D-08 기록이 있어야 한다).
    for over in [
        serde_json::json!({"default_need_amount": 5_000_000}),
        serde_json::json!({"criterion": {"defaults": {}}}),
        serde_json::json!({"versions": [{ "version": 1, "default": true }]}),
        serde_json::json!({"versions": [{ "version": 1, "sources": [{"ref": RAW_REF, "evidence_kind": "editorial", "default_weight": 1}] }]}),
    ] {
        let mut s = CriterionStore::new();
        let e = load_str(&file_json(&over), &mut s).unwrap_err();
        assert!(matches!(e, CriteriaError::DefaultOutsideGate { .. }), "{e}");
    }
}

#[test]
fn load_dir_reads_sorted_json_files() {
    let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/criteria");
    let s = load_dir(&dir).unwrap();
    assert!(s.criterion("crit:fx-question").is_some());
    assert!(s.criterion("crit:fx-priority").is_some());
    assert_eq!(s.tip("crit:fx-priority").unwrap().id, "crit:fx-priority@2");
    // 없는 디렉터리는 빈 저장소(기준 0건은 정상 상태)
    let s = load_dir(&dir.join("nope")).unwrap();
    assert!(s.criteria().next().is_none());
}

#[test]
fn release_file_loads_and_checks_id() {
    let s = store_with(1);
    let rel = freeze(&s, "crel:20261020-1", "2026-10-20T01:00:00Z").unwrap();
    let dir = std::env::temp_dir().join(format!("onj-crit-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let p = dir.join("crel:20261020-1.json");
    std::fs::write(&p, serde_json::to_string_pretty(&rel).unwrap()).unwrap();
    let back = load_release_file(&p).unwrap();
    assert_eq!(back, rel);
    let bad = dir.join("bad.json");
    std::fs::write(&bad, r#"{"id":"rel:20261020-1","members":{"criterion_versions":[]},"content_sha256":"x","frozen_at":"2026-10-20T01:00:00Z"}"#).unwrap();
    assert!(matches!(
        load_release_file(&bad).unwrap_err(),
        CriteriaError::BadReleaseId { .. }
    ));
    let _ = std::fs::remove_dir_all(&dir);
}
