//! A-box store, typed records and the snapshot ([`View`]) every check and lookup reads.
//!
//! The raw JSON of each record is kept (it is what the release content hash covers); typed records
//! are parsed from it once when a view is built.

use crate::error::{shape, OntologyError, Result};
use onjeon_contracts::ReviewStatus;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

/// Sections a release freezes. Acquisition tasks are operational state and stay outside.
pub const SECTIONS: [&str; 10] = [
    "raw_assets",
    "segments",
    "terms_editions",
    "terms_lineages",
    "clauses",
    "nodes",
    "assertions",
    "conflicts",
    "gaps",
    "premium_observations",
];

/// Document roles whose clauses are contract terms (basis evidence for C0 claims).
pub const TERMS_ROLES: [&str; 3] = ["보통약관", "특약 약관", "별표"];

/// Structural predicates: they need observation evidence, not clause basis (K1).
pub const STRUCTURAL: [&str; 3] = ["uses_edition", "realizes", "disclosure_of"];

pub(crate) fn s<'a>(v: &'a Value, k: &str) -> Option<&'a str> {
    v.get(k).and_then(Value::as_str)
}

pub(crate) fn id_of(v: &Value) -> Result<&str> {
    s(v, "id").ok_or_else(|| shape(format!("record without id: {v}")))
}

/// A mutable A-box: raw sections, releases, notices and the rule files the claims point at.
#[derive(Debug, Clone, Default)]
pub struct Abox {
    pub sections: BTreeMap<String, Vec<Value>>,
    pub acquisition_tasks: Vec<Value>,
    pub releases: Vec<crate::release::Release>,
    pub release_notices: Vec<crate::release::ReleaseNotice>,
    /// Rule files by the path stored in `rule_path`. Missing files hash to `None`.
    pub rule_files: BTreeMap<String, Vec<u8>>,
    /// Capability a caller declares per coverage (`enabled`, ...). K11 checks the declaration against the claims.
    pub declared_capabilities: BTreeMap<String, String>,
}

impl Abox {
    /// Parses an A-box document. `rule_files` supplies the bytes of the rule files by `rule_path`.
    pub fn from_json(json: &str, rule_files: BTreeMap<String, Vec<u8>>) -> Result<Abox> {
        let doc: Value = serde_json::from_str(json)?;
        let mut a = Abox {
            rule_files,
            ..Abox::default()
        };
        for k in SECTIONS {
            let list = match doc.get(k) {
                None | Some(Value::Null) => Vec::new(),
                Some(Value::Array(l)) => l.clone(),
                Some(_) => return Err(shape(format!("{k}: array expected"))),
            };
            a.sections.insert(k.to_string(), list);
        }
        if let Some(Value::Array(l)) = doc.get("acquisition_tasks") {
            a.acquisition_tasks = l.clone();
        }
        if let Some(Value::Array(l)) = doc.get("releases") {
            a.releases = l
                .iter()
                .map(crate::release::Release::from_value)
                .collect::<Result<_>>()?;
        }
        if let Some(Value::Array(l)) = doc.get("release_notices") {
            a.release_notices = l
                .iter()
                .map(|n| serde_json::from_value(n.clone()).map_err(OntologyError::from))
                .collect::<Result<_>>()?;
        }
        Ok(a)
    }

    /// Reads `<dir>/abox_cases.json` and every rule file its assertions name (relative to `dir`).
    pub fn from_dir(dir: &Path) -> Result<Abox> {
        let text = std::fs::read_to_string(dir.join("abox_cases.json"))?;
        let mut a = Abox::from_json(&text, BTreeMap::new())?;
        let paths: BTreeSet<String> = a
            .section("assertions")
            .iter()
            .filter_map(|x| s(x, "rule_path").map(str::to_string))
            .collect();
        for p in paths {
            if let Ok(bytes) = std::fs::read(dir.join(&p)) {
                a.rule_files.insert(p, bytes);
            }
        }
        Ok(a)
    }

