//! Error type for the criteria zone. Two variants carry the contract error codes
//! (`ONJ-KN-S-050` fixture data in a release, `ONJ-KN-S-052` frozen-release integrity).
//! Plain load/validation problems stay descriptive — the API error table has no
//! code for them yet.

use std::fmt;

/// `ONJ-KN-S-050`: fixture-only or `origin=fixture` material must not enter a release.
pub const CODE_FIXTURE_IN_RELEASE: &str = "ONJ-KN-S-050";
/// `ONJ-KN-S-052`: a frozen release's member is missing or its content changed.
pub const CODE_RELEASE_INTEGRITY: &str = "ONJ-KN-S-052";

/// A frozen-release integrity finding (K15 analogue): the release was read back and
/// a listed member could not be reproduced.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IntegrityFinding {
    /// `missing_member` | `content_changed` | `hash_mismatch`.
    pub kind: &'static str,
    pub member_id: String,
    pub detail: String,
}

#[derive(Debug)]
pub enum CriteriaError {
    /// Malformed identifier or an id that does not match its parts.
    Id {
        what: &'static str,
        value: String,
        detail: String,
    },
    /// The same id was inserted twice.
    Duplicate {
        what: &'static str,
        id: String,
    },
    /// A version was added for a criterion the store does not have.
    UnknownCriterion {
        version_id: String,
    },
    /// `scope.situations`/`scope.subjects` missing, empty or holding an empty entry.
    Scope {
        criterion_id: String,
        detail: String,
    },
    /// A criterion version without sources. Such a version cannot be stored and
    /// can never enter a criteria release (§1.5 "출처 없는 판은 기준 릴리스에 들어가지 못한다").
    NoSource {
        version_id: String,
    },
    /// A duplicate source ref inside one version (PK is (version, ref)).
    DuplicateSource {
        version_id: String,
        ref_: String,
    },
    /// A source ref that is not `raw:`/`clause:`/`obs:` evidence-ref grammar.
    BadSourceRef {
        version_id: String,
        ref_: String,
        detail: String,
    },
    /// `valid_from`/`valid_to`/`recorded_at`/`frozen_at` is not a real date/datetime,
    /// or `valid_to` is before `valid_from`.
    BadTime {
        version_id: String,
        field: &'static str,
        detail: String,
    },
    /// Correction chain broken: `version > 1` without `supersedes`, `supersedes` that does
    /// not point at the directly previous version of the same criterion, `version 1` with
    /// `supersedes`, or `correction_reason`/`supersedes` present alone.
    Supersedes {
        version_id: String,
        detail: String,
    },
    /// Empty `label`/`rationale`.
    EmptyField {
        what: &'static str,
        id: String,
        field: &'static str,
    },
    /// A private-zone identifier prefix (`contract:`/`person:`/`upload:`/`del:`/`consent:`/`assume:`)
    /// appeared in public criteria data (K8 analogue of `chk_no_private_ids`).
    PrivateId {
        detail: String,
    },
    /// A `default`/`defaults`/`default_*` key in a criterion file. Need-amount defaults are not
    /// criterion versions: candidates live in `data/criteria/defaults/` (T-KN-13) and can only be
    /// served behind the application record (T-KN-14, D-08). Without that record they are refused.
    DefaultOutsideGate {
        key: String,
        detail: String,
    },
    /// `origin=fixture` version offered to [`crate::release::freeze`] (`ONJ-KN-S-050`).
    FixtureInRelease {
        version_id: String,
    },
    /// Release id that is not `crel:<yyyymmdd>-<n>` (criteria releases do not share the `rel:` space).
    BadReleaseId {
        id: String,
    },
    /// [`crate::release::verify`] reproduced something different from the frozen hash
    /// (`ONJ-KN-S-052`).
    ReleaseIntegrity {
        release_id: String,
        findings: Vec<IntegrityFinding>,
    },
    /// File/JSON shape problem (serde, missing object, unknown field).
    Shape(String),
    Io(std::io::Error),
}

impl fmt::Display for IntegrityFinding {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{} {}: {}", self.kind, self.member_id, self.detail)
    }
}

impl fmt::Display for CriteriaError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        use CriteriaError::*;
        match self {
            Id { what, value, detail } => write!(f, "invalid {what} '{value}': {detail}"),
            Duplicate { what, id } => write!(f, "duplicate {what} '{id}'"),
            UnknownCriterion { version_id } => {
                write!(f, "version '{version_id}' names a criterion that is not stored")
            }
            Scope { criterion_id, detail } => {
                write!(f, "criterion '{criterion_id}' scope: {detail}")
            }
            NoSource { version_id } => write!(
                f,
                "criterion version '{version_id}' has no source; a version without sources cannot enter a release"
            ),
            DuplicateSource { version_id, ref_ } => {
                write!(f, "criterion version '{version_id}' repeats source '{ref_}'")
            }
            BadSourceRef { version_id, ref_, detail } => {
                write!(f, "source '{ref_}' of '{version_id}': {detail}")
            }
            BadTime { version_id, field, detail } => {
                write!(f, "'{version_id}' {field}: {detail}")
            }
            Supersedes { version_id, detail } => {
                write!(f, "correction chain of '{version_id}': {detail}")
            }
            EmptyField { what, id, field } => {
                write!(f, "{what} '{id}' has an empty {field}")
            }
            PrivateId { detail } => write!(f, "private identifier in public criteria data: {detail}"),
            DefaultOutsideGate { key, detail } => write!(
                f,
                "'{key}' is a need-amount default, not a criterion version: {detail} \
                 (defaults belong to data/criteria/defaults/ via the T-KN-13 loader and need the \
                 D-08 application record of T-KN-14 before service use)"
            ),
            FixtureInRelease { version_id } => write!(
                f,
                "{CODE_FIXTURE_IN_RELEASE}: fixture version '{version_id}' cannot enter a criteria release"
            ),
            BadReleaseId { id } => write!(
                f,
                "criteria release id '{id}' must match crel:<yyyymmdd>-<n>; the rel: space belongs to knowledge releases"
            ),
            ReleaseIntegrity { release_id, findings } => write!(
                f,
                "{CODE_RELEASE_INTEGRITY}: release '{release_id}' integrity failed ({} finding(s)): {}",
                findings.len(),
                findings
                    .iter()
                    .map(|x| x.to_string())
                    .collect::<Vec<_>>()
                    .join("; ")
            ),
            Shape(s) => write!(f, "{s}"),
            Io(e) => write!(f, "io: {e}"),
        }
    }
}

impl std::error::Error for CriteriaError {}

impl From<std::io::Error> for CriteriaError {
    fn from(e: std::io::Error) -> Self {
        CriteriaError::Io(e)
    }
}

impl From<serde_json::Error> for CriteriaError {
    fn from(e: serde_json::Error) -> Self {
        CriteriaError::Shape(e.to_string())
    }
}

pub type Result<T> = std::result::Result<T, CriteriaError>;
