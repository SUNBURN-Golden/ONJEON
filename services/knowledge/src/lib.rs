use onjeon_ontology::{
    candidate_view, check_constraints, Abox, CheckProfile, CodeUniverse, Violation, SECTIONS,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::fmt::{Display, Formatter};
use std::path::{Component, Path};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum KnowledgeError {
    FixturePath,
    FixtureAccepted,
    AcceptedWithoutDecision,
    InvalidDecision,
    HashNotObserved(String),
    DuplicateId(String),
    MissingId,
    MissingTarget(String),
    Immutable,
    InvalidPremium(String),
    ConstraintViolation(Vec<Violation>),
    InvalidShape(String),
}

impl Display for KnowledgeError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}

impl std::error::Error for KnowledgeError {}

#[derive(Debug, Clone, Default)]
pub struct ObservationAllowlist {
    hashes: BTreeSet<String>,
}

impl ObservationAllowlist {
    pub fn new(hashes: impl IntoIterator<Item = String>) -> Self {
        Self {
            hashes: hashes.into_iter().collect(),
        }
    }

    pub fn from_archive_listing(listing: &Value) -> Self {
        let mut hashes = BTreeSet::new();
        collect_sha256(listing, &mut hashes);
        Self { hashes }
    }

    pub fn contains(&self, hash: &str) -> bool {
        self.hashes.contains(hash)
    }
}

