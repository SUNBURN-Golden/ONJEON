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

use std::collections::BTreeMap;

use onjeon_contracts::{AcquisitionStatus, DocRole};

use super::manifest::DENOMINATOR_DOC_ROLES;
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
    /// Stable id inside the institution's denominator (e.g. `prod:<판매본>:<doc_role>`).
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
    /// Scope axis -> state, e.g. `product_list` -> `unexplored(<reason>)`.
    pub exploration: BTreeMap<String, ExplorationState>,
    pub items: Vec<DenominatorItem>,
    pub unknown_denominators: BTreeMap<DocRole, ExplorationState>,
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
    /// `true` when the axis reached termination evidence (`Enumerated`,
    /// `EnumeratedEmpty`, `PartiallyEnumerated`).
    pub fn reached_evidence(&self) -> bool {
        matches!(
            self,
            Self::Enumerated | Self::EnumeratedEmpty | Self::PartiallyEnumerated { .. }
        )
    }
}

/// Per-document-role counters for one institution (or the whole table).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct RoleCoverage {
    /// Denominator size for this role.
    pub expected: usize,
    pub unknown_scopes: usize,
    /// Items with all three evidence parts — the numerator of the acquisition rate.
    pub acquired: usize,
    /// Unacquired items by `acquisition_status` reason (plus `partial_evidence` for items
    /// with incomplete evidence and no explicit reason).
    pub unacquired: BTreeMap<String, usize>,
}

impl RoleCoverage {
    /// The acquisition rate, or `None` when the role has no denominator items. Never a
    /// NaN, never above 1.
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
    /// The table records what *this* enumeration round has attempted — registry-carried
    /// statuses (`preflight_states`) are not pre-seeded here; they reach the table the
    /// same way runtime results do, through `apply_discovery`. Likewise
    /// `unknown_denominators` starts empty: it marks a role whose denominator a manifest
    /// showed unverifiable, not a role that was simply never queried.
    pub fn for_denominator<'a>(entries: impl Iterator<Item = &'a DenomEntry>) -> Self {
        let mut rows = Vec::new();
        for e in entries {
            let mut exploration = BTreeMap::new();
            exploration.insert("disclosure_entry".into(), ExplorationState::Unqueried);
            exploration.insert("product_list".into(), ExplorationState::Unqueried);
            exploration.insert("documents".into(), ExplorationState::Unqueried);
            exploration.insert("notices".into(), ExplorationState::Unqueried);
            rows.push(InstitutionProgress {
                institution_id: e.row.insurer_id.clone(),
                kind: e.kind,
                exploration,
                items: Vec::new(),
                unknown_denominators: BTreeMap::new(),
            });
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
        let row = self
            .row_mut(&manifest.scope.institution_id)
            .ok_or("institution outside denominator")?;
        let state = super::enumerate::exploration_state_of(&manifest.termination);
        row.exploration
            .insert(manifest.scope.axis.clone(), state.clone());
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
            for role in DENOMINATOR_DOC_ROLES {
                if !manifest.scope.doc_roles.iter().any(|r| r == role.as_str()) {
                    continue;
                }
                if state.reached_evidence() {
                    row.unknown_denominators.remove(&role);
                } else {
                    row.unknown_denominators.insert(role, state.clone());
                }
                for item in row
                    .items
                    .iter_mut()
                    .filter(|i| i.doc_role == role && !i.is_acquired())
                {
                    item.unacquired = Some((status, reason.clone()));
                }
            }
            return Ok(());
        }
        if manifest.scope.axis != "product_list" {
            return Ok(());
        }
        if matches!(
            state,
            ExplorationState::Enumerated | ExplorationState::EnumeratedEmpty
        ) {
            row.unknown_denominators.clear();
        } else {
            for role in DENOMINATOR_DOC_ROLES {
                row.unknown_denominators.insert(role, state.clone());
            }
        }
        for id in &manifest.discovered_ids {
            for role in DENOMINATOR_DOC_ROLES {
                let item_id = format!("{id}:{}", role.as_str());
                if !row.items.iter().any(|item| item.item_id == item_id) {
                    row.items.push(DenominatorItem {
                        item_id,
                        doc_role: role,
                        evidence: AcquisitionEvidence::default(),
                        unacquired: Some((
                            AcquisitionStatus::Unqueried,
                            "document not acquired; product discovered".into(),
                        )),
                    });
                }
            }
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
