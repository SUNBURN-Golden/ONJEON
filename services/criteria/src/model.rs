//! Data model: criterion items, their versions (판), sources and releases.
//!
//! Mirrors `infra/db/criteria/01_criteria.sql` and 02_구현계약 §1.5. The canonical
//! `CriterionVersion` carries `id`/`criterion_id` like the DB row; the on-disk
//! `VersionFile` nests inside its criterion file and derives both.

use onjeon_contracts::{AssertionOrigin, CorrectionReason, CriterionSourceKind};
use serde::{Deserialize, Serialize};

/// The four criterion kinds of §1.5. Not yet a vocabulary axis — the same four values
/// sit in the DB `kind` CHECK and the conformance test keeps all three in step.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CriterionKind {
    /// 무엇을 우선 살펴볼 만한가(우선 고려 규칙).
    PriorityRule,
    /// 참고 통계(공공 통계에 근거하는 참고값).
    ReferenceStat,
    /// 기준이 언제·누구에게 적용되는가.
    ApplicabilityRule,
    /// 사용자에게 무엇을 물어볼 것인가.
    QuestionRule,
}

impl CriterionKind {
    pub const ALL: &'static [CriterionKind] = &[
        CriterionKind::PriorityRule,
        CriterionKind::ReferenceStat,
        CriterionKind::ApplicabilityRule,
        CriterionKind::QuestionRule,
    ];

    pub fn as_str(&self) -> &'static str {
        match self {
            CriterionKind::PriorityRule => "priority_rule",
            CriterionKind::ReferenceStat => "reference_stat",
            CriterionKind::ApplicabilityRule => "applicability_rule",
            CriterionKind::QuestionRule => "question_rule",
        }
    }
}

/// 적용 범위: 어떤 상황·어떤 대상에게 이 기준이 적용되는가. 범위 밖이면 평가에 쓰지 않는다(§1.5).
/// 두 목록 모두 한 항목 이상이어야 한다(적용 범위 없는 기준은 저장되지 않는다).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CriterionScope {
    /// 적용 상황(예: 소득 중단, 부양가족 발생).
    pub situations: Vec<String>,
    /// 적용 대상(예: 연령대, 계약 유무).
    pub subjects: Vec<String>,
}

/// 판단 기준 항목. 식별자 `crit:<slug>`. 항목 자체는 판을 갖지 않고 판의 묶음이다.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Criterion {
    /// `crit:<slug>`
    pub id: String,
    pub kind: CriterionKind,
    pub label: String,
    pub scope: CriterionScope,
    /// RFC 3339 시각.
    pub recorded_at: String,
}

/// 판 하나의 출처. `ref`는 `raw:`·`clause:`·`obs:` 근거 참조이고 `evidence_kind`로
/// 공공 통계·법령·감독 고시·약관 사실·편집 판단을 구분한다(§1.5). `editorial`은
/// "참고 통계"가 아니라 "온전의 판단"으로 표시되는 근거다.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CriterionSource {
    #[serde(rename = "ref")]
    pub ref_: String,
    pub evidence_kind: CriterionSourceKind,
}

/// 기준의 판. 기준은 고치지 않는다 — 정정은 새 판 + `supersedes`다.
/// 출처가 없는 판은 저장되지 않고 기준 릴리스에도 들어가지 못한다.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CriterionVersion {
    /// `crit:<slug>@<version>` — `criterion_id`와 `version`에서 정해지는 파생 식별자.
    pub id: String,
    pub criterion_id: String,
    /// 1부터 시작. 정정할 때마다 1씩 늘고 직전 판만 대체한다(선형 사슬).
    pub version: u32,
    /// `YYYY-MM-DD`.
    pub valid_from: String,
    pub valid_to: Option<String>,
    /// 1개 이상.
    pub sources: Vec<CriterionSource>,
    /// 이 판을 두는 이유.
    pub rationale: String,
    /// RFC 3339 시각.
    pub recorded_at: String,
    /// 바로 이전 판(`<criterion_id>@<version-1>`). `version=1`이면 없다.
    pub supersedes: Option<String>,
    /// `supersedes`가 있을 때만 필수(쌍으로만 온다).
    pub correction_reason: Option<CorrectionReason>,
    pub origin: AssertionOrigin,
}

impl CriterionVersion {
    /// Build the canonical version row from a stored criterion id and a file-level version.
    pub fn from_file(criterion_id: &str, f: VersionFile) -> CriterionVersion {
        CriterionVersion {
            id: version_id(criterion_id, f.version),
            criterion_id: criterion_id.to_string(),
            version: f.version,
            valid_from: f.valid_from,
            valid_to: f.valid_to,
            sources: f.sources,
            rationale: f.rationale,
            recorded_at: f.recorded_at,
            supersedes: f.supersedes,
            correction_reason: f.correction_reason,
            origin: f.origin,
        }
    }
}

/// `<criterion_id>@<version>`
pub fn version_id(criterion_id: &str, version: u32) -> String {
    format!("{criterion_id}@{version}")
}

/// One criterion data file: the item plus its versions (`data/criteria/criteria/<slug>.json`).
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CriterionFile {
    pub criterion: Criterion,
    pub versions: Vec<VersionFile>,
}

/// A version as written on disk — `id`/`criterion_id` are derived, never written.
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct VersionFile {
    pub version: u32,
    pub valid_from: String,
    #[serde(default)]
    pub valid_to: Option<String>,
    /// At least one source is required; an empty list fails at insertion.
    #[serde(default)]
    pub sources: Vec<CriterionSource>,
    pub rationale: String,
    pub recorded_at: String,
    /// Written explicitly so the correction chain is visible in data.
    /// Must be `<criterion_id>@<version-1>` when present.
    #[serde(default)]
    pub supersedes: Option<String>,
    #[serde(default)]
    pub correction_reason: Option<CorrectionReason>,
    pub origin: AssertionOrigin,
}

/// `criteria_release.members` — the frozen list of criterion-version ids (`data/criteria/releases/`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ReleaseMembers {
    pub criterion_versions: Vec<String>,
}
