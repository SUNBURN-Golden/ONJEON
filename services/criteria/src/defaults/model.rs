//! Data model for default candidates (`data/criteria/defaults/candidates/<slug>.json`).
//!
//! A candidate file is `{candidate, versions[]}` — the same shape as a criterion
//! file, plus `update_cycle` and `applied` on the candidate and `value` on each
//! version. Reuses `CriterionScope`, `CriterionSource`, `CorrectionReason` and
//! `AssertionOrigin` so the two record families follow one evidence grammar.

use crate::model::{CriterionScope, CriterionSource};
use onjeon_contracts::{AssertionOrigin, CorrectionReason};
use serde::{Deserialize, Serialize};

/// 후보의 종류 — 기본 "필요액" 수치 후보와 참고 통계 기본값 후보를 구분한다.
/// 둘 다 서비스 표시는 "참고 통계"이며 사실로 표시되지 않는다(수락 기준).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DefaultKind {
    /// 기본 필요액 후보(예: 상황별 참고 필요 금액의 통계적 근거).
    NeededAmount,
    /// 참고 통계 기본값 후보(예: 건강보험 본인부담 구조).
    ReferenceStat,
}

/// 갱신 주기 — 후보마다 필수(과제 산출물: "적용 대상·갱신 주기 포함"). `note`에
/// 주기의 근거(원본 갱신 주기·다음 확인 시점 등)를 자유 서술로 둔다.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct UpdateCycle {
    pub kind: UpdateCycleKind,
    #[serde(default)]
    pub note: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum UpdateCycleKind {
    Daily,
    Weekly,
    Monthly,
    Quarterly,
    Semiannual,
    Annual,
    /// 원본 통계의 발표 주기를 따른다(주기가 법령·기관 일정으로 정해지지 않은 경우).
    OnSourceRelease,
    Irregular,
}

/// 기본값 후보 항목. 식별자 `def:<slug>`. `applied`는 `false`만 적재된다 — `true`는
/// 서비스 적용 승인(`criteria_application`, T-KN-14·D-08)이 있어야 하는 상태다.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DefaultCandidate {
    /// `def:<slug>`
    pub id: String,
    pub kind: DefaultKind,
    pub label: String,
    /// 적용 대상(§1.5 적용 범위와 같은 모양 — 상황·대상 각 1개 이상).
    pub scope: CriterionScope,
    pub update_cycle: UpdateCycle,
    /// 후보는 `false`로만 적재된다(과제 메모: applied=false로 적재·표시 안 됨).
    pub applied: bool,
    /// RFC 3339 시각.
    pub recorded_at: String,
}

/// 금액 기간 — `monetary_amount` 값이 어느 기간·단위의 수치인지.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AmountPeriod {
    Day,
    Month,
    Year,
    /// 1회·건당 기준(기간이 아닌 단위).
    Case,
}

/// 후보 판이 담는 통계 값의 종류.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ValueKind {
    /// 정수 원 금액(I4 — 반올림 없이 원문 수치 그대로).
    MonetaryAmount,
    /// 비율. 소수 표현 재현성 문제를 피하려고 베이시스 포인트(1bp = 0.01%)로 둔다.
    Rate,
    /// 횟수·인원·일수 같은 정수 수치.
    Count,
    /// 구간·구조 표(예: 본인부담률 구간). 각 항목은 수치 하나 이상을 가진다.
    Structure,
}

/// 후보 판이 담는 통계 값. `kind`가 쓰는 필드만 채운다 — 나머지는 비워 두고,
/// `kind`에 없는 키·필드는 적재 단계에서 거부한다(알 수 없는 키는 거부된다는
/// 규칙이 `deny_unknown_fields`로 동작하려고 태그 enum 대신 평평한 구조다).
/// `summary`는 화면 "참고 통계" 줄에 실리는 한 줄 설명이다.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DefaultValue {
    pub kind: ValueKind,
    /// `monetary_amount`: 금액(정수 원).
    #[serde(default)]
    pub amount_krw: Option<u64>,
    /// `monetary_amount`: 어느 기간·단위의 금액인지.
    #[serde(default)]
    pub period: Option<AmountPeriod>,
    /// `rate`: 베이시스 포인트.
    #[serde(default)]
    pub rate_bp: Option<u64>,
    /// `count`: 수치.
    #[serde(default)]
    pub count: Option<u64>,
    /// `count`: 단위(회·명·일 등).
    #[serde(default)]
    pub unit: Option<String>,
    /// `structure`: 구간·항목 표.
    #[serde(default)]
    pub items: Option<Vec<StructureItem>>,
    /// "참고 통계"로 표시되는 한 줄 설명.
    pub summary: String,
}

