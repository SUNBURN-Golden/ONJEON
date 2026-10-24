//! The enumeration driver (T-DT-04): walk one `ListPlan`, record every page, and produce
//! the termination evidence — or the unexplored/hold/blocked range — honestly.
//!
//! Termination is evidence, not a guess (Masterplan §23.2):
//! - `advertised_total_reached`: unique items reach the (non-zero) total the list
//!   advertises and the endpoint reports no further cursor. A reported cursor past the
//!   total is a contradiction the walk follows instead of accepting; an advertised zero
//!   is reconciled by the empty-page rule, never counted as "reached".
//! - `empty_page`: the *first* fetched page returns zero items while the endpoint
//!   advertises no total (or advertises zero) and offers no next pointer — a successful
//!   empty list (`empty_success`), never an error. An empty page that contradicts the
//!   endpoint is not termination evidence: while the endpoint still offers a next
//!   pointer the walk continues, and an empty page fetched before the advertised total
//!   was reached is a `stall` with an unexplored tail.
//! - `next_pointer_absent`: the list itself says there is no next page (a mid-walk empty
//!   page with no shortfall ends here too — it is `Enumerated`, never `EnumeratedEmpty`).
//! - `page_repeat`: a new cursor returned an identical page hash — the walk stalls; the
//!   tail is unexplored. A repeated last page is never a successful end.
//! - `stall`: no next pointer but the advertised total was not reached — unexplored tail.
//! - `max_pages_reached` / `fetch_failed` / `parse_failed` — unexplored or failed ranges.
//! - `robots_hold` / `robots_blocked` / `login_page` / `access_denied` — never
//!   enumerated, never counted; a 401/403 from the list URL stays `blocked` all the way
//!   into the institution progress table, it is not a `failed` fetch.

use std::collections::BTreeSet;

use crate::digest::sha256_hex;
use crate::time::rfc3339;

use super::fetch::{Fetch, FetchError};
use super::listpage::{classify, parse_page, ListParser, PageClass};
use super::manifest::{
    DiscoveryManifest, GapRecord, ManifestResult, PageRecord, RequestConditions, ScopeDesc,
    Termination,
};
use super::robots::{RobotsGate, RobotsVerdict};

/// List pages are capped at 4 MiB — a disclosure list far smaller than a document.
pub const LIST_PAGE_MAX_BYTES: usize = 4 * 1024 * 1024;

/// How cursors move through a list.
#[derive(Debug, Clone)]
pub enum Pagination {
    /// `entrypoint` contains `{cursor}`; cursors are consecutive page numbers starting at
    /// `start`. The next pointer exists while the page yielded items.
    PageNumber { start: u32 },
    /// `entrypoint` contains `{cursor}`; the first request uses `first_cursor` and each
    /// page must yield the next pointer (JSON `next_field`) or the walk ends.
    Cursor { first_cursor: String },
    /// A single-page list (the entrypoint is fetched once; no `{cursor}` is needed).
    SinglePage,
}

/// One enumeration unit: a scope slice, its request shape, and its parser.
#[derive(Debug, Clone)]
pub struct ListPlan {
    pub scope: ScopeDesc,
    /// Stable identifier of this query combination (filter values in one string).
    pub query_signature: String,
    /// URL template; `{cursor}` is substituted for paged plans.
    pub entrypoint: String,
    pub pagination: Pagination,
    pub parser: ListParser,
    /// Hard stop so a malformed site cannot make the walk unbounded.
    pub max_pages: u32,
}

/// Run context shared by every plan of one enumeration run.
pub struct Enumerator<'a> {
    pub fetch: &'a dyn Fetch,
    pub gate: &'a mut RobotsGate,
    /// Clock for `fetched_at`/`recorded_at` (epoch seconds).
    pub clock: &'a dyn Fn() -> u64,
    pub page_cap_bytes: usize,
    /// Rate policy label carried into `request_conditions` (the scheduler enforces it;
    /// the enumerator only records which policy applied — contract §1 `요청 조건`).
    pub rate_policy: String,
}

