//! In-memory default-candidate store: insertion-time validation, append-only
//! semantics (there is no update or delete), tip and superseded queries — the same
//! discipline as [`crate::store::CriterionStore`].
//!
//! A candidate version enters only with its candidate present, a canonical
//! `def:<slug>@<n>` id, a non-empty scope on its candidate, a required update
//! cycle, `applied == false` on the candidate, at least one source that is both a
//! `raw:sha256:` RawAsset reference and `evidence_kind = public_statistic`, ordered
//! valid dates, and a linear correction chain. Because no version can ever be
//! `applied`, [`DefaultsStore::for_service`] is always empty until T-KN-14's
//! application record exists.

use super::error::{DefaultsError, Result};
use super::model::{version_id, CandidateVersion, DefaultCandidate, ValueKind};
use crate::error::CriteriaError;
use crate::k8;
use crate::store::is_iso_date;
use onjeon_contracts::evidence_ref;
use onjeon_contracts::CriterionSourceKind;
use std::collections::BTreeMap;

/// A stored version resolved with its candidate.
pub struct CandidateVersionRef<'a> {
    pub candidate: &'a DefaultCandidate,
    pub version: &'a CandidateVersion,
}

#[derive(Debug, Default)]
pub struct DefaultsStore {
    candidates: BTreeMap<String, DefaultCandidate>,
    /// Version id → version.
    versions: BTreeMap<String, CandidateVersion>,
}

impl DefaultsStore {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn candidate(&self, id: &str) -> Option<&DefaultCandidate> {
        self.candidates.get(id)
    }

    pub fn version(&self, version_id: &str) -> Option<&CandidateVersion> {
        self.versions.get(version_id)
    }

