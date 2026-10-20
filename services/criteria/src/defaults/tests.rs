//! Behaviour tests for default candidates (T-KN-13).
//!
//! Test material is `origin=fixture` (JSON strings built here). The shipped-dir
//! test reads `data/criteria/defaults/candidates/` — the only test that touches
//! the repo path; every version there must be `origin=pipeline`.

use super::*;
use crate::defaults::error::DefaultsError;
use crate::error::CriteriaError;
use crate::model::CriterionSource;
use onjeon_contracts::{AssertionOrigin, CriterionSourceKind};
use serde_json::json;

/// A grammar-valid `raw:sha256:` ref for fixture data (test-only value).
const RAW: &str = "raw:sha256:abababababababababababababababababababababababababababababababab";
const OBS: &str = "obs:src:klia/pub/1/2026-10-09T04:22:22Z/052d0204c9bc1cd1";

fn candidate_json(over: serde_json::Value) -> serde_json::Value {
    let mut base = json!({
        "candidate": {
            "id": "def:nhis_copay",
            "kind": "reference_stat",
            "label": "건강보험 본인부담 구조",
            "scope": {"situations": ["의료비 부담 추정"], "subjects": ["건강보험 가입자"]},
            "update_cycle": {"kind": "annual", "note": "시행령 별표 개정·고시 주기에 따름"},
            "applied": false,
            "recorded_at": "2026-10-20T00:00:00Z"
        },
        "versions": [{
            "version": 1,
            "valid_from": "2026-01-01",
            "value": {
                "kind": "structure",
                "summary": "요양기관 종별 본인부담률",
                "items": [
                    {"label": "입원", "rate_bp": 2000},
                    {"label": "외래(의원)", "rate_bp": 3000}
                ]
            },
            "sources": [{"ref": RAW, "evidence_kind": "public_statistic"}],
            "rationale": "첫 후보 판",
            "recorded_at": "2026-10-20T00:00:00Z",
            "origin": "fixture"
        }]
    });
    merge(&mut base, &over);
    base
}

fn merge(base: &mut serde_json::Value, over: &serde_json::Value) {
    match (base, over) {
        (serde_json::Value::Object(b), serde_json::Value::Object(o)) => {
            for (k, v) in o {
                merge(b.entry(k.clone()).or_insert(serde_json::Value::Null), v);
            }
        }
        (serde_json::Value::Array(b), serde_json::Value::Array(o)) => {
            if o.is_empty() {
                // An empty override array clears the base (e.g. `"sources": []`).
                *b = o.clone();
            } else {
                for (i, v) in o.iter().enumerate() {
                    if i < b.len() {
                        merge(&mut b[i], v);
                    } else {
                        b.push(v.clone());
                    }
                }
            }
        }
        (b, o) => *b = o.clone(),
    }
}

fn load_ok(over: serde_json::Value) -> DefaultsStore {
    let mut s = DefaultsStore::new();
    load_str(&candidate_json(over).to_string(), &mut s).unwrap();
    s
}

fn load_err(over: serde_json::Value) -> DefaultsError {
    let mut s = DefaultsStore::new();
    load_str(&candidate_json(over).to_string(), &mut s).unwrap_err()
}

// ---------------------------------------------------------------- admission

#[test]
fn candidate_loads_with_raw_public_statistic_source() {
    let s = load_ok(json!({}));
    let c = s.candidate("def:nhis_copay").unwrap();
    assert_eq!(c.kind, DefaultKind::ReferenceStat);
    assert!(!c.applied);
    assert_eq!(c.update_cycle.kind, UpdateCycleKind::Annual);
    let v = s.tip("def:nhis_copay").unwrap();
    assert_eq!(v.id, "def:nhis_copay@1");
    assert_eq!(v.sources.len(), 1);
    assert!(s.resolve("def:nhis_copay@1").is_some());
}

#[test]
fn unsourced_version_is_rejected() {
    // 수락 기준: 출처 없는 기본값이 없다 — sources:[]는 저장되지 않는다.
    let e = load_err(json!({"versions": [{"sources": []}]}));
    assert!(matches!(
        e,
        DefaultsError::Criteria(CriteriaError::NoSource { .. })
    ));
}

#[test]
fn non_statistic_evidence_kinds_are_rejected() {
    // 수락 기준: 출처가 확정된 공공 통계만 — statute·regulator_notice·terms_fact·
    // editorial 출처는 이 경로에 올 수 없다.
    for kind in ["statute", "regulator_notice", "terms_fact", "editorial"] {
        let e = load_err(json!({
            "versions": [{"sources": [{"ref": RAW, "evidence_kind": kind}]}]
        }));
        assert!(
            matches!(e, DefaultsError::SourceNotPublicStatistic { .. }),
            "evidence_kind {kind} must be refused"
        );
    }
}