impl<'a> Enumerator<'a> {
    /// Enumerate `plan` into a `DiscoveryManifest`. `meta` identifies the run.
    pub fn run(&mut self, plan: &ListPlan, meta: &RunMeta) -> DiscoveryManifest {
        let mut pages = Vec::new();
        let mut seen: BTreeSet<String> = BTreeSet::new();
        let mut product_candidates = Vec::new();
        let mut advertised_total = None;
        let mut termination = None;
        let mut gaps = Vec::new();

        let mut cursor = match &plan.pagination {
            Pagination::PageNumber { start } => start.to_string(),
            Pagination::Cursor { first_cursor } => first_cursor.clone(),
            Pagination::SinglePage => String::new(),
        };
        let mut prev_hash: Option<String> = None;
        let mut robots_outcome = "none".to_string();

        for _ in 0..plan.max_pages {
            let url = plan.entrypoint.replace("{cursor}", &cursor);
            let host_verdict = self.gate.check(self.fetch, &url, (self.clock)());
            if robots_outcome == "none" {
                robots_outcome = match &host_verdict {
                    RobotsVerdict::Allow { reason, .. } => format!("allow:{reason}"),
                    RobotsVerdict::Disallow => "disallow".into(),
                    RobotsVerdict::Forbidden => "forbidden".into(),
                    RobotsVerdict::Unverifiable { reason } => format!("hold:{reason}"),
                };
            }
            match host_verdict {
                RobotsVerdict::Disallow => {
                    termination = Some(Termination::RobotsBlocked {
                        reason: "robots_disallow".into(),
                    });
                    gaps.push(gap("blocked", unreached_range(&pages), "robots_disallow"));
                    break;
                }
                RobotsVerdict::Forbidden => {
                    termination = Some(Termination::RobotsBlocked {
                        reason: "robots_forbidden".into(),
                    });
                    gaps.push(gap("blocked", unreached_range(&pages), "robots_forbidden"));
                    break;
                }
                RobotsVerdict::Unverifiable { reason } => {
                    termination = Some(Termination::RobotsHold {
                        reason: reason.to_string(),
                    });
                    gaps.push(gap("hold", unreached_range(&pages), reason));
                    break;
                }
                RobotsVerdict::Allow { .. } => {}
            }
            let fetched_at = rfc3339((self.clock)());
            let resp = match self.fetch.fetch(&url, self.page_cap_bytes) {
                Ok(r) => r,
                Err(e) => {
                    let detail = match e {
                        FetchError::TooLarge => "too_large",
                        FetchError::Refused => "refused",
                        FetchError::BadUrl => "bad_url",
                        FetchError::Network => "network",
                    };
                    termination = Some(Termination::FetchFailed {
                        at_cursor: cursor.clone(),
                        detail: detail.into(),
                    });
                    gaps.push(gap("failed", &format!("page_{cursor}"), detail));
                    break;
                }
            };
            let class = classify(
                resp.status,
                resp.header("content-type").unwrap_or(""),
                &resp.body,
                resp.truncated,
                plan.parser.expects_json(),
            );
            let page_hash = sha256_hex(&resp.body);
            let kind = match class {
                PageClass::List => "items",
                PageClass::LoginPage => "login_page",
                PageClass::ErrorPage => "error",
                PageClass::NotListContent => "not_list_content",
            };
            if class != PageClass::List {
                pages.push(PageRecord {
                    query_signature: plan.query_signature.clone(),
                    cursor: cursor.clone(),
                    url,
                    http_status: resp.status,
                    item_count: 0,
                    advertised_total: None,
                    first_item_id: None,
                    last_item_id: None,
                    page_hash,
                    next_pointer: None,
                    fetched_at,
                    page_kind: kind.into(),
                });
                termination = Some(match class {
                    PageClass::LoginPage => {
                        gaps.push(gap("blocked", "remaining_pages", "login_page"));
                        Termination::LoginPage {
                            at_cursor: cursor.clone(),
                        }
                    }
                    // 401/403 is access denial — `blocked`, not `failed`, in the gap
                    // record, the termination and the exploration state alike.
                    PageClass::ErrorPage if resp.status == 401 || resp.status == 403 => {
                        gaps.push(gap("blocked", &format!("page_{cursor}"), "access_denied"));
                        Termination::AccessDenied {
                            at_cursor: cursor.clone(),
                            http_status: resp.status,
                        }
                    }
                    PageClass::ErrorPage => {
                        gaps.push(gap("failed", &format!("page_{cursor}"), "http_error"));
                        Termination::FetchFailed {
                            at_cursor: cursor.clone(),
                            detail: format!("http_status_{}", resp.status),
                        }
                    }
                    _ => {
                        gaps.push(gap("failed", &format!("page_{cursor}"), "not_list_content"));
                        Termination::ParseFailed {
                            at_cursor: cursor.clone(),
                            detail: "not list content".into(),
                        }
                    }
                });
                break;
            }
            let parsed = match parse_page(&plan.parser, &resp.body) {
                Ok(p) => p,
                Err(detail) => {
                    pages.push(PageRecord {
                        query_signature: plan.query_signature.clone(),
                        cursor: cursor.clone(),
                        url,
                        http_status: resp.status,
                        item_count: 0,
                        advertised_total: None,
                        first_item_id: None,
                        last_item_id: None,
                        page_hash,
                        next_pointer: None,
                        fetched_at,
                        page_kind: "parse_failed".into(),
                    });
                    gaps.push(gap("failed", &format!("page_{cursor}"), detail));
                    termination = Some(Termination::ParseFailed {
                        at_cursor: cursor.clone(),
                        detail: detail.into(),
                    });
                    break;
                }
            };
            if let Some(t) = parsed.advertised_total {
                advertised_total = Some(t);
            }
            for id in &parsed.item_ids {
                seen.insert(id.clone());
            }
            for candidate in &parsed.product_candidates {
                if !product_candidates.contains(candidate) {
                    product_candidates.push(candidate.clone());
                }
            }
            // A page repeating byte-for-byte on a fresh cursor is not progress and never a
            // successful end (H8 counterexample; Masterplan §23.2).
            let repeated = prev_hash.as_deref() == Some(page_hash.as_str());
            let next_pointer = next_pointer(plan, &cursor, &parsed);
            pages.push(PageRecord {
                query_signature: plan.query_signature.clone(),
                cursor: cursor.clone(),
                url,
                http_status: resp.status,
                item_count: parsed.item_ids.len() as u32,
                advertised_total: parsed.advertised_total,
                first_item_id: parsed.item_ids.first().cloned(),
                last_item_id: parsed.item_ids.last().cloned(),
                page_hash: page_hash.clone(),
                next_pointer: next_pointer.clone(),
                fetched_at,
                page_kind: if parsed.item_ids.is_empty() {
                    "empty".into()
                } else {
                    "items".into()
                },
            });
            if repeated {
                gaps.push(gap(
                    "unexplored",
                    &format!("tail_after_{cursor}"),
                    "page_repeat",
                ));
                termination = Some(Termination::PageRepeat {
                    at_cursor: cursor.clone(),
                });
                break;
            }
            prev_hash = Some(page_hash);
            let unique = seen.len() as u64;
            // A cursor the endpoint itself reports is its own signal that the list goes
            // on (a page-number successor is synthesized here, not reported). Reaching
            // the advertised total while such a cursor is offered is a contradiction,
            // not termination evidence — keep walking; the end is then the absent next
            // pointer, bounded by page_repeat/max_pages.
            let endpoint_next =
                matches!(plan.pagination, Pagination::Cursor { .. }) && next_pointer.is_some();
            if let Some(total) = advertised_total {
                // An advertised zero is never "reached": zero items with total zero is
                // the empty-list question and goes through the empty-page reconciliation
                // below (first page → EmptyPage/empty_success; next cursor → walk on),
                // and items under an advertised zero contradict the total — the walk
                // ends on the list's own next pointer instead.
                if total > 0 && unique >= total && !endpoint_next {
                    termination = Some(Termination::AdvertisedTotalReached {
                        unique_items: unique,
                        advertised_total: total,
                    });
                    break;
                }
            }
            if parsed.item_ids.is_empty() {
                // Reconcile the endpoint's own signals before accepting an empty page
                // as the end of the list (§23.2): an unreached advertised total and a
                // next pointer the endpoint still offers both contradict it.
                match next_pointer {
                    // The endpoint advertises another page — the empty page is not
                    // termination evidence; keep walking (bounded by repeat/max_pages).
                    Some(next) => cursor = next,
                    None => {
                        termination = Some(match advertised_total {
                            // Empty before the advertised total: same stall as a
                            // missing next pointer — the tail stays unexplored.
                            Some(total) if unique < total => {
                                gaps.push(gap(
                                    "unexplored",
                                    &format!("tail_after_{cursor}"),
                                    "empty_page_before_advertised_total",
                                ));
                                Termination::Stall {
                                    at_cursor: cursor.clone(),
                                    unique_items: unique,
                                    advertised_total: total,
                                }
                            }
                            // Only a first empty page is a verified empty list; a
                            // mid-walk empty page ends a non-empty list — Enumerated.
                            _ if pages.len() == 1 => Termination::EmptyPage {
                                at_cursor: cursor.clone(),
                            },
                            _ => Termination::NextPointerAbsent {
                                at_cursor: cursor.clone(),
                            },
                        });
                        break;
                    }
                }
                continue;
            }
            match next_pointer {
                Some(next) => cursor = next,
                None => {
                    termination = Some(match advertised_total {
                        Some(total) if unique < total => {
                            gaps.push(gap(
                                "unexplored",
                                &format!("tail_after_{cursor}"),
                                "stall_before_advertised_total",
                            ));
                            Termination::Stall {
                                at_cursor: cursor.clone(),
                                unique_items: unique,
                                advertised_total: total,
                            }
                        }
                        _ => Termination::NextPointerAbsent {
                            at_cursor: cursor.clone(),
                        },
                    });
                    break;
                }
            }
        }
        if termination.is_none() {
            gaps.push(gap("unexplored", "tail", "max_pages_reached"));
            termination = Some(Termination::MaxPagesReached {
                at_cursor: cursor.clone(),
            });
        }
        let termination = termination.unwrap();
        let empty_success = matches!(termination, Termination::EmptyPage { .. })
            && pages.len() == 1
            && pages[0].item_count == 0;
        let manifest_id = format!(
            "dm:{}:{}:{}",
            meta.survey_round,
            meta.source_id,
            &sha256_hex(
                format!(
                    "{}:{}:{}",
                    plan.scope.institution_id, plan.scope.axis, plan.query_signature
                )
                .as_bytes()
            )[..16]
        );
        DiscoveryManifest {
            kind: "discovery_manifest".into(),
            manifest_id,
            survey_round: meta.survey_round.clone(),
            source_id: meta.source_id.clone(),
            adapter_version: meta.adapter_version.clone(),
            scope: plan.scope.clone(),
            request_conditions: RequestConditions {
                query_signature: plan.query_signature.clone(),
                entrypoint: plan.entrypoint.clone(),
                pagination: pagination_name(&plan.pagination).into(),
                max_pages: plan.max_pages,
                rate_policy: self.rate_policy.clone(),
                robots: robots_outcome,
            },
            result: ManifestResult {
                item_count: pages.iter().map(|p| p.item_count as u64).sum(),
                unique_item_count: seen.len() as u64,
                advertised_total,
                empty_success,
            },
            pages,
            termination,
            discovered_ids: seen.into_iter().collect(),
            product_candidates,
            gaps,
            recorded_at: rfc3339((self.clock)()),
        }
    }
}

