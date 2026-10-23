//! Change lists: which criterion versions differ between two releases (or between a
//! release and the current tips). This is the input that lets a consumer find the
//! conclusions a correction affects — `conclusion_dependency.deps.criteria` holds
//! version ids, and [`ChangeList::affected_version_ids`] is exactly the set of ids
//! whose dependents must be marked stale (§1.5 정정 영향).

use crate::model::CriterionVersion;
use crate::release::CriteriaRelease;
use crate::store::CriterionStore;
use onjeon_contracts::CorrectionReason;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ChangeKind {
    /// The criterion entered the release.
    Added,
    /// A new version superseded the one the previous release read.
    Corrected,
    /// The release no longer reads this criterion (the criterion itself is never deleted —
    /// dependents lose their basis and must be revisited).
    Removed,
}

/// One criterion's change between two releases.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CriterionChange {
    pub criterion_id: String,
    pub kind: ChangeKind,
    /// Version id the older release read (`added` → none).
    pub before: Option<String>,
    /// Version id the newer release reads (`removed` → none).
    pub after: Option<String>,
    /// Why the `after` version exists (from its `correction_reason`), when it corrects an earlier 판.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub correction_reason: Option<CorrectionReason>,
}

/// The change list 영역 C hands to the personal zone and the service composition
/// (전체_구조_1차_정리 영역 C의 "판단 기준 변경 목록").
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ChangeList {
    pub from_release: Option<String>,
    pub to_release: Option<String>,
    pub entries: Vec<CriterionChange>,
}

impl ChangeList {
    /// Version ids whose dependents must be marked stale: the `before` side of every
    /// corrected or removed entry. These are the ids a consumer looks up in
    /// `conclusion_dependency.deps.criteria`.
    pub fn affected_version_ids(&self) -> Vec<String> {
        self.entries
            .iter()
            .filter_map(|e| e.before.clone())
            .collect()
    }
}

fn as_map(member_ids: &[String]) -> BTreeMap<String, String> {
    member_ids
        .iter()
        .filter_map(|id| CriterionStore::criterion_of(id).map(|c| (c, id.clone())))
        .collect()
}

fn diff(
    from: &BTreeMap<String, String>,
    to: &BTreeMap<String, String>,
    store: Option<&CriterionStore>,
    from_release: Option<String>,
    to_release: Option<String>,
) -> ChangeList {
    let mut entries = Vec::new();
    for (cid, after_id) in to {
        match from.get(cid) {
            None => entries.push(CriterionChange {
                criterion_id: cid.clone(),
                kind: ChangeKind::Added,
                before: None,
                after: Some(after_id.clone()),
                correction_reason: None,
            }),
            Some(before_id) if before_id != after_id => {
                let new_v: Option<&CriterionVersion> = store.and_then(|s| s.version(after_id));
                entries.push(CriterionChange {
                    criterion_id: cid.clone(),
                    kind: ChangeKind::Corrected,
                    before: Some(before_id.clone()),
                    after: Some(after_id.clone()),
                    correction_reason: new_v.and_then(|v| v.correction_reason),
                });
            }
            _ => {}
        }
    }
    for (cid, before_id) in from {
        if !to.contains_key(cid) {
            entries.push(CriterionChange {
                criterion_id: cid.clone(),
                kind: ChangeKind::Removed,
                before: Some(before_id.clone()),
                after: None,
                correction_reason: None,
            });
        }
    }
    entries.sort_by(|a, b| a.criterion_id.cmp(&b.criterion_id));
    ChangeList {
        from_release,
        to_release,
        entries,
    }
}

/// What changed between two frozen releases.
pub fn diff_releases(
    old: &CriteriaRelease,
    new: &CriteriaRelease,
    store: Option<&CriterionStore>,
) -> ChangeList {
    diff(
        &as_map(&old.members.criterion_versions),
        &as_map(&new.members.criterion_versions),
        store,
        Some(old.id.clone()),
        Some(new.id.clone()),
    )
}

/// What changed since a release was frozen — the live correction signal the personal
/// zone consumes (a member superseded after the release, a new criterion, one dropped
/// from the tips).
pub fn diff_to_tips(store: &CriterionStore, old: &CriteriaRelease) -> ChangeList {
    let tips: Vec<String> = store.tip_ids();
    diff(
        &as_map(&old.members.criterion_versions),
        &as_map(&tips),
        Some(store),
        Some(old.id.clone()),
        None,
    )
}
