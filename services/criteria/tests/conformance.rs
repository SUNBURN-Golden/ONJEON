//! Conformance with the resources this task consumes: `infra/db/**` (the criteria
//! schema T-CT-05 built), `packages/schemas/vocabulary.json` (the enum source), and
//! `data/criteria/**` (this task's produced path).

mod common;

use common::*;
use onjeon_contracts::{AssertionOrigin, CorrectionReason, CriterionSourceKind};
use onjeon_criteria::*;
use serde_json::Value;
use std::path::{Path, PathBuf};

fn repo(rel: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .join(rel)
}

fn json_at(rel: &str) -> Value {
    let text = std::fs::read_to_string(repo(rel)).unwrap_or_else(|e| panic!("read {rel}: {e}"));
    serde_json::from_str(&text).unwrap_or_else(|e| panic!("parse {rel}: {e}"))
}

fn axis_codes(vocab: &Value, axis: &str) -> Vec<String> {
    vocab["axes"]
        .as_array()
        .unwrap()
        .iter()
        .find(|a| a["id"] == axis)
        .unwrap_or_else(|| panic!("axis {axis} missing from vocabulary"))["values"]
        .as_array()
        .unwrap()
        .iter()
        .map(|x| x["code"].as_str().unwrap().to_string())
        .collect()
}

/// 인수 기준 2: 모든 기준 판에 출처·근거 종류·적용 범위가 있다 — 저장소에 들어온 판은
/// 출처 1개 이상·어휘 근거 종류·비어 있지 않은 적용 범위를 항상 가진다(삽입 시 강제).
#[test]
fn every_version_carries_source_kind_and_scope() {
    let s = {
        let dir = repo("services/criteria/tests/fixtures/criteria");
        load_dir(&dir).unwrap()
    };
    assert!(
        s.criteria().count() > 0,
        "fixture store should not be empty"
    );
    for c in s.criteria() {
        assert!(!c.scope.situations.is_empty() && !c.scope.subjects.is_empty());
        assert!(CriterionKind::ALL.contains(&c.kind));
    }
    for v in s.versions() {
        assert!(!v.sources.is_empty(), "{} has no source", v.id);
        assert!(!v.rationale.trim().is_empty());
        for src in &v.sources {
            assert!(CriterionSourceKind::ALL.contains(&src.evidence_kind));
        }
    }
}

/// `kind`의 네 값이 DB CHECK(`infra/db/criteria/01_criteria.sql`)와 계약(§1.5)에 맞는다.
#[test]
fn criterion_kind_matches_db_check() {
    let sql = std::fs::read_to_string(repo("infra/db/criteria/01_criteria.sql")).unwrap();
    for k in CriterionKind::ALL {
        assert!(
            sql.contains(&format!("'{}'", k.as_str())),
            "kind {} not in DB CHECK",
            k.as_str()
        );
    }
    // 파일 스키마의 kind enum도 같은 네 값이어야 한다.
    let schema = json_at("data/criteria/criterion-file.schema.json");
    let kinds = schema["$defs"]["criterion"]["properties"]["kind"]["enum"]
        .as_array()
        .unwrap()
        .iter()
        .map(|x| x.as_str().unwrap().to_string())
        .collect::<Vec<_>>();
    let want: Vec<String> = CriterionKind::ALL
        .iter()
        .map(|k| k.as_str().into())
        .collect();
    assert_eq!(kinds, want);
}

/// 출처 근거 종류·정정 사유·origin이 어휘 정본과 같고, 파일 스키마도 그 값을 쓴다.
#[test]
fn enums_match_vocabulary_and_schema() {
    let vocab = json_at("packages/schemas/vocabulary.json");
    let schema = json_at("data/criteria/criterion-file.schema.json");

    let code = |axis: &str, vals: &[String]| {
        let got = axis_codes(&vocab, axis);
        assert_eq!(&got, vals, "axis {axis}");
    };
    code(
        "criterion_source_kind",
        &CriterionSourceKind::ALL
            .iter()
            .map(|v| v.as_str().into())
            .collect::<Vec<String>>(),
    );
    code(
        "assertion_origin",
        &AssertionOrigin::ALL
            .iter()
            .map(|v| v.as_str().into())
            .collect::<Vec<String>>(),
    );
    code(
        "correction_reason",
        &CorrectionReason::ALL
            .iter()
            .map(|v| v.as_str().into())
            .collect::<Vec<String>>(),
    );

    let schema_enum = |path: &[&str]| -> Vec<String> {
        let mut v = &schema;
        for p in path {
            v = &v[*p];
        }
        v.as_array()
            .unwrap()
            .iter()
            .map(|x| x.as_str().unwrap().to_string())
            .collect()
    };
    assert_eq!(
        schema_enum(&["$defs", "source", "properties", "evidence_kind", "enum"]),
        CriterionSourceKind::ALL
            .iter()
            .map(|v| v.as_str().into())
            .collect::<Vec<String>>()
    );
    assert_eq!(
        schema_enum(&["$defs", "version", "properties", "origin", "enum"]),
        AssertionOrigin::ALL
            .iter()
            .map(|v| v.as_str().into())
            .collect::<Vec<String>>()
    );
    assert_eq!(
        schema_enum(&[
            "$defs",
            "version",
            "properties",
            "correction_reason",
            "enum"
        ]),
        CorrectionReason::ALL
            .iter()
            .map(|v| v.as_str().into())
            .collect::<Vec<String>>()
    );
}

