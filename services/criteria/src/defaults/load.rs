//! File loader for `data/criteria/defaults/candidates/` (this task's produced path).
//!
//! Layout (see this module's `README.md` and `default-file.schema.json`):
//! one file per candidate, `{ "candidate": {...}, "versions": [...] }`. Before serde
//! sees the bytes the loader runs the same K8 private-identifier scan as the
//! criterion loader; the criteria loader's `default*`-key refusal does not apply
//! here — this *is* the defaults path, and its files are refused by the criterion
//! loader anyway (they are not criterion files). The store's insertion rules then
//! run (ids, scope, update cycle, `applied == false`, sources, dates, chain).

use super::error::{DefaultsError, Result};
use super::model::{CandidateFile, CandidateVersion};
use super::store::DefaultsStore;
use crate::error::CriteriaError;
use crate::k8;
use serde_json::Value;
use std::path::{Path, PathBuf};

/// Parse and insert one candidate file (`{candidate, versions[]}`).
/// Returns the candidate id on success.
pub fn load_file(path: &Path, store: &mut DefaultsStore) -> Result<String> {
    let text = std::fs::read_to_string(path)?;
    load_str(&text, store).map_err(|e| match e {
        DefaultsError::Shape(s) => DefaultsError::Shape(format!("{}: {s}", path.display())),
        DefaultsError::Criteria(CriteriaError::Shape(s)) => {
            DefaultsError::Criteria(CriteriaError::Shape(format!("{}: {s}", path.display())))
        }
        other => other,
    })
}

/// Same as [`load_file`] for in-memory text (tests).
pub fn load_str(text: &str, store: &mut DefaultsStore) -> Result<String> {
    let v: Value = serde_json::from_str(text)?;
    k8::check_value(&v)?;
    let f: CandidateFile = serde_json::from_value(v)?;
    if f.versions.is_empty() {
        return Err(DefaultsError::Shape(format!(
            "{}: a candidate file needs at least one version",
            f.candidate.id
        )));
    }
    let cid = f.candidate.id.clone();
    store.insert_candidate(f.candidate)?;
    for vf in f.versions {
        store.insert_version(CandidateVersion::from_file(&cid, vf))?;
    }
    Ok(cid)
}

/// Load every `*.json` in `dir` (sorted for deterministic errors) into a new store.
/// A missing directory yields an empty store — zero candidates is a legitimate
/// state: it only means no confirmed public-statistic source has been archived.
pub fn load_dir(dir: &Path) -> Result<DefaultsStore> {
    let mut store = DefaultsStore::new();
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