    pub fn resolve(&self, version_id: &str) -> Option<CandidateVersionRef<'_>> {
        let v = self.versions.get(version_id)?;
        self.candidates
            .get(&v.candidate_id)
            .map(|c| CandidateVersionRef {
                candidate: c,
                version: v,
            })
    }

    pub fn candidates(&self) -> impl Iterator<Item = &DefaultCandidate> {
        self.candidates.values()
    }

    pub fn versions(&self) -> impl Iterator<Item = &CandidateVersion> {
        self.versions.values()
    }

    /// Versions of one candidate, ascending.
    pub fn versions_of<'a>(
        &'a self,
        candidate_id: &'a str,
    ) -> impl Iterator<Item = &'a CandidateVersion> + 'a {
        self.versions
            .values()
            .filter(move |v| v.candidate_id == candidate_id)
    }

    /// The current (highest-numbered) version of a candidate.
    pub fn tip<'a>(&'a self, candidate_id: &'a str) -> Option<&'a CandidateVersion> {
        self.versions_of(candidate_id).max_by_key(|v| v.version)
    }

    /// The tip version id of every candidate, sorted.
    pub fn tip_ids(&self) -> Vec<String> {
        let mut ids: Vec<String> = self
            .candidates
            .keys()
            .filter_map(|c| self.tip(c).map(|v| v.id.clone()))
            .collect();
        ids.sort();
        ids
    }

    /// Versions a service read may use: only those of `applied` candidates.
    /// `applied` can never be `true` in this store — the application record lives
    /// in T-KN-14 (`criteria_application`, D-08) — so this always yields nothing.
    /// It exists so the "후보는 표시되지 않는다" contract has an executable shape.
    pub fn for_service(&self) -> impl Iterator<Item = &CandidateVersion> + '_ {
        self.versions.values().filter(move |v| {
            self.candidates
                .get(&v.candidate_id)
                .is_some_and(|c| c.applied)
        })
    }

    /// `def:<slug>` shape.
    pub fn is_candidate_id(id: &str) -> bool {
        matches!(id.strip_prefix("def:"), Some(s) if is_slug(s))
    }

    /// Canonical `def:<slug>@<n>` shape (no leading zeros — digits of `n`).
    pub fn is_version_id(id: &str) -> bool {
        let Some((head, tail)) = id.rsplit_once('@') else {
            return false;
        };
        Self::is_candidate_id(head)
            && !tail.is_empty()
            && tail.bytes().all(|b| b.is_ascii_digit())
            && tail
                .parse::<u64>()
                .is_ok_and(|n| n >= 1 && n.to_string() == tail)
    }

    /// The candidate id embedded in a version id (`def:a@3` → `def:a`).
    pub fn candidate_of(version_id: &str) -> Option<String> {
        if !Self::is_version_id(version_id) {
            return None;
        }
        version_id.rsplit_once('@').map(|(h, _)| h.to_string())
    }

    pub fn insert_candidate(&mut self, c: DefaultCandidate) -> Result<()> {
        if !Self::is_candidate_id(&c.id) {
            return Err(CriteriaError::Id {
                what: "default candidate id",
                value: c.id.clone(),
                detail: "must match def:<slug> ([a-z0-9_-]+)".into(),
            }
            .into());
        }
        if c.label.trim().is_empty() {
            return Err(CriteriaError::EmptyField {
                what: "default candidate",
                id: c.id.clone(),
                field: "label",
            }
            .into());
        }
        check_scope(&c)?;
        if c.applied {
            return Err(DefaultsError::AppliedTrue {
                candidate_id: c.id.clone(),
            });
        }
        if !evidence_ref::is_rfc3339(&c.recorded_at) {
            return Err(CriteriaError::BadTime {
                version_id: c.id.clone(),
                field: "recorded_at",
                detail: "not RFC 3339".into(),
            }
            .into());
        }
        k8::check_model(&c)?;
        if self.candidates.contains_key(&c.id) {
            return Err(CriteriaError::Duplicate {
                what: "default candidate",
                id: c.id.clone(),
            }
            .into());
        }
        self.candidates.insert(c.id.clone(), c);
        Ok(())
    }

    pub fn insert_version(&mut self, v: CandidateVersion) -> Result<()> {
        check_version_shape(&v)?;
        if !self.candidates.contains_key(&v.candidate_id) {
            return Err(CriteriaError::UnknownCriterion {
                version_id: v.id.clone(),
            }
            .into());
        }
        if self.versions.contains_key(&v.id) {
            return Err(CriteriaError::Duplicate {
                what: "candidate version",
                id: v.id.clone(),
            }
            .into());
        }
        check_sources(&v)?;
        check_value(&v)?;
        check_times(&v)?;
        self.check_correction_chain(&v)?;
        k8::check_model(&v)?;
        self.versions.insert(v.id.clone(), v);
        Ok(())
    }

    /// Same linear chain rule as criteria: `version = 1` carries no `supersedes`;
    /// `version > 1` must supersede exactly `<candidate_id>@<version-1>`, and
    /// `supersedes`/`correction_reason` travel in pairs.
    fn check_correction_chain(&self, v: &CandidateVersion) -> Result<()> {
        let bad = |detail: &str| {
            Err(CriteriaError::Supersedes {
                version_id: v.id.clone(),
                detail: detail.to_string(),
            }
            .into())
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
        let want = version_id(&v.candidate_id, v.version - 1);
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

/// `def:` body characters (same slug alphabet as `crit:`).
fn is_slug(s: &str) -> bool {
    !s.is_empty()
        && s.bytes()
            .all(|b| matches!(b, b'a'..=b'z' | b'0'..=b'9' | b'_' | b'-'))
}

fn check_scope(c: &DefaultCandidate) -> Result<()> {
    let bad = |detail: &str| {
        Err(CriteriaError::Scope {
            criterion_id: c.id.clone(),
            detail: detail.to_string(),
        }
        .into())
    };
    for (name, list) in [
        ("situations", &c.scope.situations),
        ("subjects", &c.scope.subjects),
    ] {
        if list.is_empty() {
            return bad(&format!(
                "scope.{name} is empty; a candidate without an applicability range is never usable"
            ));
        }
        if list.iter().any(|x| x.trim().is_empty()) {
            return bad(&format!("scope.{name} holds an empty entry"));
        }
    }
    Ok(())
}

fn check_version_shape(v: &CandidateVersion) -> Result<()> {
    if !DefaultsStore::is_version_id(&v.id) {
        return Err(CriteriaError::Id {
            what: "candidate version id",
            value: v.id.clone(),
            detail: "must match def:<slug>@<n> (canonical, no leading zeros)".into(),
        }
        .into());
    }
    if !DefaultsStore::is_candidate_id(&v.candidate_id) {
        return Err(CriteriaError::Id {
            what: "default candidate id",
            value: v.candidate_id.clone(),
            detail: "must match def:<slug>".into(),
        }
        .into());
    }
    let want = version_id(&v.candidate_id, v.version);
    if v.id != want {
        return Err(CriteriaError::Id {
            what: "candidate version id",
            value: v.id.clone(),
            detail: format!("id must equal candidate_id@version ('{want}')"),
        }
        .into());
    }
    if v.version == 0 {
        return Err(CriteriaError::Id {
            what: "candidate version",
            value: v.id.clone(),
            detail: "version starts at 1".into(),
        }
        .into());
    }
    if v.rationale.trim().is_empty() {
        return Err(CriteriaError::EmptyField {
            what: "candidate version",
            id: v.id.clone(),
            field: "rationale",
        }
        .into());
    }
    Ok(())
}

/// Every source must be a `raw:sha256:` RawAsset reference AND a public statistic —
/// the "출처가 확정된 공공 통계만" rule as two executable checks.
fn check_sources(v: &CandidateVersion) -> Result<()> {
    if v.sources.is_empty() {
        return Err(CriteriaError::NoSource {
            version_id: v.id.clone(),
        }
        .into());
    }
    let mut seen = std::collections::BTreeSet::new();
    for s in &v.sources {
        if !seen.insert(s.ref_.clone()) {
            return Err(CriteriaError::DuplicateSource {
                version_id: v.id.clone(),
                ref_: s.ref_.clone(),
            }
            .into());
        }
        let parsed = evidence_ref::validate(&s.ref_).map_err(|e| {
            DefaultsError::Criteria(CriteriaError::BadSourceRef {
                version_id: v.id.clone(),
                ref_: s.ref_.clone(),
                detail: e.to_string(),
            })
        })?;
        if !matches!(parsed.kind(), evidence_ref::RefKind::Raw) {
            return Err(DefaultsError::SourceNotRawAsset {
                version_id: v.id.clone(),
                ref_: s.ref_.clone(),
            });
        }
        if s.evidence_kind != CriterionSourceKind::PublicStatistic {
            return Err(DefaultsError::SourceNotPublicStatistic {
                version_id: v.id.clone(),
                ref_: s.ref_.clone(),
                found: format!("{:?}", s.evidence_kind),
            });
        }
    }
    Ok(())
}

/// The stored statistic itself must be well-formed: a non-empty summary, the
/// fields `kind` requires, and none of the fields the other kinds use.
fn check_value(v: &CandidateVersion) -> Result<()> {
    let bad = |detail: &str| {
        Err(DefaultsError::BadValue {
            version_id: v.id.clone(),
            detail: detail.to_string(),
        })
    };
    let value = &v.value;
    if value.summary.trim().is_empty() {
        return bad("summary is empty; the reference-statistic label would have nothing to show");
    }
    let requires = |cond: bool, what: &str| -> Result<()> {
        if cond {
            Ok(())
        } else {
            bad(&format!("kind '{}' requires {what}", kind_str(value.kind)))
        }
    };
    // Fields that must stay empty for this kind; named for the error message.
    let extra: Vec<(&str, bool)> = match value.kind {
        ValueKind::MonetaryAmount => vec![
            ("rate_bp", value.rate_bp.is_some()),
            ("count", value.count.is_some()),
            ("unit", value.unit.is_some()),
            ("items", value.items.is_some()),
        ],
        ValueKind::Rate => vec![
            ("amount_krw", value.amount_krw.is_some()),
            ("period", value.period.is_some()),
            ("count", value.count.is_some()),
            ("unit", value.unit.is_some()),
            ("items", value.items.is_some()),
        ],
        ValueKind::Count => vec![
            ("amount_krw", value.amount_krw.is_some()),
            ("period", value.period.is_some()),
            ("rate_bp", value.rate_bp.is_some()),
            ("items", value.items.is_some()),
        ],
        ValueKind::Structure => vec![
            ("amount_krw", value.amount_krw.is_some()),
            ("period", value.period.is_some()),
            ("rate_bp", value.rate_bp.is_some()),
            ("count", value.count.is_some()),
            ("unit", value.unit.is_some()),
        ],
    };
    for (name, present) in extra {
        if present {
            return bad(&format!(
                "field '{name}' does not belong to kind '{}'",
                kind_str(value.kind)
            ));
        }
    }
    match value.kind {
        ValueKind::MonetaryAmount => {
            requires(value.amount_krw.is_some(), "amount_krw")?;
            requires(value.period.is_some(), "period")?;
        }
        ValueKind::Rate => {
            requires(value.rate_bp.is_some(), "rate_bp")?;
        }
        ValueKind::Count => {
            requires(value.count.is_some(), "count")?;
            match &value.unit {
                Some(u) if !u.trim().is_empty() => {}
                _ => return bad("kind 'count' requires a non-empty unit"),
            }
        }
        ValueKind::Structure => {
            let items = match &value.items {
                Some(items) if !items.is_empty() => items,
                _ => return bad("kind 'structure' requires at least one item"),
            };
            for (i, it) in items.iter().enumerate() {
                if it.label.trim().is_empty() {
                    return bad(&format!("structure item {i} has an empty label"));
                }
                if it.amount_krw.is_none() && it.rate_bp.is_none() && it.count.is_none() {
                    return bad(&format!(
                        "structure item {i} ('{}') carries no number",
                        it.label
                    ));
                }
            }
        }
    }
    Ok(())
}

fn kind_str(k: ValueKind) -> &'static str {
    match k {
        ValueKind::MonetaryAmount => "monetary_amount",
        ValueKind::Rate => "rate",
        ValueKind::Count => "count",
        ValueKind::Structure => "structure",
    }
}

fn check_times(v: &CandidateVersion) -> Result<()> {
    if !is_iso_date(&v.valid_from) {
        return Err(CriteriaError::BadTime {
            version_id: v.id.clone(),
            field: "valid_from",
            detail: "not a real YYYY-MM-DD date".into(),
        }
        .into());
    }
    if let Some(to) = &v.valid_to {
        if !is_iso_date(to) {
            return Err(CriteriaError::BadTime {
                version_id: v.id.clone(),
                field: "valid_to",
                detail: "not a real YYYY-MM-DD date".into(),
            }
            .into());
        }
        if to < &v.valid_from {
            return Err(CriteriaError::BadTime {
                version_id: v.id.clone(),
                field: "valid_to",
                detail: "before valid_from".into(),
            }
            .into());
        }
    }
    if !evidence_ref::is_rfc3339(&v.recorded_at) {
        return Err(CriteriaError::BadTime {
            version_id: v.id.clone(),
            field: "recorded_at",
            detail: "not RFC 3339".into(),
        }
        .into());
    }
    Ok(())
}
