//! In-memory criterion store: insertion-time validation matching the DB constraints,
//! append-only semantics (there is no update or delete), tip and superseded queries.
//!
//! A version enters only with its criterion present, a canonical `crit:<slug>@<n>` id,
//! at least one `raw:`/`clause:`/`obs:` source with a vocabulary evidence kind, a
//! non-empty scope on its criterion, ordered valid dates, and a linear correction
//! chain (`supersedes` must be the directly previous version of the same criterion,
//! paired with `correction_reason`).

use crate::error::{CriteriaError, Result};
use crate::k8;
use crate::model::{version_id, Criterion, CriterionVersion};
use onjeon_contracts::evidence_ref;
use std::collections::BTreeMap;

/// A stored version resolved with its criterion.
pub struct VersionRef<'a> {
    pub criterion: &'a Criterion,
    pub version: &'a CriterionVersion,
}

#[derive(Debug, Default)]
pub struct CriterionStore {
    criteria: BTreeMap<String, Criterion>,
    /// Version id → version. Insertion order is irrelevant; ids sort canonically.
    versions: BTreeMap<String, CriterionVersion>,
}

impl CriterionStore {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn criterion(&self, id: &str) -> Option<&Criterion> {
        self.criteria.get(id)
    }

    pub fn version(&self, version_id: &str) -> Option<&CriterionVersion> {
        self.versions.get(version_id)
    }

