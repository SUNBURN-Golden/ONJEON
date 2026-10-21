//! Canonical JSON and SHA-256 for the criteria release content hash.
//!
//! Object keys are sorted explicitly, output is compact, and non-ASCII text is written as is.
//! Floats are rejected: a hash that depends on float formatting is not reproducible, and the
//! criteria store has none. Same rules as the knowledge release hash (`packages/ontology`);
//! duplicated here because zone rules allow `services/criteria` to depend on contracts only.

use crate::error::{CriteriaError, Result};
use serde_json::Value;
use sha2::{Digest, Sha256};

pub fn canonical_json(v: &Value) -> Result<String> {
    let mut out = String::new();
    write(v, &mut out)?;
    Ok(out)
}

fn write(v: &Value, out: &mut String) -> Result<()> {
    match v {
        Value::Null => out.push_str("null"),
        Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
        Value::Number(n) => {
            if n.is_f64() {
                return Err(CriteriaError::Shape(format!(
                    "float {n} cannot be canonicalised"
                )));
            }
            out.push_str(&n.to_string());
        }
        Value::String(s) => out.push_str(&serde_json::to_string(s)?),
        Value::Array(a) => {
            out.push('[');
            for (i, x) in a.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                write(x, out)?;
            }
            out.push(']');
        }
        Value::Object(m) => {
            let mut keys: Vec<&String> = m.keys().collect();
            keys.sort();
            out.push('{');
            for (i, k) in keys.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                out.push_str(&serde_json::to_string(k)?);
                out.push(':');
                write(&m[k.as_str()], out)?;
            }
            out.push('}');
        }
    }
    Ok(())
}

pub fn sha256_hex(bytes: &[u8]) -> String {
    let d = Sha256::digest(bytes);
    d.iter().map(|b| format!("{b:02x}")).collect()
}
