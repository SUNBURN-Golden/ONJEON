//! File loader for `data/criteria/` (the path this task produces).
//!
//! Layout (see `data/criteria/README.md` and `criterion-file.schema.json`):
//! one file per criterion, `{ "criterion": {...}, "versions": [...] }`. The loader
//! checks, before serde ever sees the bytes:
//!
//! - **Reserved keys**: any object key `default`, `defaults` or starting with `default_`
//!   is a need-amount default, not a criterion version. Such payloads belong to
//!   `data/criteria/defaults/` (T-KN-13) and may only be served behind the D-08
//!   application record (T-KN-14) — so they are refused here, unconditionally.
//! - **K8**: no private-zone id prefix in any string.
//!
//! then the store's insertion rules run (ids, scope, sources, dates, correction chain).

use crate::error::{CriteriaError, Result};
use crate::k8;
use crate::model::{CriterionFile, CriterionVersion};
use crate::release::CriteriaRelease;
use crate::store::CriterionStore;
use serde_json::Value;
use std::path::{Path, PathBuf};

fn scan_keys(v: &Value) -> Result<()> {
    if let Value::Object(m) = v {
        for (k, x) in m {
            if k.starts_with("default") {
                return Err(CriteriaError::DefaultOutsideGate {
                    key: k.clone(),
                    detail: "need-amount defaults are not criterion versions".into(),
                });
            }
            scan_keys(x)?;
        }
    }
    if let Value::Array(a) = v {
        for x in a {
            scan_keys(x)?;
        }
    }
    Ok(())
}

/// Parse and insert one criterion file (`{criterion, versions[]}`).
/// Returns the criterion id on success.
pub fn load_file(path: &Path, store: &mut CriterionStore) -> Result<String> {
    let text = std::fs::read_to_string(path)?;
    load_str(&text, store).map_err(|e| match e {
        CriteriaError::Shape(s) => CriteriaError::Shape(format!("{}: {s}", path.display())),
        other => other,
    })
}

/// Same as [`load_file`] for in-memory text (tests).
pub fn load_str(text: &str, store: &mut CriterionStore) -> Result<String> {
    let v: Value = serde_json::from_str(text)?;
    scan_keys(&v)?;
    k8::check_value(&v)?;
    let f: CriterionFile = serde_json::from_value(v)?;
    if f.versions.is_empty() {
        return Err(CriteriaError::Shape(format!(
            "{}: a criterion file needs at least one version",
            f.criterion.id
        )));
    }
    let cid = f.criterion.id.clone();
    store.insert_criterion(f.criterion)?;
    for vf in f.versions {
        store.insert_version(CriterionVersion::from_file(&cid, vf))?;
    }
    Ok(cid)
}

/// Load every `*.json` in `dir` (sorted for deterministic errors) into a new store.
/// A missing directory yields an empty store — zero criteria is a legitimate state.
pub fn load_dir(dir: &Path) -> Result<CriterionStore> {
    let mut store = CriterionStore::new();
    if !dir.is_dir() {
        return Ok(store);
    }
    let mut files: Vec<PathBuf> = std::fs::read_dir(dir)?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().is_some_and(|x| x == "json"))
        .collect();
    files.sort();
    for p in files {
        load_file(&p, &mut store)?;
    }
    Ok(store)
}

/// Read a frozen criteria release file (`releases/<id>.json`). Integrity against a
/// store is checked separately with [`crate::release::verify`].
pub fn load_release_file(path: &Path) -> Result<CriteriaRelease> {
    let text = std::fs::read_to_string(path)?;
    let r: CriteriaRelease = serde_json::from_str(&text)
        .map_err(|e| CriteriaError::Shape(format!("{}: {e}", path.display())))?;
    if !crate::release::is_release_id(&r.id) {
        return Err(CriteriaError::BadReleaseId { id: r.id });
    }
    Ok(r)
}
