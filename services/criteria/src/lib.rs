//! 판단 기준 관리(영역 C, T-KN-12, 02_구현계약 §1.5).
//!
//! 약관 지식("무엇을 지급하나")과 다른 종류의 판단("무엇을 우선 살펴볼 만한가")을 관리한다.
//! 둘이 같은 사실처럼 보이지 않도록 저장·판·근거를 나눈다.
//!
//! - [`model`]: `Criterion`(기준 항목), `CriterionVersion`(기준의 판: 출처·근거 종류·적용 범위·정정 사슬),
//!   `CriteriaRelease`(기준 판 목록 + 내용 해시, 지식 릴리스 `rel:`와 별도의 `crel:` ID).
//! - [`store`]: 판 검증과 보관. 기준은 고치지 않는다 — 정정은 새 판 + `supersedes`다(추가만).
//! - [`load`]: `data/criteria/criteria/*.json` 파일 계약의 적재기.
//! - [`release`]: 릴리스 고정(`freeze`)과 무결성 검사(`verify`, K15·ONJ-KN-S-052 유사).
//! - [`changes`]: 두 릴리스(또는 릴리스와 현재 판)의 변경 목록 — `conclusion_dependency.deps.criteria`에서
//!   영향받는 결론을 찾는 입력(§1.5 정정 영향).
//!
//! 이 크레이트가 하지 않는 것:
//! - 기본 필요액·참고 통계 기본값. 후보 적재는 T-KN-13(`data/criteria/defaults/`),
//!   서비스 적용 승인 관문(`criteria_application`, D-08)은 T-KN-14다. 기준 판에 `default*`
//!   키가 있으면 적재 단계에서 거부한다([`CriteriaError::DefaultOutsideGate`]).
//! - 필요성 판단 결과(`need_result`, T-AP-09)와 사용자 가정(`user_assumption`, 개인 영역).
//! - 데이터베이스. `infra/db/criteria/`의 스키마·제약과 같은 규칙을 파일 계약에도 강제하지만,
//!   실제 적재는 후속 적재기 과제의 몫이다. 이 크레이트의 검사가 DB보다 좁을 뿐 넓지는 않다.

pub mod canon;
pub mod changes;
pub mod error;
pub mod k8;
pub mod load;
pub mod model;
pub mod release;
pub mod store;

pub use changes::{diff_releases, diff_to_tips, ChangeKind, ChangeList, CriterionChange};
pub use error::{CriteriaError, IntegrityFinding, Result};
pub use load::{load_dir, load_file, load_release_file, load_str};
pub use model::{
    Criterion, CriterionFile, CriterionKind, CriterionScope, CriterionSource, CriterionVersion,
    ReleaseMembers,
};
pub use release::{freeze, is_release_id, verify, CriteriaRelease};
pub use store::{CriterionStore, VersionRef};
