//! Institution-level discovery adapters (T-DT-04): the `DiscoveryAdapter` contract plus
//! the per-institution implementations — association disclosure sites (협회) and each
//! insurer's own disclosure room (보험사별).
//!
//! Masterplan §24.1 gives the adapter contract: an `AdapterManifest` (source, version,
//! allowed hosts, entrypoints, termination rule, known limitations) and enumeration plans
//! per institution. The adapters here cover the *discovery* half of that contract —
//! `discover_scopes` / `enumerate_products` / `enumerate_notices` as list plans. Document
//! download itself flows through the archive pipeline (T-DT-01); an adapter only reports
//! what it found, what stayed unexplored, and what blocked it.
//!
//! Entrypoint honesty: a `ListPlan` is only emitted for a URL the registry or the
//! 2026-10-10 source survey actually observed. An institution whose disclosure entrypoint
//! is missing or unverified yields no plan — its scope is recorded unexplored with the
//! registry's gap reason instead, never guessed.

use onjeon_contracts::{AcquisitionStatus, DocRole, HostAccess};

use super::enumerate::{ListPlan, Pagination};
use super::listpage::ListParser;
use super::manifest::ScopeDesc;
use super::progress::ExplorationState;
use super::registry::DenomEntry;

/// AdapterManifest — Masterplan §24.1 shape (소스·버전·허용 호스트·진입점·종료 규칙·알려진 한계).
#[derive(Debug, Clone)]
pub struct AdapterManifest {
    pub source_id: String,
    pub adapter_version: String,
    pub allowed_hosts: Vec<String>,
    pub inventory_entrypoints: Vec<String>,
    pub query_matrix_version: String,
    pub acquisition_method: String,
    pub rate_policy: String,
    pub access_review_ref: String,
    pub supported_document_roles: Vec<String>,
    pub pagination_termination_rule: String,
    pub known_limitations: Vec<String>,
    pub owner: String,
}

/// The discovery contract: which list plans an institution needs enumerated.
pub trait DiscoveryAdapter {
    fn manifest(&self) -> &AdapterManifest;
    /// The list plans to run for this denominator entry. An empty vec means the adapter
    /// has no verified entrypoint for the institution — the caller records the scope
    /// unexplored, it does not invent a URL.
    fn plans(&self, entry: &DenomEntry) -> Vec<ListPlan>;
}

/// A parameterized association adapter (생명보험협회 공시실 / 손해보험협회 공시실).
///
/// The association axes enumerate *companies* and comparison-disclosure *products* for
/// every in-scope institution; `plans` therefore ignores the entry's own URL and emits
/// the association's configured list plans.
pub struct AssociationAdapter {
    manifest: AdapterManifest,
    plan_templates: Vec<PlanTemplate>,
}

#[derive(Debug, Clone)]
struct PlanTemplate {
    axis: &'static str,
    query_signature: String,
    entrypoint: String,
    pagination: Pagination,
    parser: ListParser,
    doc_roles: Vec<String>,
    max_pages: u32,
}

impl AssociationAdapter {
    /// An association adapter from a manifest and its verified list endpoints.
    pub fn new(manifest: AdapterManifest, plans: Vec<AssociationPlan>) -> Self {
        Self {
            manifest,
            plan_templates: plans
                .into_iter()
                .map(|p| PlanTemplate {
                    axis: p.axis,
                    query_signature: p.query_signature,
                    entrypoint: p.entrypoint,
                    pagination: p.pagination,
                    parser: p.parser,
                    doc_roles: p.doc_roles,
                    max_pages: p.max_pages,
                })
                .collect(),
        }
    }
}

/// One configured association list endpoint.
pub struct AssociationPlan {
    pub axis: &'static str,
    pub query_signature: String,
    pub entrypoint: String,
    pub pagination: Pagination,
    pub parser: ListParser,
    pub doc_roles: Vec<String>,
    pub max_pages: u32,
}

impl DiscoveryAdapter for AssociationAdapter {
    fn manifest(&self) -> &AdapterManifest {
        &self.manifest
    }

