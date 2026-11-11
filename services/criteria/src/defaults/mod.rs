//! 기본 필요액·참고 통계 기본값 후보(T-KN-13, 02_구현계약 §1.5 "기본값" 행, O05, 통합안 D-08).
//!
//! 경로 정책 상태: 이 과제의 허용 경로는 `data/criteria/defaults/**`와
//! `services/criteria/src/defaults/**`뿐이라 이 모듈을 켜는 `pub mod defaults;`
//! 한 줄(`src/lib.rs`)은 허용 밖이다. 제품 크레이트에서는 아직 컴파일되지 않는다.
//! `verification/Cargo.toml`은 원본 소스를 컴파일하는 시험 전용 진입점이다.
//! 배선과 `data/criteria/defaults/` 생성(conformance의 비존재 단정 갱신 포함)은
//! 여전히 미완료다. 자세한 것은 이 디렉터리의 `README.md` "현재 상태" 절.
//!
//! 이 모듈은 기본값 **후보**만 적재한다. 판 하나는 출처가 확정된 공공 통계에만 근거한다:
//! `sources`는 1개 이상이고 각 `ref`는 `raw:sha256:<64>` RawAsset 해시이며
//! `evidence_kind`는 `public_statistic`뿐이다. 모든 후보는 적용 대상(`scope`)과
//! 갱신 주기(`update_cycle`)를 가진다.
//!
//! 후보는 `applied=false`로만 저장된다. 서비스 적용 승인 기록(`criteria_application`,
//! T-KN-14, D-08)이 없는 한 어떤 후보도 사용자에게 보이지 않는다 —
//! [`DefaultsStore::for_service`]는 항상 비어 있고, 후보를 `applied`로 바꾸는
//! 경로는 이 모듈에 없다.
//!
//! 사용자에게 보이게 되는 경우에도 기본값은 "사실"이 아니라 "참고 통계"로 표시된다
//! ([`service::display`]), 사용자 가정이 있으면 기본값이 덮지 않는다
//! ([`service::effective`]), 가정도 후보도 없으면 0이나 평균으로 채우지 않는다
//! (`None` — 결과는 보류로 간다, D-08).

mod error;
mod load;
mod model;
mod service;
mod store;

#[cfg(test)]
mod tests;

pub use error::{DefaultsError, Result};
pub use load::{load_dir, load_file, load_str};
pub use model::{
    AmountPeriod, CandidateFile, CandidateVersion, CandidateVersionFile, DefaultCandidate,
    DefaultKind, DefaultValue, StructureItem, UpdateCycle, UpdateCycleKind, ValueKind,
};
pub use service::{
    display, effective, CandidateDisplay, DisplayKind, EffectiveDefault, REFERENCE_STAT_LABEL,
};
pub use store::{CandidateVersionRef, DefaultsStore};
