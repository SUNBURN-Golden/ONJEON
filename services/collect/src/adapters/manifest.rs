//! `DiscoveryManifest` records (DATA_PIPELINE_CONTRACT §1, Masterplan §23.2).
//!
//! One manifest documents one enumeration run over one scope slice
//! (기관×판매상태×채널×기간×문서종류): the request conditions, every page's evidence,
//! what terminated the walk, the discovered item ids, and the ranges that stayed
//! unexplored or were blocked — including robots holds. A list that came back empty after
//! a successful fetch is a **successful empty list**, never an error; a failed or blocked
//! fetch is never an empty list.
//!
//! Manifests are records, not originals: they persist through `archive::put_once` under
//! `manifests/discovery/<source_id>/<stamp>_<sha16>.json` — write-once like every key.

use serde::Serialize;

use onjeon_contracts::DocRole;

use crate::archive::{put_once, ArchiveResult, PutOutcome};
use crate::digest::sha256_hex;
use crate::keys::observation_stamp;
use crate::store::Store;

/// The scope slice one enumeration covered (contract §1: 회사×판매상태×채널×기간×문서종류).
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ScopeDesc {
    /// Denominator axis this manifest enumerates (`institution` | `product_list` |
    /// `documents` | `notices`).
    pub axis: String,
    /// The institution row this scope belongs to (`insurer_id` from the registry, or the
    /// association's own source id for association-level axes).
    pub institution_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sale_status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub channel: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub period_from: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub period_to: Option<String>,
    /// Document roles this enumeration is responsible for.
    pub doc_roles: Vec<String>,
}

/// One fetched page of a list (Masterplan §23.2 record shape).
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct PageRecord {
    /// The query combination this page belongs to.
    pub query_signature: String,
    /// Page number or cursor actually requested.
    pub cursor: String,
    /// The concrete URL requested.
    pub url: String,
    pub http_status: u16,
    /// Items this page yielded (0 on a genuine empty page).
    pub item_count: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub advertised_total: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub first_item_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_item_id: Option<String>,
    /// SHA-256 of the response body — the repeat/stillness check.
    pub page_hash: String,
    /// Where the page says the next page is, if it says.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub next_pointer: Option<String>,
    pub fetched_at: String,
    /// `items` | `empty` | `login_page` | `error` | `not_list_content` — the
    /// classification, so a later reader can distinguish a 200 login page from a list.
    pub page_kind: String,
}

/// How a walk ended — evidence for "the list is done", never a guess.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Termination {
    /// The unique item count reached the advertised total.
    AdvertisedTotalReached {
        unique_items: u64,
        advertised_total: u64,
    },
    /// A page after the first came back with zero items.
    EmptyPage { at_cursor: String },
    /// The last page declared no next pointer (no advertised total existed or it matched).
    NextPointerAbsent { at_cursor: String },
    /// The host could not be checked under robots rules — the whole scope is on hold.
    RobotsHold { reason: String },
    /// robots rules or a 401/403 forbid the path (`robots_disallow` | `robots_forbidden`).
    RobotsBlocked { reason: String },
    /// A 200 login page — the scope is blocked behind authentication, not enumerated.
    LoginPage { at_cursor: String },
    /// The fetch failed (network/HTTP error page).
    FetchFailed { at_cursor: String, detail: String },
    /// A new cursor returned an identical page hash — the walk stalls here; the tail is
    /// unexplored, not done (Masterplan §23.2: a repeated last page is not a success).
    PageRepeat { at_cursor: String },
    /// No next pointer but the advertised total was not reached — a real stall, the
    /// remaining items are unexplored.
    Stall {
        at_cursor: String,
        unique_items: u64,
        advertised_total: u64,
    },
    /// `max_pages` reached before termination — the rest of the list is unexplored.
    MaxPagesReached { at_cursor: String },
    /// The page could not be parsed as the declared list format.
    ParseFailed { at_cursor: String, detail: String },
    /// The entrypoint itself is not verified for this institution (e.g. the registry
    /// carries no disclosure URL) — nothing was requested.
    EntrypointUnverified { detail: String },
}

/// A range the manifest could not cover, with why — `hold` (robots unverifiable),
/// `blocked` (robots/login/access denial), `failed`, or `unexplored` (not reached).
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct GapRecord {
    /// `hold` | `blocked` | `failed` | `unexplored`
    pub kind: String,
    /// Human-readable slice description (e.g. `tail_after_page_3`, `whole_scope`).
    pub range: String,
    pub reason: String,
}

/// The whole enumeration record.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct DiscoveryManifest {
    pub kind: String, // always "discovery_manifest"
    pub manifest_id: String,
    /// The survey/enumeration round this run belongs to (`조사 회차`).
    pub survey_round: String,
    pub source_id: String,
    pub adapter_version: String,
    pub scope: ScopeDesc,
    /// Request conditions: the query signature, entrypoint template, pagination mode and
    /// the page cap actually applied.
    pub request_conditions: RequestConditions,
    pub pages: Vec<PageRecord>,
    pub termination: Termination,
    /// Unique item ids discovered across all pages.
    pub discovered_ids: Vec<String>,
    pub result: ManifestResult,
    /// Ranges that stayed unexplored, on hold, or blocked — with reasons. These records
    /// are the "미탐색·차단 구간" of contract §1; they never count as enumerated.
    #[serde(rename = "gaps")]
    pub gaps: Vec<GapRecord>,
    pub recorded_at: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct RequestConditions {
    pub query_signature: String,
    pub entrypoint: String,
    pub pagination: String,
    pub max_pages: u32,
    pub rate_policy: String,
    /// The robots verdict of the first checked URL (`allow:<reason>` | `disallow` |
    /// `forbidden` | `hold:<reason>` | `none` when nothing was checked).
    pub robots: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ManifestResult {
    /// Sum of `item_count` over pages.
    pub item_count: u64,
    /// Distinct ids across pages (dedup overlap counted once).
    pub unique_item_count: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub advertised_total: Option<u64>,
    /// `true` only when fetching+classification succeeded and the list genuinely held no
    /// items — a *successful empty list*, distinct from every failure kind.
    pub empty_success: bool,
}

/// `manifests/discovery/<source_id>/<stamp>_<sha16>.json`.
pub fn manifest_key(source_id: &str, recorded_at: &str, record_sha256: &str) -> String {
    format!(
        "manifests/discovery/{}/{}_{}.json",
        source_id,
        observation_stamp(recorded_at),
        &record_sha256[..16]
    )
}

/// Serialize `m` as indented JSON and store it once. Returns `(key, outcome)`.
pub fn record_manifest(
    st: &dyn Store,
    m: &DiscoveryManifest,
) -> ArchiveResult<(String, PutOutcome)> {
    let mut body = serde_json::to_vec_pretty(m).expect("manifest serializes");
    body.push(b'\n');
    let key = manifest_key(&m.source_id, &m.recorded_at, &sha256_hex(&body));
    let outcome = put_once(st, &key, &body, "application/json")?;
    Ok((key, outcome))
}

/// The six denominator document kinds the progress table reports separately
/// (약관·특약·별표·사업방법서·상품요약서·가격 조건).
pub const DENOMINATOR_DOC_ROLES: [DocRole; 6] = [
    DocRole::Terms,
    DocRole::RiderTerms,
    DocRole::Annex,
    DocRole::BusinessMethod,
    DocRole::Summary,
    DocRole::PriceTable,
];