#[test]
fn non_raw_refs_are_rejected() {
    // 산출물 명세: 출처는 RawAsset 해시 — clause:/obs: 참조는 거부된다.
    let e = load_err(json!({
        "versions": [{"sources": [{"ref": OBS, "evidence_kind": "public_statistic"}]}]
    }));
    assert!(matches!(e, DefaultsError::SourceNotRawAsset { .. }));
}

#[test]
fn malformed_source_ref_is_rejected() {
    let e = load_err(json!({
        "versions": [{"sources": [{"ref": "raw:sha256:nothex", "evidence_kind": "public_statistic"}]}]
    }));
    assert!(matches!(
        e,
        DefaultsError::Criteria(CriteriaError::BadSourceRef { .. }) | DefaultsError::Shape(_)
    ));
}

#[test]
fn applied_true_is_rejected() {
    // 후보는 applied=false로만 적재된다 — 적용 승인은 criteria_application(T-KN-14)의 몫.
    let e = load_err(json!({"candidate": {"applied": true}}));
    assert!(matches!(e, DefaultsError::AppliedTrue { .. }));
}

#[test]
fn scope_and_update_cycle_are_required() {
    // 적용 대상·갱신 주기 없는 후보는 없다.
    let e = load_err(json!({"candidate": {"scope": {"situations": [], "subjects": ["전체"]}}}));
    assert!(matches!(
        e,
        DefaultsError::Criteria(CriteriaError::Scope { .. })
    ));
    let e = load_err(json!({"candidate": {"scope": {"situations": ["x"], "subjects": []}}}));
    assert!(matches!(
        e,
        DefaultsError::Criteria(CriteriaError::Scope { .. })
    ));
    let e = load_err(json!({"candidate": {"update_cycle": null}}));
    assert!(matches!(e, DefaultsError::Shape(_)));
}

#[test]
fn unknown_keys_are_rejected() {
    let e = load_err(json!({"candidate": {"surprise": 1}}));
    assert!(matches!(e, DefaultsError::Shape(_)));
    // value 안의 알 수 없는 키도 거부된다(태그 enum이면 serde가 조용히 무시한다).
    let e = load_err(json!({"versions": [{"value": {"extra_key": 1}}]}));
    assert!(matches!(e, DefaultsError::Shape(_)));
}

#[test]
fn value_fields_must_match_their_kind() {
    // kind가 쓰지 않는 필드·빠진 필수 필드는 거부된다. value는 통째로 바꿔 적는다
    // (merge가 배열을 요소 단위로 덮어 기본값을 남기면 의도와 다른 값이 된다).
    for value in [
        json!({"kind": "rate", "summary": "x"}), // rate_bp 빠짐
        json!({"kind": "rate", "rate_bp": 2000, "amount_krw": 5, "summary": "x"}), // 다른 kind의 필드
        json!({"kind": "structure", "items": [{"label": "항목"}], "summary": "x"}), // 수치 없는 항목
        json!({"kind": "count", "count": 3, "summary": "x"}),                       // unit 빠짐
    ] {
        let mut j = candidate_json(json!({}));
        j["versions"][0]["value"] = value;
        let mut s = DefaultsStore::new();
        let e = load_str(&j.to_string(), &mut s).unwrap_err();
        assert!(
            matches!(e, DefaultsError::BadValue { .. }),
            "value {e:?} should be BadValue"
        );
    }
}

#[test]
fn private_id_prefixes_are_rejected() {
    // K8 — 공개 기준·기본값 자료에 개인 영역 식별자 접두어가 올 수 없다.
    let e = load_err(json!({"candidate": {"label": "person:x 기준"}}));
    assert!(matches!(
        e,
        DefaultsError::Criteria(CriteriaError::PrivateId { .. })
    ));
}

// ---------------------------------------------------------------- versioning

#[test]
fn correction_chain_loads_and_tips() {
    let mut j = candidate_json(json!({}));
    j["versions"].as_array_mut().unwrap().push(json!({
        "version": 2,
        "valid_from": "2026-07-01",
        "value": {"kind": "rate", "rate_bp": 2000, "summary": "입원 본인부담률"},
        "sources": [{"ref": RAW, "evidence_kind": "public_statistic"}],
        "rationale": "통계표 갱신",
        "recorded_at": "2026-10-20T01:00:00Z",
        "supersedes": "def:nhis_copay@1",
        "correction_reason": "source_changed",
        "origin": "fixture"
    }));
    let mut s = DefaultsStore::new();
    load_str(&j.to_string(), &mut s).unwrap();
    assert_eq!(s.tip("def:nhis_copay").unwrap().version, 2);
    // v1은 지워지지 않는다.
    assert!(s.version("def:nhis_copay@1").is_some());
}

