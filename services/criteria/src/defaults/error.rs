//! Error type for default-candidate loading. Shared rules (ids, scope, sources
//! count, dates, correction chain, K8) reuse [`crate::error::CriteriaError`] so the
//! defaults path enforces exactly the criterion rules; the defaults-only rules get
//! their own variants here.

use crate::error::CriteriaError;
use std::fmt;

#[derive(Debug)]
pub enum DefaultsError {
    /// `applied: true` in a candidate file. Candidates are stored as `applied=false`
    /// only: applying needs a `criteria_application` record (T-KN-14, D-08), which
    /// this task cannot produce.
    AppliedTrue {
        candidate_id: String,
    },
    /// A candidate source whose `evidence_kind` is not `public_statistic`. Only
    /// confirmed public statistics may back a default candidate (§1.5 기본값 행).
    SourceNotPublicStatistic {
        version_id: String,
        ref_: String,
        found: String,
    },
    /// A candidate source that is not a `raw:sha256:` RawAsset reference — the
    /// "확정된" (hash-pinned) source form this task's output contract requires.
    SourceNotRawAsset {
        version_id: String,
        ref_: String,
    },
    /// A stored value violates its own contract (empty summary, empty structure
    /// items, a structure item carrying no number).
    BadValue {
        version_id: String,
        detail: String,
    },
    /// Shared criterion rules (id grammar, scope, sources, times, correction
    /// chain, K8, shape/io plumbing) raised by the criteria checks this module
    /// reuses.
    Criteria(CriteriaError),
    /// File/JSON shape problem before validation.
    Shape(String),
    Io(std::io::Error),
}

impl fmt::Display for DefaultsError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        use DefaultsError::*;
        match self {
            AppliedTrue { candidate_id } => write!(
                f,
                "default candidate '{candidate_id}' has applied=true; candidates are stored \
                 applied=false until a criteria_application record exists (T-KN-14, D-08)"
            ),
            SourceNotPublicStatistic { version_id, ref_, found } => write!(
                f,
                "source '{ref_}' of '{version_id}' has evidence_kind '{found}', not \
                 'public_statistic'; default candidates may rest on confirmed public statistics only"
            ),
            SourceNotRawAsset { version_id, ref_ } => write!(
                f,
                "source '{ref_}' of '{version_id}' is not a raw:sha256: RawAsset reference; \
                 a candidate's source must be the hash of the archived statistic"
            ),
            BadValue { version_id, detail } => write!(f, "value of '{version_id}': {detail}"),
            Criteria(e) => write!(f, "{e}"),
            Shape(s) => write!(f, "{s}"),
            Io(e) => write!(f, "io: {e}"),
        }
    }
}

impl std::error::Error for DefaultsError {}

impl From<CriteriaError> for DefaultsError {
    fn from(e: CriteriaError) -> Self {
        DefaultsError::Criteria(e)
    }
}

impl From<std::io::Error> for DefaultsError {
    fn from(e: std::io::Error) -> Self {
        DefaultsError::Io(e)
    }
}

impl From<serde_json::Error> for DefaultsError {
    fn from(e: serde_json::Error) -> Self {
        DefaultsError::Shape(e.to_string())
    }
}

pub type Result<T> = std::result::Result<T, DefaultsError>;
