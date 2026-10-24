//! Denominator enumeration adapters (T-DT-04 — DATA_PIPELINE_CONTRACT §1·§2,
//! ADR-0018 §3·§4, source-survey H1~H14, Masterplan §23–24).
//!
//! The denominator is tracked, not assumed: [`registry`] loads the institution axis from
//! `data/registry/*.csv` (ADR-0018 scope rules — 공제·우체국 구분, seed 제외, 사유 보존),
//! [`institution`] supplies the per-institution adapters (협회·보험사별) and their
//! `AdapterManifest`s, and [`enumerate`] walks each list plan writing page records and
//! termination evidence into a [`manifest::DiscoveryManifest`].
//!
//! Enforced rules:
//!
//! - **robots 확인 불가 호스트는 보류**: an unverifiable robots.txt defers the host for the
//!   rest of the UTC day; its scopes stay `hold`, never fetched (same table as
//!   `tools/crawler/robots.py`).
//! - **200 로그인 HTML은 성공이 아니다**: a login form at a list URL records a `blocked`
//!   range (`login_page`), never an item count.
//! - **종료 증거 없이 성공 없음**: a repeated last page, a stall before the advertised
//!   total, or the page cap each produce an unexplored range — not a completed list.
//! - **미확보 사유는 확보가 아니다** (09 P02): the progress table counts a document as
//!   acquired only when 원본 보존 + 구획 추출 + 판 연결(accepted realizes) all exist.
//! - **공제는 분모 밖**: cooperative and policy-insurer rows are excluded *with* their
//!   reasons, never silently dropped.

pub mod enumerate;
pub mod fetch;
pub mod institution;
pub mod listpage;
pub mod manifest;
pub mod progress;
pub mod registry;
pub mod robots;

#[cfg(test)]
mod regression;

pub use enumerate::{
    exploration_state_of, unenumerated_manifest, Enumerator, ListPlan, Pagination, RunMeta,
    LIST_PAGE_MAX_BYTES,
};
pub use fetch::{split_url, Fetch, FetchError, FetchResponse};
pub use institution::{
    company_doc_roles, klia, knia, AdapterManifest, AssociationAdapter, AssociationPlan,
    DiscoveryAdapter, InsurerAdapter,
};
pub use listpage::{classify, looks_like_login, parse_page, ListParser, PageClass, ParsedPage};
pub use manifest::{
    manifest_key, record_manifest, CandidateDocument, DiscoveryManifest, GapRecord, ManifestResult,
    PageRecord, ProductCandidate, RequestConditions, ScopeDesc, Termination, DENOMINATOR_DOC_ROLES,
};
pub use progress::{
    coverage, AcquisitionEvidence, DenominatorItem, ExplorationState, InstitutionProgress,
    ProgressScope, ProgressTable, RoleCoverage, ScopeIssue, ScopeProgress,
};
pub use registry::{
    denominator_from_rows, load_denominator, parse_csv, read_csv, DenomEntry, Denominator,
    Exclusion, InstitutionKind, InstitutionRow, LoadError,
};
pub use robots::{RobotsGate, RobotsVerdict, PRODUCT_TOKEN, ROBOTS_MAX_BYTES};