    /// Association axes cover every in-scope institution alike: the same list plans are
    /// emitted under the association's own scope (the institution id on each scope is the
    /// association source — the company filter is part of `query_signature` when the
    /// endpoint supports one, otherwise the whole list is walked once).
    fn plans(&self, _entry: &DenomEntry) -> Vec<ListPlan> {
        self.plan_templates
            .iter()
            .map(|t| ListPlan {
                scope: ScopeDesc {
                    axis: t.axis.into(),
                    institution_id: self.manifest.source_id.clone(),
                    sale_status: None,
                    channel: None,
                    period_from: None,
                    period_to: None,
                    doc_roles: t.doc_roles.clone(),
                },
                query_signature: t.query_signature.clone(),
                entrypoint: t.entrypoint.clone(),
                pagination: t.pagination.clone(),
                parser: t.parser.clone(),
                max_pages: t.max_pages,
            })
            .collect()
    }
}

/// 생명보험협회 공시실 (KLIA, `pub.insure.or.kr`). Entrypoints are the URLs the
/// 2026-10-09 registry survey and the 2026-10-10 source survey actually fetched.
///
/// NOTE (survey A, 절차 고지): `pub.insure.or.kr/robots.txt` was `User-agent: *
/// Disallow: /` on 2026-10-10 — under the robots gate every plan below correctly
/// terminates as `robots_blocked` until the robots or the access decision changes. The
/// adapter records that, it does not work around it.
pub fn klia() -> AssociationAdapter {
    AssociationAdapter::new(
        AdapterManifest {
            source_id: "klia_pub".into(),
            adapter_version: "0.1.0".into(),
            allowed_hosts: vec!["pub.insure.or.kr".into()],
            inventory_entrypoints: vec!["https://pub.insure.or.kr/mngtDis/mngtDis/list.do".into()],
            query_matrix_version: "qm-klia-0.1".into(),
            acquisition_method: "static_html".into(),
            rate_policy: "default".into(),
            access_review_ref: "docs/research/2026-10-10_source_survey/A_klia.md".into(),
            supported_document_roles: vec!["disclosure_list".into()],
            pagination_termination_rule: "advertised_total_or_empty_page".into(),
            known_limitations: vec![
                "robots.txt(2026-10-10 관측)가 User-agent:* Disallow:/ — 승인 전 열거 불가".into(),
                "비교공시 상품 목록 엔드포인트는 조사 H1 반례(판매본 키 불안정)로 미확정".into(),
            ],
            owner: "collect".into(),
        },
        vec![AssociationPlan {
            axis: "institution",
            query_signature: "scope=management_disclosure_company_list".into(),
            entrypoint: "https://pub.insure.or.kr/mngtDis/mngtDis/list.do".into(),
            pagination: Pagination::SinglePage,
            parser: ListParser::HtmlLinks {
                link_substring: "mngtDis".into(),
                id_query_key: "coId".into(),
                total_marker: None,
            },
            doc_roles: vec!["disclosure_list".into()],
            max_pages: 1,
        }],
    )
}

