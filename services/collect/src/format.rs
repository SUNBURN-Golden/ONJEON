//! Format validation for fetched responses (DATA_PIPELINE_CONTRACT §2: a download is a
//! temporary object until length·MIME·parse·hash checks pass; §8: a 200 that is a login HTML
//! page is not an acquisition). A failure never becomes an `objects/` original: it is
//! quarantined as evidence instead (`archive::put_quarantined`).

use serde::{Deserialize, Serialize};

/// The document format the caller expected the response to be.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ExpectedFormat {
    /// `%PDF-` at byte 0 (a text or scanned PDF alike).
    Pdf,
    /// First non-whitespace byte is `<` (HTML or XML documents, disclosure pages included).
    Html,
    /// Parses as JSON.
    Json,
    /// No magic check — only non-empty; for formats this stage does not parse.
    Binary,
}

impl ExpectedFormat {
    /// The string used in records and on the CLI (`--expected-format`).
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Pdf => "pdf",
            Self::Html => "html",
            Self::Json => "json",
            Self::Binary => "binary",
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "pdf" | "text_pdf" | "scanned_pdf" => Some(Self::Pdf),
            "html" | "xml" | "disclosure_page" => Some(Self::Html),
            "json" => Some(Self::Json),
            "binary" => Some(Self::Binary),
            _ => None,
        }
    }
}

/// Why a response failed validation (kept on the quarantine record).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FormatFailure {
    /// `empty` | `wrong_magic` | `not_parseable` | `declared_type_mismatch`
    pub reason: String,
    /// What the check saw (declared content type and the first bytes as hex), never the body.
    pub detail: String,
}

/// Validate `body` against `expected` and the declared `content_type`.
/// An empty body or a `text/html` body for a non-HTML expectation is a failure — the
/// "login page / error page saved as a PDF" case of §2 and §8.
pub fn check(
    expected: ExpectedFormat,
    content_type: &str,
    body: &[u8],
) -> Result<(), FormatFailure> {
    if body.is_empty() {
        return Err(FormatFailure {
            reason: "empty".into(),
            detail: format!("declared {content_type}, 0 bytes"),
        });
    }
    if expected != ExpectedFormat::Html
        && content_type.to_ascii_lowercase().starts_with("text/html")
    {
        return Err(FormatFailure {
            reason: "declared_type_mismatch".into(),
            detail: format!("declared text/html but expected {}", expected.as_str()),
        });
    }
    match expected {
        ExpectedFormat::Pdf if !body.starts_with(b"%PDF-") => Err(FormatFailure {
            reason: "wrong_magic".into(),
            detail: "expected PDF signature at offset 0".into(),
        }),
        ExpectedFormat::Html
            if !body
                .iter()
                .position(|b| !b.is_ascii_whitespace())
                .map(|i| body[i] == b'<')
                .unwrap_or(false) =>
        {
            Err(FormatFailure {
                reason: "wrong_magic".into(),
                detail: "first non-blank byte is not markup".into(),
            })
        }
        ExpectedFormat::Json if serde_json::from_slice::<serde_json::Value>(body).is_err() => {
            Err(FormatFailure {
                reason: "not_parseable".into(),
                detail: "body does not parse as JSON".into(),
            })
        }
        _ => Ok(()),
    }
}
