//! Error type of the crate. Loading and lookups fail loudly; checks report [`crate::Violation`]s instead.

use std::fmt;

#[derive(Debug)]
pub enum OntologyError {
    Json(serde_json::Error),
    Io(std::io::Error),
    /// The document does not have the expected shape (message names the path).
    Shape(String),
    /// A referenced id does not exist in the snapshot.
    Unknown(String),
    /// A diagnosis code or code range is not in the KCD form `A00`, `A00.1`, `A00-A09`.
    BadCode(String),
}

pub type Result<T> = std::result::Result<T, OntologyError>;

impl fmt::Display for OntologyError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            OntologyError::Json(e) => write!(f, "json: {e}"),
            OntologyError::Io(e) => write!(f, "io: {e}"),
            OntologyError::Shape(m) => write!(f, "shape: {m}"),
            OntologyError::Unknown(m) => write!(f, "unknown: {m}"),
            OntologyError::BadCode(m) => write!(f, "bad code: {m}"),
        }
    }
}

impl std::error::Error for OntologyError {}

impl From<serde_json::Error> for OntologyError {
    fn from(e: serde_json::Error) -> Self {
        OntologyError::Json(e)
    }
}

impl From<std::io::Error> for OntologyError {
    fn from(e: std::io::Error) -> Self {
        OntologyError::Io(e)
    }
}

pub(crate) fn shape(msg: impl Into<String>) -> OntologyError {
    OntologyError::Shape(msg.into())
}
