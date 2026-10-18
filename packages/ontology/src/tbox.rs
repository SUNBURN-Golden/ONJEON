//! T-box loader (`packages/schemas/ontology/tbox.json`, onto-0.2).

use crate::error::{shape, Result};
use serde::Deserialize;

/// Constraint ids the T-box must define: K1~K16, nothing else.
pub const CONSTRAINT_IDS: [&str; 16] = [
    "K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8", "K9", "K10", "K11", "K12", "K13", "K14", "K15",
    "K16",
];

/// Classes the model layers (source, document, product, meaning, execution, meta) rely on.
const REQUIRED_CLASSES: [&str; 12] = [
    "RawAsset",
    "DocumentSegment",
    "TermsEdition",
    "TermsLineage",
    "ClauseOccurrence",
    "SalesConfiguration",
    "CoverageOccurrence",
    "DiseaseCategory",
    "CodeSet",
    "Assertion",
    "Release",
    "ReleaseNotice",
];

/// Relations the checker and the input stage read.
const REQUIRED_RELATIONS: [&str; 10] = [
    "uses_definition",
    "includes_codes",
    "excludes_codes",
    "realizes",
    "in_edition",
    "uses_edition",
    "applies_to",
    "application_scope_complete",
    "scope_relation",
    "implemented_by",
];

#[derive(Debug, Clone, Deserialize)]
pub struct Class {
    pub id: String,
    pub ko: String,
    pub layer: String,
    pub identity: String,
    pub zone: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Relation {
    pub id: String,
    pub ko: String,
    pub domain: String,
    pub range: String,
    pub cardinality: String,
    pub semantics: String,
    pub temporal: bool,
    pub inference: String,
    pub criticality: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Constraint {
    pub id: String,
    pub rule: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Tbox {
    pub version: String,
    pub classes: Vec<Class>,
    pub relations: Vec<Relation>,
    pub constraints: Vec<Constraint>,
}

impl Tbox {
    pub fn class(&self, id: &str) -> Option<&Class> {
        self.classes.iter().find(|c| c.id == id)
    }

    pub fn relation(&self, id: &str) -> Option<&Relation> {
        self.relations.iter().find(|r| r.id == id)
    }

    pub fn constraint(&self, id: &str) -> Option<&Constraint> {
        self.constraints.iter().find(|c| c.id == id)
    }
}

/// Parses and validates a T-box document. Rejects other onto versions, duplicate ids and
/// a constraint list that is not exactly K1~K16.
pub fn load_tbox(json: &str) -> Result<Tbox> {
    let t: Tbox = serde_json::from_str(json)?;
    if !t.version.starts_with("onto-0.2") {
        return Err(shape(format!(
            "tbox version {:?}: onto-0.2 expected",
            t.version
        )));
    }
    unique(t.classes.iter().map(|c| c.id.as_str()), "class")?;
    unique(t.relations.iter().map(|r| r.id.as_str()), "relation")?;
    unique(t.constraints.iter().map(|c| c.id.as_str()), "constraint")?;
    let mut ids: Vec<&str> = t.constraints.iter().map(|c| c.id.as_str()).collect();
    let mut want = CONSTRAINT_IDS.to_vec();
    ids.sort_unstable();
    want.sort_unstable();
    if ids != want {
        return Err(shape(format!(
            "constraints must be exactly K1~K16, got {ids:?}"
        )));
    }
    for c in REQUIRED_CLASSES {
        if t.class(c).is_none() {
            return Err(shape(format!("tbox has no class {c}")));
        }
    }
    for r in REQUIRED_RELATIONS {
        if t.relation(r).is_none() {
            return Err(shape(format!("tbox has no relation {r}")));
        }
    }
    Ok(t)
}

fn unique<'a>(ids: impl Iterator<Item = &'a str>, what: &str) -> Result<()> {
    let mut seen = std::collections::BTreeSet::new();
    for id in ids {
        if !seen.insert(id) {
            return Err(shape(format!("duplicate {what} id {id}")));
        }
    }
    Ok(())
}