#[test]
fn version_two_without_supersedes_is_rejected() {
    let mut j = candidate_json(json!({}));
    let mut v2 = candidate_json(json!({}))["versions"][0].clone();
    v2["version"] = json!(2);
    j["versions"].as_array_mut().unwrap().push(v2);
    let mut s = DefaultsStore::new();
    let e = load_str(&j.to_string(), &mut s).unwrap_err();
    assert!(matches!(
        e,
        DefaultsError::Criteria(CriteriaError::Supersedes { .. })
    ));
}

// ---------------------------------------------------------------- service gate

#[test]
fn candidates_never_reach_service_reads() {
    // 과제 메모: 후보는 applied=false로 적재되고 표시되지 않는다 — 서비스 모드가
    // 읽을 수 있는 유일한 목록(for_service)은 적용 승인이 없는 한 항상 비어 있다.
    let s = load_ok(json!({}));
    assert!(s.candidates().count() > 0, "후보는 적재된다");
    assert_eq!(
        s.for_service().count(),
        0,
        "적용 승인(criteria_application, T-KN-14·D-08) 없이 어떤 후보도 서비스에 나가지 않는다"
    );
}

#[test]
fn display_is_reference_statistic_never_fact() {
    // 수락 기준: 기본값은 결과에 "참고 통계"로 표시되고 사실로 표시되지 않는다 —
    // DisplayKind에는 fact 변형이 아예 없고 라벨은 고정이다.
    let s = load_ok(json!({}));
    let r = s.resolve("def:nhis_copay@1").unwrap();
    let d = display(r);
    assert_eq!(d.kind, DisplayKind::ReferenceStatistic);
    assert_eq!(d.kind.label(), "참고 통계");
    assert_eq!(d.summary, "요양기관 종별 본인부담률");
    assert_eq!(d.sources.len(), 1);
}

#[test]
fn user_assumption_is_never_overwritten() {
    // 수락 기준: 사용자 가정이 있으면 기본값을 덮지 않는다.
    let s = load_ok(json!({}));
    let tip = s.tip("def:nhis_copay");
    // 가정이 있으면 후보가 있어도 가정이 돌아온다.
    match effective(Some(9_000_000u64), tip) {
        Some(EffectiveDefault::UserAssumption(a)) => assert_eq!(a, 9_000_000),
        _ => panic!("assumption must win over any candidate"),
    }
    // 가정이 없고 후보만 있으면 후보가 참고 통계로 돌아온다.
    match effective::<u64>(None, tip) {
        Some(EffectiveDefault::Candidate(v)) => assert_eq!(v.id, "def:nhis_copay@1"),
        _ => panic!("candidate should back the slot when no assumption exists"),
    }
    // 둘 다 없으면 0·평균으로 채우지 않고 None(보류)이다(D-08).
    assert!(effective::<u64>(None, None).is_none());
}

// ---------------------------------------------------------------- shipped data

#[test]
fn shipped_defaults_dir_loads_clean() {
    // data/criteria/defaults/candidates/의 서비스 후보는 전부 적재·검증을 통과해야
    // 한다. 후보가 0건인 것도 정상 상태다(확정된 공공 통계 원본이 아직 없다).
    let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../data/criteria/defaults/candidates");
    let s = load_dir(&dir).unwrap();
    for v in s.versions() {
        assert!(!v.sources.is_empty(), "출처 없는 기본값이 없다");
        for src in &v.sources {
            assert_eq!(
                src.evidence_kind,
                CriterionSourceKind::PublicStatistic,
                "후보 출처는 공공 통계뿐이다"
            );
            assert!(
                src.ref_.starts_with("raw:sha256:"),
                "후보 출처는 RawAsset 해시 참조다"
            );
        }
        assert_eq!(
            v.origin,
            AssertionOrigin::Pipeline,
            "서비스 후보는 pipeline 자료만 — 시험용은 origin=fixture로 tests 안에 둔다"
        );
    }
    for c in s.candidates() {
        assert!(!c.applied, "후보는 applied=false로만 적재된다");
    }
    assert_eq!(s.for_service().count(), 0);
}

#[test]
fn criterion_sources_type_is_shared() {
    // 후보 출처는 기준 출처와 같은 근거 문법을 쓴다(같은 CriterionSource 타입).
    let s = load_ok(json!({}));
    let v = s.version("def:nhis_copay@1").unwrap();
    let src: &CriterionSource = &v.sources[0];
    assert!(src.ref_.starts_with("raw:sha256:"));
}