/// 손해보험협회 공시실 (KNIA, `kpub.knia.or.kr`). Entrypoints observed in the registry
/// survey (`sources.csv`) and the 2026-10-10 group-B survey: the 정기경영공시 회사 목록
/// page is the only entrypoint a GET/HTML request shape was observed for.
/// `/popup/disclosureList.do` answered only POST returning a JS object literal
/// (`{list:[{TP_NAME:'…'}]}`, B_knia §2, requests/B_knia.tsv) — a shape this adapter's
/// GET transport and HTML parser cannot reproduce, so the `documents` axis gets no plan
/// and stays unexplored instead of guessing a request the survey never saw.
pub fn knia() -> AssociationAdapter {
    AssociationAdapter::new(
        AdapterManifest {
            source_id: "knia_pub".into(),
            adapter_version: "0.1.0".into(),
            allowed_hosts: vec!["kpub.knia.or.kr".into()],
            inventory_entrypoints: vec![
                "https://kpub.knia.or.kr/managementDisc/regularly/regularlyDisclosure.do".into(),
            ],
            query_matrix_version: "qm-knia-0.1".into(),
            acquisition_method: "static_html".into(),
            rate_policy: "default".into(),
            access_review_ref: "docs/research/2026-10-10_source_survey/B_knia.md".into(),
            supported_document_roles: vec!["disclosure_list".into()],
            pagination_termination_rule: "advertised_total_or_empty_page".into(),
            known_limitations: vec![
                "robots.txt(2026-10-10 관측)가 403(WAF Block URL List) — 규칙 확인 불가로 게이트는 호스트를 robots_forbidden 차단으로 기록한다".into(),
                "상품비교공시 판매본 키는 H1 반례로 불안정 — 판매본 식별은 별도 관문".into(),
                "사업방법서·약관은 협회 비교공시에 없어 회사 공시실에서 열거한다(B_knia)".into(),
                "/popup/disclosureList.do는 POST+JS 객체 리터럴로만 관측됨 — GET·HTML 계획으로 재현할 검증된 요청 형태가 없어 documents 축은 미탐색으로 남는다(B_knia §2)".into(),
            ],
            owner: "collect".into(),
        },
        vec![AssociationPlan {
            axis: "institution",
            query_signature: "scope=regularly_disclosure_company_list".into(),
            entrypoint:
                "https://kpub.knia.or.kr/managementDisc/regularly/regularlyDisclosure.do".into(),
            pagination: Pagination::SinglePage,
            parser: ListParser::HtmlLinks {
                link_substring: "disclosurePopup.do".into(),
                id_query_key: "tptyCode".into(),
                total_marker: None,
            },
            doc_roles: vec!["disclosure_list".into()],
            max_pages: 1,
        }],
    )
}

/// A per-insurer adapter built from one denominator entry (`DenomEntry`).
///
/// The adapter's only verified entrypoint is the registry's `disclosure_url`. When it is
/// empty or the registry already records the entry as not secured, the adapter emits no
/// plan — `preflight_states` exposes the registry-recorded status so the caller can
/// record the same state through a manifest instead of a fresh attempt (기록된 미확보
/// 사유를 다시 시도로 위장하지 않는다).
pub struct InsurerAdapter<'a> {
    entry: &'a DenomEntry,
    manifest: AdapterManifest,
}

impl<'a> InsurerAdapter<'a> {
    pub fn for_entry(entry: &'a DenomEntry) -> Self {
        let host = super::fetch::split_url(&entry.row.disclosure_url)
            .map(|(_, h, _, _)| h.to_string())
            .unwrap_or_default();
        Self {
            entry,
            manifest: AdapterManifest {
                source_id: format!("insurer:{}", entry.row.insurer_id),
                adapter_version: "0.1.0".into(),
                allowed_hosts: if host.is_empty() {
                    Vec::new()
                } else {
                    vec![host]
                },
                inventory_entrypoints: if entry.row.disclosure_url.is_empty() {
                    Vec::new()
                } else {
                    vec![entry.row.disclosure_url.clone()]
                },
                query_matrix_version: "qm-insurer-0.1".into(),
                acquisition_method: "static_html".into(),
                rate_policy: "default".into(),
                access_review_ref: format!(
                    "data/registry/{}.csv#{}",
                    entry.row.registry_file, entry.row.insurer_id
                ),
                supported_document_roles: vec![
                    "terms", "rider_terms", "annex", "business_method", "summary",
                    "price_table", "disclosure_list", "notice",
                ]
                .into_iter()
                .map(String::from)
                .collect(),
                pagination_termination_rule: "advertised_total_or_empty_page".into(),
                known_limitations: vec![
                    "회사 공시실의 상품 목록 구조는 기관별 상이 — 페이지 파서는 확인된 진입점에만 적용".into(),
                ],
                owner: "collect".into(),
            },
        }
    }