impl DefaultValue {
    pub fn summary(&self) -> &str {
        &self.summary
    }
}

/// `structure` 값의 한 줄 — 구간 라벨과 수치(금액·비율·횟수 중 하나 이상).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StructureItem {
    pub label: String,
    #[serde(default)]
    pub amount_krw: Option<u64>,
    #[serde(default)]
    pub rate_bp: Option<u64>,
    #[serde(default)]
    pub count: Option<u64>,
    #[serde(default)]
    pub unit: Option<String>,
    #[serde(default)]
    pub note: Option<String>,
}

/// 후보의 판. 기준 판과 같은 규칙: 고치지 않고 정정은 새 판 + `supersedes`
/// (바로 이전 판)이다. `value`와 `sources`가 판마다 달라진다.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CandidateVersion {
    /// `def:<slug>@<version>` — `candidate_id`와 `version`에서 정해지는 파생 식별자.
    pub id: String,
    pub candidate_id: String,
    /// 1부터. 정정할 때마다 1씩 늘고 직전 판만 대체한다(선형 사슬).
    pub version: u32,
    /// `YYYY-MM-DD`.
    pub valid_from: String,
    pub valid_to: Option<String>,
    /// 이 판의 통계 값.
    pub value: DefaultValue,
    /// 1개 이상. 각 `ref`는 `raw:sha256:`이고 `evidence_kind`는 `public_statistic`이어야 한다.
    pub sources: Vec<CriterionSource>,
    /// 이 판을 두는 이유.
    pub rationale: String,
    /// RFC 3339 시각.
    pub recorded_at: String,
    /// 바로 이전 판(`<candidate_id>@<version-1>`). `version=1`이면 없다.
    pub supersedes: Option<String>,
    /// `supersedes`가 있을 때만 필수(쌍으로만 온다).
    pub correction_reason: Option<CorrectionReason>,
    pub origin: AssertionOrigin,
}

impl CandidateVersion {
    pub fn from_file(candidate_id: &str, f: CandidateVersionFile) -> CandidateVersion {
        CandidateVersion {
            id: version_id(candidate_id, f.version),
            candidate_id: candidate_id.to_string(),
            version: f.version,
            valid_from: f.valid_from,
            valid_to: f.valid_to,
            value: f.value,
            sources: f.sources,
            rationale: f.rationale,
            recorded_at: f.recorded_at,
            supersedes: f.supersedes,
            correction_reason: f.correction_reason,
            origin: f.origin,
        }
    }
}

/// `def:<slug>@<n>`
pub fn version_id(candidate_id: &str, version: u32) -> String {
    format!("{candidate_id}@{version}")
}

/// One candidate data file: the item plus its versions
/// (`data/criteria/defaults/candidates/<slug>.json`).
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CandidateFile {
    pub candidate: DefaultCandidate,
    pub versions: Vec<CandidateVersionFile>,
}

/// A version as written on disk — `id`/`candidate_id` are derived, never written.
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CandidateVersionFile {
    pub version: u32,
    pub valid_from: String,
    #[serde(default)]
    pub valid_to: Option<String>,
    pub value: DefaultValue,
    /// At least one `raw:` + `public_statistic` source is required at insertion.
    #[serde(default)]
    pub sources: Vec<CriterionSource>,
    pub rationale: String,
    pub recorded_at: String,
    /// Must be `<candidate_id>@<version-1>` when present.
    #[serde(default)]
    pub supersedes: Option<String>,
    #[serde(default)]
    pub correction_reason: Option<CorrectionReason>,
    pub origin: AssertionOrigin,
}