    pub fn resolve(&self, version_id: &str) -> Option<VersionRef<'_>> {
        let v = self.versions.get(version_id)?;
        self.criteria.get(&v.criterion_id).map(|c| VersionRef {
            criterion: c,
            version: v,
        })
    }

    pub fn criteria(&self) -> impl Iterator<Item = &Criterion> {
        self.criteria.values()
    }

    pub fn versions(&self) -> impl Iterator<Item = &CriterionVersion> {
        self.versions.values()
    }

    /// Versions of one criterion, ascending.
    pub fn versions_of<'a>(
        &'a self,
        criterion_id: &'a str,
    ) -> impl Iterator<Item = &'a CriterionVersion> + 'a {
        self.versions
            .values()
            .filter(move |v| v.criterion_id == criterion_id)
    }

    /// The current (highest-numbered) version of a criterion.
    pub fn tip<'a>(&'a self, criterion_id: &'a str) -> Option<&'a CriterionVersion> {
        self.versions_of(criterion_id).max_by_key(|v| v.version)
    }

    /// Tip version ids of every criterion, sorted — the member list of a new release.
    pub fn tip_ids(&self) -> Vec<String> {
        let mut ids: Vec<String> = self
            .criteria
            .keys()
            .filter_map(|c| self.tip(c).map(|v| v.id.clone()))
            .collect();
        ids.sort();
        ids
    }

    /// Version ids that a newer version of the same criterion supersedes —
    /// the ids consumers look up in `conclusion_dependency.deps.criteria` to mark
    /// stored results stale when a correction lands (§1.5 정정 영향).
    pub fn superseded_ids(&self) -> Vec<String> {
        let mut ids: Vec<String> = self
            .versions
            .values()
            .filter_map(|v| v.supersedes.clone())
            .collect();
        ids.sort();
        ids.dedup();
        ids
    }

    /// `crit:<slug>` shape.
    pub fn is_criterion_id(id: &str) -> bool {
        matches!(id.strip_prefix("crit:"), Some(s) if is_slug(s))
    }

    /// Canonical `crit:<slug>@<n>` shape (grammar of evidence_ref's criterion_ref).
    pub fn is_version_id(id: &str) -> bool {
        matches!(
            evidence_ref::parse(id),
            Ok(evidence_ref::ParsedRef::Criterion(_))
        )
    }

    /// The criterion id embedded in a version id (`crit:a@3` → `crit:a`).
    pub fn criterion_of(version_id: &str) -> Option<String> {
        match evidence_ref::parse(version_id) {
            Ok(evidence_ref::ParsedRef::Criterion(p)) => Some(format!("crit:{}", p.slug)),
            _ => None,
        }
    }

    pub fn insert_criterion(&mut self, c: Criterion) -> Result<()> {
        if !Self::is_criterion_id(&c.id) {
            return Err(CriteriaError::Id {
                what: "criterion id",
                value: c.id.clone(),
                detail: "must match crit:<slug> ([a-z0-9_-]+)".into(),
            });
        }
        if c.label.trim().is_empty() {
            return Err(CriteriaError::EmptyField {
                what: "criterion",
                id: c.id.clone(),
                field: "label",
            });
        }
        check_scope(&c)?;
        if !evidence_ref::is_rfc3339(&c.recorded_at) {
            return Err(CriteriaError::BadTime {
                version_id: c.id.clone(),
                field: "recorded_at",
                detail: "not RFC 3339".into(),
            });
        }
        k8::check_model(&c)?;
        if self.criteria.contains_key(&c.id) {
            return Err(CriteriaError::Duplicate {
                what: "criterion",
                id: c.id.clone(),
            });
        }
        self.criteria.insert(c.id.clone(), c);
        Ok(())
    }

    pub fn insert_version(&mut self, v: CriterionVersion) -> Result<()> {
        check_version_shape(&v)?;
        if !self.criteria.contains_key(&v.criterion_id) {
            return Err(CriteriaError::UnknownCriterion {
                version_id: v.id.clone(),
            });
        }
        if self.versions.contains_key(&v.id) {
            return Err(CriteriaError::Duplicate {
                what: "criterion version",
                id: v.id.clone(),
            });
        }
        check_sources(&v)?;
        check_times(&v)?;
        self.check_correction_chain(&v)?;
        k8::check_model(&v)?;
        self.versions.insert(v.id.clone(), v);
        Ok(())
    }

    /// Correction rules (DB `version_guard` + `chk_criterion_correction`, plus the SQL
    /// comment's "바로 이전 판" — this loader is narrower than the DB on purpose):
    /// `version = 1` carries no `supersedes`; `version > 1` must supersede exactly
    /// `<criterion_id>@<version-1>`, and `supersedes`/`correction_reason` travel in pairs.
    fn check_correction_chain(&self, v: &CriterionVersion) -> Result<()> {
        let bad = |detail: &str| {
            Err(CriteriaError::Supersedes {
                version_id: v.id.clone(),
                detail: detail.to_string(),
            })
        };
        match (&v.supersedes, &v.correction_reason) {
            (Some(_), None) => return bad("supersedes without correction_reason"),
            (None, Some(_)) => return bad("correction_reason without supersedes"),
            _ => {}
        }
        if v.version == 1 {
            return if v.supersedes.is_some() {
                bad("version 1 must not supersede")
            } else {
                Ok(())
            };
        }
        let Some(prev) = &v.supersedes else {
            return bad("version > 1 must supersede the previous version");
        };
        let want = version_id(&v.criterion_id, v.version - 1);
        if *prev != want {
            return bad(&format!(
                "supersedes must be '{want}' (the directly previous version), got '{prev}'"
            ));
        }
        if !self.versions.contains_key(prev) {
            return bad(&format!("superseded version '{prev}' is not stored"));
        }
        Ok(())
    }
}

/// `crit:` body characters.
fn is_slug(s: &str) -> bool {
    !s.is_empty()
        && s.bytes()
            .all(|b| matches!(b, b'a'..=b'z' | b'0'..=b'9' | b'_' | b'-'))
}

fn check_scope(c: &Criterion) -> Result<()> {
    let bad = |detail: &str| {
        Err(CriteriaError::Scope {
            criterion_id: c.id.clone(),
            detail: detail.to_string(),
        })
    };
    for (name, list) in [
        ("situations", &c.scope.situations),
        ("subjects", &c.scope.subjects),
    ] {
        if list.is_empty() {
            return bad(&format!(
                "scope.{name} is empty; a criterion without an applicability range is never usable"
            ));
        }
        if list.iter().any(|x| x.trim().is_empty()) {
            return bad(&format!("scope.{name} holds an empty entry"));
        }
    }
    Ok(())
}