    /// Registry-recorded state carried into the progress table before any enumeration:
    /// the disclosure-entry axis mirrors `disclosure_status`/`disclosure_gap_reason`, the
    /// product-list axis mirrors `product_list_status`/`product_list_reason`.
    pub fn preflight_states(&self) -> Vec<(String, ExplorationState)> {
        vec![
            (
                "disclosure_entry".into(),
                carried(
                    &self.entry.row.disclosure_status,
                    &self.entry.row.disclosure_gap_reason,
                ),
            ),
            (
                "product_list".into(),
                carried(
                    &self.entry.row.product_list_status,
                    &self.entry.row.product_list_reason,
                ),
            ),
        ]
    }
}

/// Map a registry `acquisition_status` (+its reason) onto an exploration state without
/// inventing access: `archived` becomes an enumeratable entry, `not_found` is a verified
/// absence, everything else stays the recorded non-acquired state.
fn carried(status: &Option<AcquisitionStatus>, reason: &str) -> ExplorationState {
    match status {
        Some(AcquisitionStatus::Archived) => ExplorationState::Unqueried,
        Some(AcquisitionStatus::Blocked) => ExplorationState::Blocked {
            reason: reason.to_string(),
        },
        Some(AcquisitionStatus::Failed) => ExplorationState::Failed {
            reason: reason.to_string(),
        },
        Some(AcquisitionStatus::NotFound) => ExplorationState::EnumeratedEmpty,
        Some(AcquisitionStatus::NotDisclosed) => ExplorationState::Blocked {
            reason: format!("not_disclosed: {reason}"),
        },
        _ => ExplorationState::Unqueried,
    }
}

impl<'a> DiscoveryAdapter for InsurerAdapter<'a> {
    fn manifest(&self) -> &AdapterManifest {
        &self.manifest
    }

    /// One product-list plan per verified disclosure entrypoint. The plan is bound to
    /// the entry the adapter was built for (`for_entry`) — the trait parameter is
    /// ignored so a plan can never describe an institution outside this manifest's
    /// `allowed_hosts`/`inventory_entrypoints`. It is only emitted when the registry
    /// recorded the entrypoint as reachable (`disclosure_access` = `reachable`) and
    /// secured (`disclosure_status` = `archived`); a `js_shell` home page or a missing
    /// URL yields nothing — the scope stays unexplored with the recorded reason.
    fn plans(&self, _entry: &DenomEntry) -> Vec<ListPlan> {
        let row = &self.entry.row;
        let verified = row.disclosure_status == Some(AcquisitionStatus::Archived)
            && row.disclosure_access == HostAccess::Reachable
            && !row.disclosure_url.is_empty();
        if !verified {
            return Vec::new();
        }
        vec![ListPlan {
            scope: ScopeDesc {
                axis: "disclosure_entry".into(),
                institution_id: row.insurer_id.clone(),
                sale_status: None,
                channel: None,
                period_from: None,
                period_to: None,
                doc_roles: vec!["disclosure_list".into()],
            },
            query_signature: "scope=company_disclosure_entry_probe".into(),
            entrypoint: row.disclosure_url.clone(),
            // 회사 공시실 목록은 보통 단일 화면+탭이다. 페이지 매개변수는 기관 검증 전까지
            // 만들지 않는다 — 첫 화면이 전부인지는 종료 증거로만 판단한다.
            pagination: Pagination::SinglePage,
            // 프로브: 진입 페이지의 모든 링크를 관측 항목으로 기록한다(빈 id_query_key는
            // href 전체를 id로 쓴다). 기관별 판매본 파서는 사이트 검증 뒤에 온다.
            parser: ListParser::EntryProbe,
            max_pages: 1,
        }]
    }
}

/// The document roles a company disclosure room is expected to publish (09 P02 axes):
/// 약관·특약·별표·사업방법서·상품요약서·가격 조건.
pub fn company_doc_roles() -> Vec<DocRole> {
    super::manifest::DENOMINATOR_DOC_ROLES.to_vec()
}
