//! Institution progress table (기관 진행표, T-DT-04).
//!
//! One [`InstitutionProgress`] exists per in-scope denominator institution. Within it,
//! every denominator document item is tracked per document role
//! ([`DENOMINATOR_DOC_ROLES`]: 약관·특약·별표·사업방법서·상품요약서·가격 조건) and the
//! **acquired** count follows the 09 P02 rule:
//!
//! > 확보 = 원본 보존(RawAsset) + 구획 추출(DocumentSegment) + 판 연결(accepted realizes)
//! > — all three. A reason-only record stays in the denominator with its reason and never
//! > enters the numerator.
//!
//! Ten items that carry nothing but an unacquired reason do not move the rate.

use std::collections::{BTreeMap, BTreeSet};

use onjeon_contracts::{AcquisitionStatus, DocRole};

use super::manifest::{GapRecord, ProductCandidate, ScopeDesc, DENOMINATOR_DOC_ROLES};
use super::registry::{DenomEntry, InstitutionKind};

/// The three pieces of evidence an acquired document needs (09 P02).
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct AcquisitionEvidence {
    /// 원본 보존: the raw bytes are archived (`objects/sha256/…`).
    pub raw_stored: bool,
    /// 구획 추출: a `DocumentSegment` was extracted from the original.
    pub segment_extracted: bool,
    /// 판 연결: an accepted `realizes` assertion ties the segment to a terms edition.
    pub edition_link_accepted: bool,
}

impl AcquisitionEvidence {
    pub fn acquired(&self) -> bool {
        self.raw_stored && self.segment_extracted && self.edition_link_accepted
    }
}

/// One denominator document item: what it is, what evidence exists, and — when it is not
/// acquired — the recorded reason.
#[derive(Debug, Clone)]
pub struct DenominatorItem {
    /// Actual discovered document reference, unique together with `doc_role` inside
    /// the institution. Never a fabricated product/role slot.
    pub item_id: String,
    pub doc_role: DocRole,
    pub evidence: AcquisitionEvidence,
    /// `Some` when the item is recorded with a non-acquired `acquisition_status` reason
    /// (`blocked`, `failed`, `not_found`, `not_disclosed`). The reason never upgrades an
    /// item to acquired; an item with both partial evidence and a reason stays
    /// unacquired under that reason.
    pub unacquired: Option<(AcquisitionStatus, String)>,
}

impl DenominatorItem {
    /// `true` only when all three evidence parts exist (09 P02).
    pub fn is_acquired(&self) -> bool {
        self.evidence.acquired()
    }
}