/// Shape checks that need no store state.
fn check_version_shape(v: &CriterionVersion) -> Result<()> {
    if !CriterionStore::is_version_id(&v.id) {
        return Err(CriteriaError::Id {
            what: "criterion version id",
            value: v.id.clone(),
            detail: "must match crit:<slug>@<n> (canonical, no leading zeros)".into(),
        });
    }
    if !CriterionStore::is_criterion_id(&v.criterion_id) {
        return Err(CriteriaError::Id {
            what: "criterion id",
            value: v.criterion_id.clone(),
            detail: "must match crit:<slug>".into(),
        });
    }
    let want = version_id(&v.criterion_id, v.version);
    if v.id != want {
        return Err(CriteriaError::Id {
            what: "criterion version id",
            value: v.id.clone(),
            detail: format!("id must equal criterion_id@version ('{want}')"),
        });
    }
    if v.version == 0 {
        return Err(CriteriaError::Id {
            what: "criterion version",
            value: v.id.clone(),
            detail: "version starts at 1".into(),
        });
    }
    if v.rationale.trim().is_empty() {
        return Err(CriteriaError::EmptyField {
            what: "criterion version",
            id: v.id.clone(),
            field: "rationale",
        });
    }
    Ok(())
}

fn check_sources(v: &CriterionVersion) -> Result<()> {
    if v.sources.is_empty() {
        return Err(CriteriaError::NoSource {
            version_id: v.id.clone(),
        });
    }
    let mut seen = std::collections::BTreeSet::new();
    for s in &v.sources {
        if !seen.insert(s.ref_.clone()) {
            return Err(CriteriaError::DuplicateSource {
                version_id: v.id.clone(),
                ref_: s.ref_.clone(),
            });
        }
        // The contract grammar for a criterion source is raw: | clause: | url observation.
        let detail = match evidence_ref::validate(&s.ref_) {
            Ok(p) => match p.kind() {
                evidence_ref::RefKind::Raw
                | evidence_ref::RefKind::Clause
                | evidence_ref::RefKind::Observation => None,
                other => Some(format!(
                    "ref kind {other:?} is not one of raw:/clause:/obs:"
                )),
            },
            Err(e) => Some(e.to_string()),
        };
        if let Some(detail) = detail {
            return Err(CriteriaError::BadSourceRef {
                version_id: v.id.clone(),
                ref_: s.ref_.clone(),
                detail,
            });
        }
    }
    Ok(())
}

fn check_times(v: &CriterionVersion) -> Result<()> {
    if !is_iso_date(&v.valid_from) {
        return Err(CriteriaError::BadTime {
            version_id: v.id.clone(),
            field: "valid_from",
            detail: "not a real YYYY-MM-DD date".into(),
        });
    }
    if let Some(to) = &v.valid_to {
        if !is_iso_date(to) {
            return Err(CriteriaError::BadTime {
                version_id: v.id.clone(),
                field: "valid_to",
                detail: "not a real YYYY-MM-DD date".into(),
            });
        }
        if to < &v.valid_from {
            return Err(CriteriaError::BadTime {
                version_id: v.id.clone(),
                field: "valid_to",
                detail: "before valid_from".into(),
            });
        }
    }
    if !evidence_ref::is_rfc3339(&v.recorded_at) {
        return Err(CriteriaError::BadTime {
            version_id: v.id.clone(),
            field: "recorded_at",
            detail: "not RFC 3339".into(),
        });
    }
    Ok(())
}

/// `YYYY-MM-DD`, real calendar date (ISO dates compare correctly as strings).
pub fn is_iso_date(s: &str) -> bool {
    let d: Vec<&str> = s.split('-').collect();
    let [y, m, day] = match d.as_slice() {
        [y, m, d] if y.len() == 4 && m.len() == 2 && d.len() == 2 => [y, m, d],
        _ => return false,
    };
    let (Some(y), Some(m), Some(day)) = (num(y), num(m), num(day)) else {
        return false;
    };
    if !(1..=12).contains(&m) {
        return false;
    }
    let leap = (y % 4 == 0 && y % 100 != 0) || y % 400 == 0;
    let dim = match m {
        2 if leap => 29,
        2 => 28,
        4 | 6 | 9 | 11 => 30,
        _ => 31,
    };
    (1..=dim).contains(&day)
}

fn num(s: &str) -> Option<u32> {
    (!s.is_empty() && s.bytes().all(|b| b.is_ascii_digit())).then(|| s.parse().ok())?
}
