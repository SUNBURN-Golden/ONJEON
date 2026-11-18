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
            adapter_version: "0.3.0".into(),
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
                empty_marker: None,
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
            adapter_version: "0.3.0".into(),
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
                empty_marker: None,
            },
            doc_roles: vec!["disclosure_list".into()],
            max_pages: 1,
        }],
    )
}

/// A per-insurer adapter built from one denominator entry (`DenomEntry`).
///
/// The adapter combines registry identity/access with survey-backed list endpoints.
/// When no concrete request/parser pair is verified, the adapter emits no plan.
/// `preflight_states` exposes the registry-recorded status so the caller can
/// record the same state through a manifest instead of a fresh attempt (기록된 미확보
/// 사유를 다시 시도로 위장하지 않는다).
pub struct InsurerAdapter<'a> {
    entry: &'a DenomEntry,
    manifest: AdapterManifest,
    plans: Vec<ListPlan>,
}

impl<'a> InsurerAdapter<'a> {
    pub fn for_entry(entry: &'a DenomEntry) -> Self {
        let plans = lifeplanet_plans(entry);
        let host = super::fetch::split_url(&entry.row.disclosure_url)
            .map(|(_, h, _, _)| h.to_string())
            .unwrap_or_default();
        Self {
            entry,
            manifest: AdapterManifest {
                source_id: format!("insurer:{}", entry.row.insurer_id),
                adapter_version: "0.3.0".into(),
                allowed_hosts: if host.is_empty() {
                    Vec::new()
                } else {
                    vec![host]
                },
                inventory_entrypoints: plans
                    .iter()
                    .map(|p| p.entrypoint.clone())
                    .collect::<std::collections::BTreeSet<_>>()
                    .into_iter()
                    .collect(),
                query_matrix_version: "qm-insurer-0.2".into(),
                acquisition_method: "static_html".into(),
                rate_policy: "default".into(),
                access_review_ref: if plans.is_empty() {
                    format!(
                        "data/registry/{}.csv#{}",
                        entry.row.registry_file, entry.row.insurer_id
                    )
                } else {
                    "docs/research/2026-10-10_source_survey/C_life.md#35-교보라이프플래닛".into()
                },
                supported_document_roles: plans
                    .iter()
                    .flat_map(|p| p.scope.doc_roles.clone())
                    .collect::<std::collections::BTreeSet<_>>()
                    .into_iter()
                    .collect(),
                pagination_termination_rule: "verified_complete_embedded_inventory".into(),
                known_limitations: if plans.is_empty() {
                    vec!["공시실 진입점만으로 목록 구조를 증명할 수 없음 — 검증된 기관별 파서가 없어 전 범위 미탐색".into()]
                } else {
                    vec![
                        "C_life §2·§3.5의 라이프플래닛 전량 내장 목록만 지원; 실제 응답 재검증은 수행하지 않음".into(),
                        "발견 행은 관측 메타데이터 해시로 식별; 판매본 확정이나 약관 판 연결을 주장하지 않음(H1·H14)".into(),
                        "특약·별표·가격 및 누락된 문서 참조는 별도 열거 증거가 없어 미확인 유지".into(),
                    ]
                },
                owner: "collect".into(),
            },
            plans,
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

    /// Only survey-backed request/parser pairs can enumerate a denominator. A
    /// reachable landing page alone supplies no list or termination evidence.
    fn plans(&self, _entry: &DenomEntry) -> Vec<ListPlan> {
        self.plans.clone()
    }
}

/// C_life §2 observes GET and a complete outData.prdList on both endpoints.
/// Other insurers require verified request/parser pairs; no generic probe pretends
/// to implement enumeration for them. Their progress rows remain unknown.
fn lifeplanet_plans(entry: &DenomEntry) -> Vec<ListPlan> {
    let row = &entry.row;
    if row.insurer_id != "life-kyobo-lifeplanet"
        || row.disclosure_status != Some(AcquisitionStatus::Archived)
        || row.disclosure_access != HostAccess::Reachable
        || row.disclosure_url != "https://www.lifeplanet.co.kr/disclosure/good/HPDA01S0.dev"
    {
        return Vec::new();
    }
    let mut plans = Vec::new();
    for (sale_status, page) in [("selling", "HPDA11S0.dev"), ("stopped", "HPDA21S0.dev")] {
        for (axis, role, field) in [
            ("product_list", "disclosure_list", None),
            ("documents", "terms", Some("insTxtPat")),
            ("documents", "summary", Some("prdSryPat")),
            ("documents", "business_method", Some("prdMdPat")),
        ] {
            plans.push(ListPlan {
                scope: ScopeDesc {
                    axis: axis.into(),
                    institution_id: row.insurer_id.clone(),
                    sale_status: Some(sale_status.into()),
                    channel: Some("online".into()),
                    period_from: None,
                    period_to: None,
                    doc_roles: vec![role.into()],
                },
                query_signature: format!("scope={axis};sale={sale_status};role={role}"),
                entrypoint: format!("https://www.lifeplanet.co.kr/disclosure/good/{page}"),
                pagination: Pagination::SinglePage,
                parser: ListParser::Lifeplanet {
                    document_field: field.map(String::from),
                },
                max_pages: 1,
            });
        }
    }
    plans
}

/// The document roles a company disclosure room is expected to publish (09 P02 axes):
/// 약관·특약·별표·사업방법서·상품요약서·가격 조건.
pub fn company_doc_roles() -> Vec<DocRole> {
    super::manifest::DENOMINATOR_DOC_ROLES.to_vec()
}