/// One institution's progress row: its denominator items plus the exploration state of
/// each scope axis (what enumeration reached, what is held or blocked).
#[derive(Debug, Clone)]
pub struct InstitutionProgress {
    pub institution_id: String,
    pub kind: InstitutionKind,
    /// Conservative axis summary, derived from every scope below. A success on one
    /// role/channel/period cannot replace another scope's hold or blocked state.
    pub exploration: BTreeMap<String, ExplorationState>,
    /// Authoritative latest state and gap reasons for each precise scope and role.
    pub scope_progress: BTreeMap<ProgressScope, ScopeProgress>,
    /// Candidate product identities, kept separate from document counts.
    pub discovered_products: BTreeSet<String>,
    /// Structured metadata and document edges, also populated by document-first runs.
    pub product_candidates: BTreeMap<String, ProductCandidate>,
    pub items: Vec<DenominatorItem>,
    /// All unresolved scopes for each role; no scope's reason replaces another's.
    pub unknown_denominators: BTreeMap<DocRole, Vec<ScopeIssue>>,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub struct ProgressScope {
    pub axis: String,
    pub sale_status: Option<String>,
    pub channel: Option<String>,
    pub period_from: Option<String>,
    pub period_to: Option<String>,
    pub doc_role: Option<DocRole>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ScopeProgress {
    pub state: ExplorationState,
    pub gaps: Vec<GapRecord>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ScopeIssue {
    pub scope: ProgressScope,
    pub progress: ScopeProgress,
}

impl InstitutionProgress {
    fn update_scope_state(
        &mut self,
        scope: &ScopeDesc,
        state: &ExplorationState,
        gaps: &[GapRecord],
    ) {
        let roles = if scope.axis == "documents" {
            DENOMINATOR_DOC_ROLES
                .iter()
                .filter(|r| scope.doc_roles.iter().any(|s| s == r.as_str()))
                .map(|r| Some(*r))
                .collect::<Vec<_>>()
        } else {
            vec![None]
        };
        for doc_role in roles {
            self.scope_progress.insert(
                ProgressScope {
                    axis: scope.axis.clone(),
                    sale_status: scope.sale_status.clone(),
                    channel: scope.channel.clone(),
                    period_from: scope.period_from.clone(),
                    period_to: scope.period_to.clone(),
                    doc_role,
                },
                ScopeProgress {
                    state: state.clone(),
                    gaps: gaps.to_vec(),
                },
            );
        }
        let states: Vec<_> = self
            .scope_progress
            .iter()
            .filter(|(key, _)| key.axis == scope.axis)
            .collect();
        if let Some((_, first)) = states.first() {
            let summary = if states.iter().all(|(_, p)| p.state == first.state) {
                first.state.clone()
            } else if states.iter().all(|(_, p)| p.state.reached_evidence()) {
                ExplorationState::Enumerated
            } else {
                ExplorationState::PartiallyEnumerated {
                    unexplored: states
                        .iter()
                        .filter(|(_, p)| !p.state.reached_evidence())
                        .map(|(key, p)| format!("{key:?}: {:?}", p.state))
                        .collect::<Vec<_>>()
                        .join("; "),
                }
            };
            self.exploration.insert(scope.axis.clone(), summary);
        }
        self.unknown_denominators.clear();
        for (key, progress) in &self.scope_progress {
            if progress.state.reached_evidence()
                || !matches!(key.axis.as_str(), "documents" | "product_list")
            {
                continue;
            }
            for role in DENOMINATOR_DOC_ROLES {
                if key.axis == "documents" && key.doc_role != Some(role) {
                    continue;
                }
                self.unknown_denominators
                    .entry(role)
                    .or_default()
                    .push(ScopeIssue {
                        scope: key.clone(),
                        progress: progress.clone(),
                    });
            }
        }
    }
}

/// Where a scope axis of an institution stands after enumeration.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ExplorationState {
    /// Not attempted yet.
    Unqueried,
    /// Enumerated to termination evidence.
    Enumerated,
    /// A verified empty list.
    EnumeratedEmpty,
    /// robots could not be checked — the host is on hold (보류), not failed.
    Hold { reason: String },
    /// Blocked (robots disallow/forbidden, login page, access denial).
    Blocked { reason: String },
    /// Enumeration attempted but failed before any termination evidence.
    Failed { reason: String },
    /// Partially enumerated — a range stayed unexplored.
    PartiallyEnumerated { unexplored: String },
    /// Not enumerated: no verified entrypoint, or the run never reached this axis.
    Unexplored { reason: String },
}

impl ExplorationState {
    /// `true` only when the axis was fully enumerated. A partial walk leaves an
    /// unknown denominator even though it records why enumeration stopped.
    pub fn reached_evidence(&self) -> bool {
        matches!(self, Self::Enumerated | Self::EnumeratedEmpty)
    }
}

/// Per-document-role counters for one institution (or the whole table).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct RoleCoverage {
    /// Denominator size for this role.
    pub expected: usize,
    /// Number of institutions with at least one unresolved scope for this role.
    /// The full scope counts and reasons are retained in `unknown_denominators`.
    pub unknown_scopes: usize,
    /// Items with all three evidence parts — the numerator of the acquisition rate.
    pub acquired: usize,
    /// Unacquired items by `acquisition_status` reason (plus `partial_evidence` for items
    /// with incomplete evidence and no explicit reason).
    pub unacquired: BTreeMap<String, usize>,
}

impl RoleCoverage {
    /// The acquisition rate only when the denominator is known and nonempty.
    /// Unqueried institutions and incomplete enumeration suppress numeric rates.
    pub fn rate(&self) -> Option<f64> {
        if self.expected == 0 || self.unknown_scopes > 0 {
            return None;
        }
        Some(self.acquired as f64 / self.expected as f64)
    }
}

/// The whole progress table: one row per in-scope institution (acceptance: 기관마다
/// 진행표), exclusions carried for reporting.
#[derive(Debug, Default)]
pub struct ProgressTable {
    pub rows: Vec<InstitutionProgress>,
}

impl ProgressTable {
    /// Build one row per in-scope institution; every scope axis starts `Unqueried`.
    ///
    /// Both product and document inventories are required for a known denominator.
    /// Seed their whole-institution unknowns before any requests: unqueried rows must
    /// continue to suppress aggregate rates after another institution succeeds.
    /// A narrower sale/channel/period success cannot prove the whole inventory.
    /// Registry-carried statuses still arrive through manifests, never as successes.
    pub fn for_denominator<'a>(entries: impl Iterator<Item = &'a DenomEntry>) -> Self {
        let mut rows = Vec::new();
        for e in entries {
            let mut exploration = BTreeMap::new();
            exploration.insert("disclosure_entry".into(), ExplorationState::Unqueried);
            exploration.insert("product_list".into(), ExplorationState::Unqueried);
            exploration.insert("documents".into(), ExplorationState::Unqueried);
            exploration.insert("notices".into(), ExplorationState::Unqueried);
            let mut progress = InstitutionProgress {
                institution_id: e.row.insurer_id.clone(),
                kind: e.kind,
                exploration,
                scope_progress: BTreeMap::new(),
                discovered_products: BTreeSet::new(),
                product_candidates: BTreeMap::new(),
                items: Vec::new(),
                unknown_denominators: BTreeMap::new(),
            };
            for axis in ["disclosure_entry", "product_list", "documents", "notices"] {
                progress.update_scope_state(
                    &super::manifest::ScopeDesc {
                        axis: axis.into(),
                        institution_id: e.row.insurer_id.clone(),
                        sale_status: None,
                        channel: None,
                        period_from: None,
                        period_to: None,
                        doc_roles: DENOMINATOR_DOC_ROLES
                            .iter()
                            .map(|r| r.as_str().into())
                            .collect(),
                    },
                    &ExplorationState::Unqueried,
                    &[],
                );
            }
            rows.push(progress);
        }
        rows.sort_by(|a, b| a.institution_id.cmp(&b.institution_id));
        Self { rows }
    }