/// Run identity stamped on every manifest of the run.
pub struct RunMeta {
    pub survey_round: String,
    pub source_id: String,
    pub adapter_version: String,
}

fn next_pointer(
    plan: &ListPlan,
    cursor: &str,
    parsed: &super::listpage::ParsedPage,
) -> Option<String> {
    match &plan.pagination {
        Pagination::PageNumber { .. } => {
            if parsed.item_ids.is_empty() {
                None
            } else {
                Some(match cursor.parse::<u32>() {
                    Ok(n) => (n + 1).to_string(),
                    Err(_) => format!("{cursor}+1"),
                })
            }
        }
        Pagination::Cursor { .. } => parsed.next_cursor.clone(),
        Pagination::SinglePage => None,
    }
}

/// The slice a robots stop leaves unrecorded: `whole_scope` before the first page,
/// `remaining_pages` once earlier pages were fetched and recorded.
fn unreached_range(pages: &[PageRecord]) -> &'static str {
    if pages.is_empty() {
        "whole_scope"
    } else {
        "remaining_pages"
    }
}

fn pagination_name(p: &Pagination) -> &'static str {
    match p {
        Pagination::PageNumber { .. } => "page_number",
        Pagination::Cursor { .. } => "cursor",
        Pagination::SinglePage => "single_page",
    }
}