fn collect_sha256(value: &Value, hashes: &mut BTreeSet<String>) {
    match value {
        Value::Object(map) => {
            for (key, value) in map {
                if matches!(
                    key.as_str(),
                    "sha256" | "content_sha256" | "checksum_sha256"
                ) {
                    if let Some(hash) = value.as_str().filter(|v| is_sha256(v)) {
                        hashes.insert(hash.to_owned());
                    }
                }
                collect_sha256(value, hashes);
            }
        }
        Value::Array(values) => values
            .iter()
            .for_each(|value| collect_sha256(value, hashes)),
        _ => {}
    }
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ReviewDecision {
    pub id: String,
    pub environment: String,
    pub outcome: String,
    pub families_count: u32,
    pub code_checks_passed: bool,
    pub redteam_counterexamples: u32,
    pub cross_doc_conflict_free: bool,
    pub audit_log_sha256: String,
}

impl ReviewDecision {
    fn valid_for_acceptance(&self) -> bool {
        matches!(self.environment.as_str(), "test" | "production")
            && self.outcome == "accepted"
            && self.families_count >= 2
            && self.code_checks_passed
            && self.redteam_counterexamples == 0
            && self.cross_doc_conflict_free
            && is_sha256(&self.audit_log_sha256)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct AcquisitionTask {
    pub id: String,
    pub gap_id: String,
    pub state: String,
    pub attempts: u32,
}

#[derive(Debug, Clone, Default)]
pub struct KnowledgeRepository {
    abox: Abox,
    decisions: BTreeMap<String, ReviewDecision>,
    tasks: BTreeMap<String, AcquisitionTask>,
    promoted_candidates: BTreeSet<String>,
}

impl KnowledgeRepository {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn insert_review_decision(
        &mut self,
        decision: ReviewDecision,
    ) -> Result<(), KnowledgeError> {
        if self.decisions.contains_key(&decision.id) {
            return Err(KnowledgeError::DuplicateId(decision.id));
        }
        self.decisions.insert(decision.id.clone(), decision);
        Ok(())
    }

    pub fn ingest_assertion(
        &mut self,
        source_path: &Path,
        assertion: Value,
        allowlist: &ObservationAllowlist,
    ) -> Result<(), KnowledgeError> {
        reject_fixture_path(source_path)?;
        let id = record_id(&assertion)?.to_owned();
        self.ensure_unique(&id)?;
        let accepted = assertion.get("review_status").and_then(Value::as_str) == Some("accepted");
        let fixture = assertion.get("origin").and_then(Value::as_str) == Some("fixture");
        if accepted && fixture {
            return Err(KnowledgeError::FixtureAccepted);
        }
        if accepted {
            let decision_id = assertion
                .get("review_decision_id")
                .and_then(Value::as_str)
                .ok_or(KnowledgeError::AcceptedWithoutDecision)?;
            if !self
                .decisions
                .get(decision_id)
                .is_some_and(ReviewDecision::valid_for_acceptance)
            {
                return Err(KnowledgeError::InvalidDecision);
            }
        }
        self.check_raw_hashes(&assertion, allowlist)?;
        if let Some(target) = assertion.get("supersedes").and_then(Value::as_str) {
            if self.abox.find("assertions", target).is_none() {
                return Err(KnowledgeError::MissingTarget(target.to_owned()));
            }
        }
        self.abox.section_mut("assertions").push(assertion);
        Ok(())
    }

    pub fn insert_record(&mut self, section: &str, record: Value) -> Result<(), KnowledgeError> {
        if matches!(
            section,
            "assertions" | "premium_observations" | "gaps" | "conflicts"
        ) {
            return Err(KnowledgeError::InvalidShape(format!(
                "use the validated {section} API"
            )));
        }
        self.insert_section(section, record)
    }

    pub fn insert_premium(&mut self, premium: Value) -> Result<(), KnowledgeError> {
        validate_premium(&premium)?;
        self.insert_section("premium_observations", premium)
    }

    pub fn insert_conflict(&mut self, conflict: Value) -> Result<(), KnowledgeError> {
        let members = conflict
            .get("assertion_ids")
            .and_then(Value::as_array)
            .filter(|members| members.len() >= 2)
            .ok_or_else(|| {
                KnowledgeError::InvalidShape("conflict needs at least two assertion_ids".to_owned())
            })?;
        for member in members {
            let id = member.as_str().ok_or_else(|| {
                KnowledgeError::InvalidShape("assertion id must be a string".to_owned())
            })?;
            if self.abox.find("assertions", id).is_none() {
                return Err(KnowledgeError::MissingTarget(id.to_owned()));
            }
        }
        self.insert_section("conflicts", conflict)
    }

    pub fn get(&self, section: &str, id: &str) -> Option<&Value> {
        self.abox.find(section, id)
    }

    pub fn list(&self, section: &str) -> &[Value] {
        self.abox.section(section)
    }

    pub fn update_assertion(
        &mut self,
        _id: &str,
        _replacement: Value,
    ) -> Result<(), KnowledgeError> {
        Err(KnowledgeError::Immutable)
    }

    pub fn superseding(&self, id: &str) -> Vec<&Value> {
        self.abox
            .section("assertions")
            .iter()
            .filter(|row| row.get("supersedes").and_then(Value::as_str) == Some(id))
            .collect()
    }

    pub fn conflicts_for(&self, assertion_id: &str) -> Vec<&Value> {
        self.abox
            .section("conflicts")
            .iter()
            .filter(|row| {
                row.get("assertion_ids")
                    .and_then(Value::as_array)
                    .is_some_and(|ids| ids.iter().any(|id| id.as_str() == Some(assertion_id)))
            })
            .collect()
    }

    pub fn insert_gap(&mut self, gap: Value) -> Result<(), KnowledgeError> {
        self.insert_section("gaps", gap)
    }

    pub fn insert_task(&mut self, task: AcquisitionTask) -> Result<(), KnowledgeError> {
        if self.tasks.contains_key(&task.id) {
            return Err(KnowledgeError::DuplicateId(task.id));
        }
        if self.abox.find("gaps", &task.gap_id).is_none() {
            return Err(KnowledgeError::MissingTarget(task.gap_id));
        }
        self.tasks.insert(task.id.clone(), task);
        Ok(())
    }

    pub fn update_task_state(&mut self, id: &str, state: &str) -> Result<(), KnowledgeError> {
        let task = self
            .tasks
            .get_mut(id)
            .ok_or_else(|| KnowledgeError::MissingTarget(id.to_owned()))?;
        if !matches!(
            state,
            "queued" | "running" | "done" | "failed" | "cancelled"
        ) {
            return Err(KnowledgeError::InvalidShape(state.to_owned()));
        }
        task.state = state.to_owned();
        Ok(())
    }

    pub fn task(&self, id: &str) -> Option<&AcquisitionTask> {
        self.tasks.get(id)
    }

    pub fn check_candidate(
        &self,
        universe: Option<CodeUniverse>,
    ) -> Result<Vec<Violation>, KnowledgeError> {
        let view = candidate_view(&self.abox)
            .map_err(|error| KnowledgeError::InvalidShape(error.to_string()))?;
        Ok(check_constraints(
            &view,
            &CheckProfile::service_conformance(universe),
        ))
    }

    pub fn promote_candidate(
        &mut self,
        candidate_id: &str,
        universe: Option<CodeUniverse>,
    ) -> Result<(), KnowledgeError> {
        let violations = self.check_candidate(universe)?;
        if !violations.is_empty() {
            return Err(KnowledgeError::ConstraintViolation(violations));
        }
        self.promoted_candidates.insert(candidate_id.to_owned());
        Ok(())
    }

    pub fn is_promoted(&self, candidate_id: &str) -> bool {
        self.promoted_candidates.contains(candidate_id)
    }

    fn insert_section(&mut self, section: &str, record: Value) -> Result<(), KnowledgeError> {
        if !SECTIONS.contains(&section) {
            return Err(KnowledgeError::InvalidShape(section.to_owned()));
        }
        let id = record_id(&record)?.to_owned();
        self.ensure_unique(&id)?;
        self.abox.section_mut(section).push(record);
        Ok(())
    }

    fn ensure_unique(&self, id: &str) -> Result<(), KnowledgeError> {
        if SECTIONS
            .iter()
            .any(|section| self.abox.find(section, id).is_some())
            || self.tasks.contains_key(id)
            || self.decisions.contains_key(id)
        {
            Err(KnowledgeError::DuplicateId(id.to_owned()))
        } else {
            Ok(())
        }
    }

    fn check_raw_hashes(
        &self,
        assertion: &Value,
        allowlist: &ObservationAllowlist,
    ) -> Result<(), KnowledgeError> {
        let raw_assets: BTreeMap<&str, &str> = self
            .abox
            .section("raw_assets")
            .iter()
            .filter_map(|raw| Some((record_id(raw).ok()?, raw.get("sha256")?.as_str()?)))
            .collect();
        for evidence in assertion
            .get("evidence")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
        {
            if let Some(raw_id) = evidence
                .get("ref")
                .and_then(Value::as_str)
                .filter(|id| id.starts_with("raw:"))
            {
                let hash = raw_assets
                    .get(raw_id)
                    .ok_or_else(|| KnowledgeError::MissingTarget(raw_id.to_owned()))?;
                if !allowlist.contains(hash) {
                    return Err(KnowledgeError::HashNotObserved((*hash).to_owned()));
                }
            }
        }
        Ok(())
    }
}

fn record_id(record: &Value) -> Result<&str, KnowledgeError> {
    record
        .get("id")
        .and_then(Value::as_str)
        .ok_or(KnowledgeError::MissingId)
}

fn reject_fixture_path(path: &Path) -> Result<(), KnowledgeError> {
    let parts: Vec<_> = path
        .components()
        .filter_map(|part| match part {
            Component::Normal(value) => value.to_str(),
            _ => None,
        })
        .collect();
    if parts
        .windows(2)
        .any(|pair| pair == ["packages", "fixtures"])
    {
        Err(KnowledgeError::FixturePath)
    } else {
        Ok(())
    }
}

fn validate_premium(premium: &Value) -> Result<(), KnowledgeError> {
    for required in [
        "evidence",
        "raw_amount",
        "observed_at",
        "missing_dimensions",
        "comparison_eligible",
    ] {
        if premium.get(required).is_none() {
            return Err(KnowledgeError::InvalidPremium(format!(
                "missing {required}"
            )));
        }
    }
    if premium
        .get("raw_amount")
        .and_then(Value::as_i64)
        .is_none_or(|amount| amount <= 0)
    {
        return Err(KnowledgeError::InvalidPremium("raw_amount".to_owned()));
    }
    if premium.get("comparison_eligible").and_then(Value::as_bool) == Some(true) {
        for required in [
            "conditions",
            "package_binding",
            "source_as_of",
            "comparison_basis_id",
        ] {
            if premium.get(required).is_none_or(Value::is_null) {
                return Err(KnowledgeError::InvalidPremium(format!(
                    "eligible missing {required}"
                )));
            }
        }
        if premium.get("review_status").and_then(Value::as_str) != Some("accepted") {
            return Err(KnowledgeError::InvalidPremium(
                "eligible not accepted".to_owned(),
            ));
        }
    }
    Ok(())
}