    pub fn from_discoveries(
        denominator: &super::registry::Denominator,
        manifests: &[super::manifest::DiscoveryManifest],
    ) -> Result<Self, &'static str> {
        let mut table = Self::for_denominator(denominator.in_scope.iter());
        for manifest in manifests {
            table.apply_discovery(manifest)?;
        }
        Ok(table)
    }

    pub fn apply_discovery(
        &mut self,
        manifest: &super::manifest::DiscoveryManifest,
    ) -> Result<(), &'static str> {
        if manifest.scope.axis == "documents"
            && (manifest.scope.doc_roles.is_empty()
                || manifest
                    .scope
                    .doc_roles
                    .iter()
                    .any(|role| !DENOMINATOR_DOC_ROLES.iter().any(|r| r.as_str() == role)))
        {
            return Err("document scope requires known denominator roles");
        }
        // discovered_ids has no per-item role annotation. Require one explicit role
        // for document identities; multiplying every id across roles fabricates items.
        let document_role =
            if manifest.scope.axis == "documents" && !manifest.discovered_ids.is_empty() {
                if manifest.scope.doc_roles.len() != 1 {
                    return Err("document discoveries require one explicit document role");
                }
                Some(
                    *DENOMINATOR_DOC_ROLES
                        .iter()
                        .find(|r| r.as_str() == manifest.scope.doc_roles[0])
                        .ok_or("document role outside denominator")?,
                )
            } else {
                None
            };
        let row = self
            .row_mut(&manifest.scope.institution_id)
            .ok_or("institution outside denominator")?;
        let state = super::enumerate::exploration_state_of(&manifest.termination);
        row.update_scope_state(&manifest.scope, &state, &manifest.gaps);
        for candidate in &manifest.product_candidates {
            row.product_candidates
                .insert(candidate.candidate_id.clone(), candidate.clone());
        }
        if manifest.scope.axis == "documents" {
            let reason = manifest
                .gaps
                .iter()
                .map(|g| g.reason.as_str())
                .collect::<Vec<_>>()
                .join("; ");
            let reason = if reason.is_empty() {
                "discovered document lacks acquisition evidence".into()
            } else {
                reason
            };
            let status = match state {
                ExplorationState::Blocked { .. } => AcquisitionStatus::Blocked,
                ExplorationState::Failed { .. } => AcquisitionStatus::Failed,
                _ => AcquisitionStatus::Unqueried,
            };
            if let Some(role) = document_role {
                for id in &manifest.discovered_ids {
                    if !row
                        .items
                        .iter()
                        .any(|item| item.doc_role == role && item.item_id == *id)
                    {
                        row.items.push(DenominatorItem {
                            item_id: id.clone(),
                            doc_role: role,
                            evidence: AcquisitionEvidence::default(),
                            unacquired: Some((status, reason.clone())),
                        });
                    }
                    // Re-enumeration preserves per-document acquisition evidence and
                    // reasons. A scope failure is not a download failure for every
                    // document previously found in another channel or period.
                }
            }
            return Ok(());
        }
        if manifest.scope.axis == "product_list" {
            row.discovered_products
                .extend(manifest.discovered_ids.iter().cloned());
        }
        Ok(())
    }

    pub fn row_mut(&mut self, institution_id: &str) -> Option<&mut InstitutionProgress> {
        self.rows
            .iter_mut()
            .find(|r| r.institution_id == institution_id)
    }

    /// Per-role coverage for one institution.
    pub fn coverage_of(&self, institution_id: &str) -> BTreeMap<DocRole, RoleCoverage> {
        let empty = Vec::new();
        let items = self
            .rows
            .iter()
            .find(|r| r.institution_id == institution_id)
            .map(|r| &r.items)
            .unwrap_or(&empty);
        let mut out = coverage(items);
        if let Some(row) = self
            .rows
            .iter()
            .find(|r| r.institution_id == institution_id)
        {
            for role in row.unknown_denominators.keys() {
                out.entry(*role).or_default().unknown_scopes += 1;
            }
        }
        out
    }

    /// Per-role coverage over every institution's items (the aggregate the coverage
    /// endpoint will read; `expected` is the sum of denominators).
    pub fn coverage_all(&self) -> BTreeMap<DocRole, RoleCoverage> {
        let items: Vec<DenominatorItem> = self
            .rows
            .iter()
            .flat_map(|r| r.items.iter().cloned())
            .collect();
        let mut out = coverage(&items);
        for row in &self.rows {
            for role in row.unknown_denominators.keys() {
                out.entry(*role).or_default().unknown_scopes += 1;
            }
        }
        out
    }
}

/// Count items per role. `acquired` needs all three evidence parts; everything else lands
/// in `unacquired[<reason>]` — a recorded reason is never a numerator unit (09 P02).
pub fn coverage(items: &[DenominatorItem]) -> BTreeMap<DocRole, RoleCoverage> {
    let mut out: BTreeMap<DocRole, RoleCoverage> = DENOMINATOR_DOC_ROLES
        .iter()
        .map(|r| (*r, RoleCoverage::default()))
        .collect();
    for item in items {
        let cov = out.entry(item.doc_role).or_default();
        cov.expected += 1;
        if item.is_acquired() {
            cov.acquired += 1;
            continue;
        }
        let reason = match &item.unacquired {
            Some((status, _)) => status.as_str().to_string(),
            None => "partial_evidence".into(),
        };
        *cov.unacquired.entry(reason).or_insert(0) += 1;
    }
    out
}
