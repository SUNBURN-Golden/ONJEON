//! Release freezing and reading (K15), and the usage restriction that sits beside it.
//!
//! A release lists its members by id and fixes the hash of every rule file its claims point at; its
//! content hash covers both. `view` reads only listed members, so a claim added later never shows up in an
//! older release, and an in-place edit, a deletion or a swapped rule file is a K15 finding.
//! A `ReleaseNotice` is operational state outside the content: it never changes what `view` returns,
//! it only restricts new calculations through [`service_allowed`].

use crate::canon::{canonical_json, sha256_hex};
use crate::check::Violation;
use crate::error::{shape, OntologyError, Result};
use crate::model::{id_of, s, Abox, View, SECTIONS};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};

/// Member ids per section.
pub type Members = BTreeMap<String, Vec<String>>;

/// What `freeze` fixes about a release.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Freeze {
    pub members: Members,
    /// Rule file path → SHA-256 (`None` when the file is missing).
    pub rule_files: BTreeMap<String, Option<String>>,
    pub content_sha256: String,
    /// Rule edition of the input stage (membership, time, link checks) the release was calculated with.
    /// The reference fixes the hash over members and rule files only, so this field travels beside
    /// the hash and is not covered by it.
    pub input_stage_edition: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Release {
    pub id: String,
    pub frozen_at: Option<String>,
    pub note: Option<String>,
    pub freeze: Freeze,
}

impl Release {
    pub(crate) fn from_value(v: &Value) -> Result<Release> {
        let id = id_of(v)?.to_string();
        let mut members = Members::new();
        match v.get("members") {
            Some(Value::Object(m)) => {
                for (k, ids) in m {
                    let ids = ids
                        .as_array()
                        .ok_or_else(|| shape(format!("{id}: members.{k} must be an array")))?
                        .iter()
                        .filter_map(|x| x.as_str().map(str::to_string))
                        .collect();
                    members.insert(k.clone(), ids);
                }
            }
            _ => return Err(shape(format!("{id}: members missing"))),
        }
        let rule_files = match v.get("rule_files") {
            Some(Value::Object(m)) => m
                .iter()
                .map(|(k, h)| (k.clone(), h.as_str().map(str::to_string)))
                .collect(),
            _ => BTreeMap::new(),
        };
        Ok(Release {
            frozen_at: s(v, "frozen_at").map(str::to_string),
            note: s(v, "note").map(str::to_string),
            freeze: Freeze {
                members,
                rule_files,
                content_sha256: s(v, "content_sha256")
                    .ok_or_else(|| shape(format!("{id}: content_sha256 missing")))?
                    .to_string(),
                input_stage_edition: s(v, "input_stage_edition")
                    .or_else(|| s(v, "input_stage"))
                    .map(str::to_string),
            },
            id,
        })
    }
}

fn sorted_by_id(list: &[Value]) -> Vec<Value> {
    let mut l = list.to_vec();
    l.sort_by(|a, b| s(a, "id").unwrap_or("").cmp(s(b, "id").unwrap_or("")));
    l
}

fn select(a: &Abox, members: &Members) -> BTreeMap<String, Vec<Value>> {
    SECTIONS
        .iter()
        .map(|k| {
            let want: BTreeSet<&str> = members
                .get(*k)
                .map(|l| l.iter().map(String::as_str).collect())
                .unwrap_or_default();
            let picked: Vec<Value> = a
                .section(k)
                .iter()
                .filter(|x| s(x, "id").is_some_and(|i| want.contains(i)))
                .cloned()
                .collect();
            ((*k).to_string(), sorted_by_id(&picked))
        })
        .collect()
}

fn rule_hashes(a: &Abox, assertions: &[Value]) -> BTreeMap<String, Option<String>> {
    assertions
        .iter()
        .filter_map(|x| s(x, "rule_path"))
        .map(|p| (p.to_string(), a.rule_files.get(p).map(|b| sha256_hex(b))))
        .collect()
}

fn content_hash(
    sel: &BTreeMap<String, Vec<Value>>,
    rules: &BTreeMap<String, Option<String>>,
) -> Result<String> {
    let blob = json!({ "members": sel, "rule_files": rules });
    Ok(sha256_hex(canonical_json(&blob)?.as_bytes()))
}

