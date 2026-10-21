//! Private-zone identifier scan (K8 analogue of `chk_no_private_ids`).
//!
//! Public criteria data must never name a private-zone object. The DB trigger checks every
//! string in a row against `(^|[^a-z0-9_])(contract|person|upload|del|consent|assume):`
//! case-insensitively; this module applies the same rule to file JSON and to inserted models.
//! It is a prefix check, not a parser: a natural-language string that happens to contain the
//! same shape is refused too (the DB chose the false-positive side as well).

use crate::error::{CriteriaError, Result};
use serde::Serialize;
use serde_json::Value;

const PREFIXES: [&str; 6] = ["contract", "person", "upload", "del", "consent", "assume"];

/// Scan every string in `v` (object keys included).
pub fn check_value(v: &Value) -> Result<()> {
    match v {
        Value::String(s) => check_str(s),
        Value::Array(a) => a.iter().try_for_each(check_value),
        Value::Object(m) => m.iter().try_for_each(|(k, x)| {
            check_str(k)?;
            check_value(x)
        }),
        _ => Ok(()),
    }
}

/// Scan the serialized form of any model. Call this for programmatic inserts that
/// did not come through `load`'s file scan.
pub fn check_model<T: Serialize>(v: &T) -> Result<()> {
    check_value(&serde_json::to_value(v)?)
}

fn check_str(s: &str) -> Result<()> {
    let lower = s.to_lowercase();
    let bytes = lower.as_bytes();
    for p in PREFIXES {
        let needle = format!("{p}:");
        let mut from = 0;
        while let Some(off) = lower[from..].find(&needle) {
            let at = from + off;
            let boundary = at == 0 || !matches!(bytes[at - 1], b'a'..=b'z' | b'0'..=b'9' | b'_');
            if boundary {
                return Err(CriteriaError::PrivateId {
                    detail: format!("'{p}:' prefix in '{s}'"),
                });
            }
            from = at + needle.len();
        }
    }
    Ok(())
}
