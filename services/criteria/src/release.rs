//! Criteria releases (불변): the frozen list of criterion-version ids plus a content hash.
//!
//! A criteria release has its own id space `crel:<yyyymmdd>-<n>` — the knowledge release
//! `rel:` space is not shared (02_구현계약 §1.3: the knowledge release only references
//! `criteria_release_ref`). `freeze` snapshots the current tip versions; `verify` rebuilds
//! the content from the store and fails on a missing member or a changed hash (K15 analogue,
//! `ONJ-KN-S-052`).

use crate::canon::{canonical_json, sha256_hex};
use crate::error::{CriteriaError, IntegrityFinding, Result};
use crate::model::ReleaseMembers;
use crate::store::CriterionStore;
use onjeon_contracts::evidence_ref::is_rfc3339;
use onjeon_contracts::AssertionOrigin;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

/// `criteria_release` row/file shape (§1.5). Immutable once written.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CriteriaRelease {
    /// `crel:<yyyymmdd>-<n>` — separate from the knowledge `rel:` space.
    pub id: String,
    pub members: ReleaseMembers,
    /// SHA-256 of the canonical JSON `{"members": [...sorted ids], "content": {id: row}}`.
    pub content_sha256: String,
    /// RFC 3339.
    pub frozen_at: String,
}

/// `crel:<yyyymmdd>-<n>`.
pub fn is_release_id(id: &str) -> bool {
    let Some(rest) = id.strip_prefix("crel:") else {
        return false;
    };
    let Some((d, n)) = rest.split_once('-') else {
        return false;
    };
    d.len() == 8
        && d.bytes().all(|b| b.is_ascii_digit())
        && !n.is_empty()
        && n.bytes().all(|b| b.is_ascii_digit())
}

/// Canonical content of one member: its criterion row, version row and sources.
fn member_content(store: &CriterionStore, version_id: &str) -> Result<Value> {
    let Some(r) = store.resolve(version_id) else {
        return Err(CriteriaError::Shape(format!(
            "member '{version_id}' is not in the store"
        )));
    };
    let mut v = serde_json::to_value(r.version)?;
    // `id`/`criterion_id` are derivable; keep them for the hash so an in-place edit is caught.
    v["criterion"] = serde_json::to_value(r.criterion)?;
    Ok(v)
}

fn content_hash(
    store: &CriterionStore,
    member_ids: &[String],
) -> Result<(String, serde_json::Map<String, Value>)> {
    let mut ids = member_ids.to_vec();
    ids.sort();
    ids.dedup();
    let mut content = serde_json::Map::new();
    for id in &ids {
        content.insert(id.clone(), member_content(store, id)?);
    }
    let blob = json!({ "members": ids, "content": content });
    let hash = sha256_hex(canonical_json(&blob)?.as_bytes());
    Ok((hash, content))
}

/// Freeze the current tips into a release. Member list = every criterion's tip version,
/// sorted. A version without sources or with `origin=fixture` cannot enter
/// (`ONJ-KN-S-050` for the fixture case).
pub fn freeze(
    store: &CriterionStore,
    release_id: &str,
    frozen_at: &str,
) -> Result<CriteriaRelease> {
    if !is_release_id(release_id) {
        return Err(CriteriaError::BadReleaseId {
            id: release_id.to_string(),
        });
    }
    if !is_rfc3339(frozen_at) {
        return Err(CriteriaError::BadTime {
            version_id: release_id.to_string(),
            field: "frozen_at",
            detail: "not RFC 3339".into(),
        });
    }
    let member_ids = store.tip_ids();
    for id in &member_ids {
        let v = store
            .version(id)
            .expect("tip_ids only lists stored versions");
        if v.sources.is_empty() {
            return Err(CriteriaError::NoSource {
                version_id: id.clone(),
            });
        }
        if v.origin != AssertionOrigin::Pipeline {
            return Err(CriteriaError::FixtureInRelease {
                version_id: id.clone(),
            });
        }
    }
    let (content_sha256, _) = content_hash(store, &member_ids)?;
    Ok(CriteriaRelease {
        id: release_id.to_string(),
        members: ReleaseMembers {
            criterion_versions: member_ids,
        },
        content_sha256,
        frozen_at: frozen_at.to_string(),
    })
}

/// Reproduce a frozen release against the store. Every listed member must still exist and
/// the recomputed hash must match. Members not listed stay invisible — a release reads
/// only its member list (same rule as the knowledge release).
pub fn verify(store: &CriterionStore, release: &CriteriaRelease) -> Result<()> {
    let mut findings = Vec::new();
    for id in &release.members.criterion_versions {
        if store.version(id).is_none() {
            findings.push(IntegrityFinding {
                kind: "missing_member",
                member_id: id.clone(),
                detail: "구성원이 저장소에 없음".into(),
            });
        }
    }
    if findings.is_empty() {
        let (hash, _) = content_hash(store, &release.members.criterion_versions)?;
        if hash != release.content_sha256 {
            findings.push(IntegrityFinding {
                kind: "hash_mismatch",
                member_id: release.id.clone(),
                detail: "구성원 내용이 제자리에서 바뀜(내용 해시 불일치)".into(),
            });
        }
    }
    if findings.is_empty() {
        Ok(())
    } else {
        Err(CriteriaError::ReleaseIntegrity {
            release_id: release.id.clone(),
            findings,
        })
    }
}