    pub fn section(&self, name: &str) -> &[Value] {
        self.sections.get(name).map(Vec::as_slice).unwrap_or(&[])
    }

    pub fn section_mut(&mut self, name: &str) -> &mut Vec<Value> {
        self.sections.entry(name.to_string()).or_default()
    }

    /// The record `id` in `section`, for in-place edits (tests use it to simulate tampering).
    pub fn find_mut(&mut self, section: &str, id: &str) -> Option<&mut Value> {
        self.section_mut(section)
            .iter_mut()
            .find(|x| s(x, "id") == Some(id))
    }

    pub fn find(&self, section: &str, id: &str) -> Option<&Value> {
        self.section(section)
            .iter()
            .find(|x| s(x, "id") == Some(id))
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct Fingerprint {
    pub rule: String,
    pub sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Evidence {
    pub target: String,
    pub role: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Decision {
    pub by: Option<String>,
    /// `covers=[rule, fingerprint]` of a review decision that accepts a differing fingerprint as the same part.
    pub covers: Option<Fingerprint>,
}

#[derive(Debug, Clone)]
pub struct Assertion {
    pub id: String,
    pub subject: String,
    pub predicate: String,
    pub object: Option<String>,
    pub value: Option<Value>,
    pub criticality: String,
    pub value_state: String,
    pub review_status: ReviewStatus,
    pub evidence: Vec<Evidence>,
    pub valid_from: Option<String>,
    pub valid_to: Option<String>,
    pub supersedes: Option<String>,
    pub decision: Option<Decision>,
    pub origin: Option<String>,
    pub rule_path: Option<String>,
    pub covers_editions: Option<Vec<String>>,
}

impl Assertion {
    pub fn accepted(&self) -> bool {
        self.review_status == ReviewStatus::Accepted
    }

    pub fn value_str(&self) -> Option<&str> {
        self.value.as_ref().and_then(Value::as_str)
    }

    pub fn decision_by(&self) -> Option<&str> {
        self.decision.as_ref().and_then(|d| d.by.as_deref())
    }

    fn parse(v: &Value) -> Result<Assertion> {
        let id = id_of(v)?.to_string();
        let req = |k: &str| {
            s(v, k)
                .map(str::to_string)
                .ok_or_else(|| shape(format!("assertion {id}: {k} missing")))
        };
        let status = req("review_status")?;
        let review_status: ReviewStatus = serde_json::from_value(Value::String(status.clone()))
            .map_err(|_| shape(format!("assertion {id}: unknown review_status {status}")))?;
        let evidence = match v.get("evidence") {
            Some(Value::Array(l)) => l
                .iter()
                .map(|e| {
                    Ok(Evidence {
                        target: s(e, "ref")
                            .ok_or_else(|| shape(format!("assertion {id}: evidence without ref")))?
                            .to_string(),
                        role: s(e, "role").unwrap_or("").to_string(),
                    })
                })
                .collect::<Result<Vec<_>>>()?,
            _ => Vec::new(),
        };
        let time = v.get("time");
        let tm = |k: &str| {
            time.and_then(|t| s(t, k))
                .filter(|x| !x.is_empty())
                .map(str::to_string)
        };
        let decision = v
            .get("decision")
            .filter(|d| d.is_object())
            .map(|d| Decision {
                by: s(d, "by").map(str::to_string),
                covers: match d.get("covers") {
                    Some(Value::Array(c)) if c.len() == 2 => match (c[0].as_str(), c[1].as_str()) {
                        (Some(r), Some(h)) => Some(Fingerprint {
                            rule: r.to_string(),
                            sha256: h.to_string(),
                        }),
                        _ => None,
                    },
                    _ => None,
                },
            });
        Ok(Assertion {
            subject: req("subject")?,
            predicate: req("predicate")?,
            object: s(v, "object").map(str::to_string),
            value: v.get("value").filter(|x| !x.is_null()).cloned(),
            criticality: s(v, "criticality").unwrap_or("").to_string(),
            value_state: s(v, "value_state").unwrap_or("").to_string(),
            review_status,
            evidence,
            valid_from: tm("valid_from"),
            valid_to: tm("valid_to"),
            supersedes: s(v, "supersedes").map(str::to_string),
            decision,
            origin: s(v, "origin").map(str::to_string),
            rule_path: s(v, "rule_path").map(str::to_string),
            covers_editions: match v.get("covers_editions") {
                Some(Value::Array(l)) => Some(
                    l.iter()
                        .filter_map(|x| x.as_str().map(str::to_string))
                        .collect(),
                ),
                _ => None,
            },
            id,
        })
    }

    /// Valid on `date` (`YYYY-MM-DD`, compared as text): open ends are always valid.
    pub fn valid_on(&self, date: &str) -> bool {
        self.valid_from.as_deref().is_none_or(|f| f <= date)
            && self.valid_to.as_deref().is_none_or(|t| date <= t)
    }
}

#[derive(Debug, Clone)]
pub struct Segment {
    pub id: String,
    pub raw_asset: Option<String>,
    pub doc_role: String,
    pub fingerprint: Option<Fingerprint>,
}

#[derive(Debug, Clone)]
pub struct Clause {
    pub id: String,
    pub segment: String,
}

#[derive(Debug, Clone)]
pub struct EditionPart {
    pub role: String,
    pub fingerprint: Fingerprint,
}

#[derive(Debug, Clone)]
pub struct Edition {
    pub id: String,
    pub lineage: Option<String>,
    pub parts: Vec<EditionPart>,
}

#[derive(Debug, Clone)]
pub struct Node {
    pub id: String,
    pub class: String,
    pub raw: Value,
}

impl Node {
    pub fn label(&self) -> &str {
        s(&self.raw, "label").unwrap_or(&self.id)
    }

    pub fn get_str(&self, k: &str) -> Option<&str> {
        s(&self.raw, k).filter(|x| !x.is_empty())
    }
}

#[derive(Debug, Clone)]
pub struct Conflict {
    pub id: String,
    pub assertions: Vec<String>,
    pub state: Option<String>,
}

fn fingerprint_of(v: &Value) -> Option<Fingerprint> {
    let fp = v.get("fingerprint")?;
    let (r, h) = (s(fp, "rule")?, s(fp, "sha256")?);
    (!r.is_empty() && !h.is_empty()).then(|| Fingerprint {
        rule: r.to_string(),
        sha256: h.to_string(),
    })
}

/// What a release (or a candidate) reads: sorted records, typed, plus the integrity findings of its freeze.
#[derive(Debug, Clone)]
pub struct View {
    pub raw: BTreeMap<String, Vec<Value>>,
    pub assertions: Vec<Assertion>,
    pub segments: Vec<Segment>,
    pub clauses: Vec<Clause>,
    pub editions: Vec<Edition>,
    pub nodes: Vec<Node>,
    pub conflicts: Vec<Conflict>,
    pub acquisition_tasks: Vec<Value>,
    /// K15 findings from comparing the stored members with the frozen release (empty for a candidate).
    pub integrity: Vec<crate::check::Violation>,
    pub rule_files: BTreeMap<String, Vec<u8>>,
    pub declared_capabilities: BTreeMap<String, String>,
    superseded: BTreeSet<String>,
}

impl View {
    pub(crate) fn build(
        raw: BTreeMap<String, Vec<Value>>,
        a: &Abox,
        integrity: Vec<crate::check::Violation>,
    ) -> Result<View> {
        let list = |k: &str| raw.get(k).map(Vec::as_slice).unwrap_or(&[]);
        let assertions = list("assertions")
            .iter()
            .map(Assertion::parse)
            .collect::<Result<Vec<_>>>()?;
        let segments = list("segments")
            .iter()
            .map(|v| {
                Ok(Segment {
                    id: id_of(v)?.to_string(),
                    raw_asset: s(v, "raw_asset").map(str::to_string),
                    doc_role: s(v, "doc_role").unwrap_or("").to_string(),
                    fingerprint: fingerprint_of(v),
                })
            })
            .collect::<Result<Vec<_>>>()?;
        let clauses = list("clauses")
            .iter()
            .map(|v| {
                Ok(Clause {
                    id: id_of(v)?.to_string(),
                    segment: s(v, "segment")
                        .ok_or_else(|| shape("clause without segment"))?
                        .to_string(),
                })
            })
            .collect::<Result<Vec<_>>>()?;
        let editions = list("terms_editions")
            .iter()
            .map(|v| {
                let parts = match v.get("parts") {
                    Some(Value::Array(l)) => l
                        .iter()
                        .map(|p| {
                            Ok(EditionPart {
                                role: s(p, "role").unwrap_or("").to_string(),
                                fingerprint: fingerprint_of(p).ok_or_else(|| {
                                    shape(format!(
                                        "edition {}: part without fingerprint",
                                        s(v, "id").unwrap_or("?")
                                    ))
                                })?,
                            })
                        })
                        .collect::<Result<Vec<_>>>()?,
                    _ => Vec::new(),
                };
                Ok(Edition {
                    id: id_of(v)?.to_string(),
                    lineage: s(v, "lineage").map(str::to_string),
                    parts,
                })
            })
            .collect::<Result<Vec<_>>>()?;
        let nodes = list("nodes")
            .iter()
            .map(|v| {
                Ok(Node {
                    id: id_of(v)?.to_string(),
                    class: s(v, "class").unwrap_or("").to_string(),
                    raw: v.clone(),
                })
            })
            .collect::<Result<Vec<_>>>()?;
        let conflicts = list("conflicts")
            .iter()
            .map(|v| {
                Ok(Conflict {
                    id: id_of(v)?.to_string(),
                    assertions: match v.get("assertions") {
                        Some(Value::Array(l)) => l
                            .iter()
                            .filter_map(|x| x.as_str().map(str::to_string))
                            .collect(),
                        _ => Vec::new(),
                    },
                    state: s(v, "state").map(str::to_string),
                })
            })
            .collect::<Result<Vec<_>>>()?;
        let superseded = assertions
            .iter()
            .filter_map(|x| x.supersedes.clone())
            .collect();
        Ok(View {
            assertions,
            segments,
            clauses,
            editions,
            nodes,
            conflicts,
            superseded,
            raw,
            acquisition_tasks: a.acquisition_tasks.clone(),
            integrity,
            rule_files: a.rule_files.clone(),
            declared_capabilities: a.declared_capabilities.clone(),
        })
    }

    /// Assertions nobody supersedes. Superseded ones stay in the pool so a release reproduces history.
    pub fn current(&self) -> impl Iterator<Item = &Assertion> {
        self.assertions
            .iter()
            .filter(|a| !self.superseded.contains(&a.id))
    }

    pub fn node(&self, id: &str) -> Option<&Node> {
        self.nodes.iter().find(|n| n.id == id)
    }

    pub fn segment(&self, id: &str) -> Option<&Segment> {
        self.segments.iter().find(|x| x.id == id)
    }

    pub fn assertion(&self, id: &str) -> Option<&Assertion> {
        self.assertions.iter().find(|a| a.id == id)
    }

    /// Clause id → terms edition, for clauses of a terms-role segment that an accepted `realizes` ties to an edition.
    pub fn terms_clauses(&self) -> BTreeMap<String, String> {
        let realized: BTreeMap<&str, &str> = self
            .current()
            .filter(|a| a.predicate == "realizes" && a.accepted())
            .filter_map(|a| a.object.as_deref().map(|o| (a.subject.as_str(), o)))
            .collect();
        self.clauses
            .iter()
            .filter_map(|c| {
                let seg = self.segment(&c.segment)?;
                if !TERMS_ROLES.contains(&seg.doc_role.as_str()) {
                    return None;
                }
                realized
                    .get(c.segment.as_str())
                    .map(|e| (c.id.clone(), (*e).to_string()))
            })
            .collect()
    }
}