/// A manifest for a scope that produced no plan at all (unverified entrypoint): nothing
/// was requested and the whole scope is unexplored with the recorded reason. Every
/// institution scope gets a manifest — enumerated or not — so the denominator's record
/// has no silent cells.
pub fn unenumerated_manifest(
    scope: ScopeDesc,
    query_signature: &str,
    entrypoint: &str,
    meta: &RunMeta,
    reason: &str,
    recorded_at: &str,
) -> DiscoveryManifest {
    let manifest_id = format!(
        "dm:{}:{}:{}",
        meta.survey_round,
        meta.source_id,
        &sha256_hex(
            format!(
                "{}:{}:{}",
                scope.institution_id, scope.axis, query_signature
            )
            .as_bytes()
        )[..16]
    );
    DiscoveryManifest {
        kind: "discovery_manifest".into(),
        manifest_id,
        survey_round: meta.survey_round.clone(),
        source_id: meta.source_id.clone(),
        adapter_version: meta.adapter_version.clone(),
        scope: scope.clone(),
        request_conditions: RequestConditions {
            query_signature: query_signature.into(),
            entrypoint: entrypoint.into(),
            pagination: "none".into(),
            max_pages: 0,
            rate_policy: "none".into(),
            robots: "none".into(),
        },
        pages: Vec::new(),
        termination: Termination::EntrypointUnverified {
            detail: reason.into(),
        },
        discovered_ids: Vec::new(),
        product_candidates: Vec::new(),
        result: ManifestResult {
            item_count: 0,
            unique_item_count: 0,
            advertised_total: None,
            empty_success: false,
        },
        gaps: vec![gap("unexplored", "whole_scope", reason)],
        recorded_at: recorded_at.into(),
    }
}