/// Fixes `members` (ids per section) and the rule files their assertions name, and hashes their content.
pub fn freeze(a: &Abox, members: &Members, input_stage_edition: &str) -> Result<Freeze> {
    let sel = select(a, members);
    let rules = rule_hashes(a, &sel["assertions"]);
    let hash = content_hash(&sel, &rules)?;
    Ok(Freeze {
        members: SECTIONS
            .iter()
            .map(|k| {
                let mut ids = members.get(*k).cloned().unwrap_or_default();
                ids.sort();
                ((*k).to_string(), ids)
            })
            .collect(),
        rule_files: rules,
        content_sha256: hash,
        input_stage_edition: Some(input_stage_edition.to_string()),
    })
}

/// Release candidate: everything stored now. Nothing is frozen yet, so K15 is not checked.
pub fn candidate_view(a: &Abox) -> Result<View> {
    let raw = SECTIONS
        .iter()
        .map(|k| ((*k).to_string(), sorted_by_id(a.section(k))))
        .collect();
    View::build(raw, a, Vec::new())
}

/// What the frozen release `release_id` reads. Members outside the list are invisible; a missing member,
/// an in-place edit or a swapped rule file is reported in `integrity` as K15.
pub fn view(a: &Abox, release_id: &str) -> Result<View> {
    let rel = a
        .releases
        .iter()
        .find(|r| r.id == release_id)
        .ok_or_else(|| OntologyError::Unknown(format!("release {release_id}")))?;
    let sel = select(a, &rel.freeze.members);
    let mut integrity = Vec::new();
    for k in SECTIONS {
        let have: BTreeSet<&str> = sel[k].iter().filter_map(|x| s(x, "id")).collect();
        for mid in rel.freeze.members.get(k).into_iter().flatten() {
            if !have.contains(mid.as_str()) {
                integrity.push(Violation::new(
                    "K15",
                    mid,
                    format!("{release_id} 구성원이 저장소에 없음"),
                ));
            }
        }
    }
    let rules = rule_hashes(a, &sel["assertions"]);
    if rules != rel.freeze.rule_files {
        integrity.push(Violation::new(
            "K15",
            release_id,
            "규칙 파일 해시가 고정값과 다름",
        ));
    } else if content_hash(&sel, &rules)? != rel.freeze.content_sha256 {
        integrity.push(Violation::new(
            "K15",
            release_id,
            "구성원 내용이 제자리에서 바뀜(내용 해시 불일치)",
        ));
    }
    View::build(sel, a, integrity)
}

/// Operational restriction on a release (not release content). `state == "restricted"` blocks new calculations
/// for the listed coverages (and sales configurations, when listed) until it is lifted.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReleaseNotice {
    pub id: String,
    pub release: String,
    /// Affected coverages.
    #[serde(default)]
    pub affects: Vec<String>,
    /// Affected sales configurations (empty: not narrowed by configuration).
    #[serde(default)]
    pub affects_sales_configs: Vec<String>,
    pub state: String,
    pub reason: String,
    #[serde(default)]
    pub lifted_at: Option<String>,
}

impl ReleaseNotice {
    fn restricts(&self, release: &str, coverage: &str, sales_config: Option<&str>) -> bool {
        self.release == release
            && self.state == "restricted"
            && self.lifted_at.is_none()
            && self.affects.iter().any(|c| c == coverage)
            && (self.affects_sales_configs.is_empty()
                || sales_config.is_none_or(|sc| self.affects_sales_configs.iter().any(|x| x == sc)))
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NoticeHit {
    pub id: String,
    pub reason: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ServiceDecision {
    pub allowed: bool,
    pub notices: Vec<NoticeHit>,
}

/// May the service calculate `coverage` against `release` now? Reproduction of past results is a separate
/// matter (`view` always returns the same content); a restriction only stops new calculations.
pub fn service_allowed(
    release: &str,
    coverage: &str,
    notices: &[ReleaseNotice],
) -> ServiceDecision {
    service_allowed_for(release, coverage, None, notices)
}

/// Like [`service_allowed`], also narrowing by the sales configuration of the request.
pub fn service_allowed_for(
    release: &str,
    coverage: &str,
    sales_config: Option<&str>,
    notices: &[ReleaseNotice],
) -> ServiceDecision {
    let hits: Vec<NoticeHit> = notices
        .iter()
        .filter(|n| n.restricts(release, coverage, sales_config))
        .map(|n| NoticeHit {
            id: n.id.clone(),
            reason: n.reason.clone(),
        })
        .collect();
    ServiceDecision {
        allowed: hits.is_empty(),
        notices: hits,
    }
}