/// 식별자·출처 형식이 DB와 같은 문법이다(DB CHECK와 evidence_ref 문법).
#[test]
fn ids_and_refs_match_db_grammar() {
    let sql = std::fs::read_to_string(repo("infra/db/criteria/01_criteria.sql")).unwrap();
    // DB: criterion.id ~ '^crit:[a-z0-9_-]+$', version id ~ '^crit:[a-z0-9_-]+@[0-9]+$'
    for (id, ok) in [
        ("crit:a", true),
        ("crit:a-b_c9", true),
        ("crit:A", false),
        ("a", false),
        ("crit:a@1", false),
    ] {
        assert_eq!(CriterionStore::is_criterion_id(id), ok, "{id}");
    }
    assert!(sql.contains("^crit:[a-z0-9_-]+$"));
    assert!(sql.contains("^crit:[a-z0-9_-]+@[0-9]+$"));

    // 출처 ref는 DB가 허용하는 세 접두어(raw:/clause:/obs:)의 evidence_ref 문법이다.
    for ok in [RAW_REF, OBS_REF, CLAUSE_REF] {
        let parsed = onjeon_contracts::evidence_ref::validate(ok).unwrap();
        use onjeon_contracts::evidence_ref::RefKind::*;
        assert!(matches!(parsed.kind(), Raw | Clause | Observation));
    }
}

/// 이 과제의 산출 경로 `data/criteria/`는 파일 계약을 가진다. 서비스 기준은 아직 없고
/// (기준 작성 절차·D-08 적용 승인 이전) 있다면 전부 적재 가능해야 한다.
/// `data/criteria/defaults/`는 T-KN-13의 경로이므로 여기서 만들지도 읽지도 않는다.
#[test]
fn shipped_criteria_dir_loads_clean() {
    let dir = repo("data/criteria/criteria");
    let s = load_dir(&dir).unwrap();
    for v in s.versions() {
        assert!(!v.sources.is_empty());
        assert_eq!(
            v.origin,
            AssertionOrigin::Pipeline,
            "service data is pipeline-only; test material stays in tests/"
        );
    }
    // 릴리스 파일이 있으면 무결성 검사를 통과해야 한다(지금은 없음).
    let rel_dir = repo("data/criteria/releases");
    if rel_dir.is_dir() {
        for e in std::fs::read_dir(&rel_dir).unwrap() {
            let p = e.unwrap().path();
            if p.extension().is_some_and(|x| x == "json") {
                let rel = load_release_file(&p).unwrap();
                verify(&s, &rel).unwrap();
            }
        }
    }
    assert!(
        !repo("data/criteria/defaults").exists(),
        "기본 필요액 후보는 T-KN-13의 경로 — 이 과제에서 생성하지 않는다"
    );
}

/// DB의 불변식을 이 크레이트도 강제한다: 판은 고치지 않고 정정은 새 팀다
/// (UPDATE/DELETE가 없다는 것은 API 표면에 그런 함수가 없음으로 증명한다 — 아래는
/// 데이터 수준의 동등 보장: 두 판이 공존하고 사슬이 이어진다).
#[test]
fn append_only_semantics_hold() {
    let s = store_with(2);
    let v1 = s.version("crit:a@1").unwrap();
    let v2 = s.version("crit:a@2").unwrap();
    assert_eq!(v2.supersedes.as_deref(), Some(v1.id.as_str()));
    assert_eq!(v1.version + 1, v2.version);
}