/// Map a termination onto the scope's exploration state for the progress table.
pub fn exploration_state_of(t: &Termination) -> super::progress::ExplorationState {
    use super::progress::ExplorationState as S;
    match t {
        Termination::AdvertisedTotalReached { .. } | Termination::NextPointerAbsent { .. } => {
            S::Enumerated
        }
        Termination::EmptyPage { .. } => S::EnumeratedEmpty,
        Termination::RobotsHold { reason } => S::Hold {
            reason: reason.clone(),
        },
        Termination::RobotsBlocked { reason } => S::Blocked {
            reason: reason.clone(),
        },
        Termination::LoginPage { .. } => S::Blocked {
            reason: "login_page".into(),
        },
        Termination::AccessDenied { .. } => S::Blocked {
            reason: "access_denied".into(),
        },
        Termination::FetchFailed { detail, .. } => S::Failed {
            reason: detail.clone(),
        },
        Termination::ParseFailed { detail, .. } => S::Failed {
            reason: detail.clone(),
        },
        Termination::PageRepeat { at_cursor } => S::PartiallyEnumerated {
            unexplored: format!("tail_after_{at_cursor}"),
        },
        Termination::Stall { at_cursor, .. } => S::PartiallyEnumerated {
            unexplored: format!("tail_after_{at_cursor}"),
        },
        Termination::MaxPagesReached { at_cursor } => S::PartiallyEnumerated {
            unexplored: format!("tail_after_{at_cursor}"),
        },
        Termination::EntrypointUnverified { detail } => S::Unexplored {
            reason: detail.clone(),
        },
    }
}

fn gap(kind: &str, range: &str, reason: &str) -> GapRecord {
    GapRecord {
        kind: kind.into(),
        range: range.into(),
        reason: reason.into(),
    }
}
