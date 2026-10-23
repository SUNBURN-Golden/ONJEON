//! Append-only knowledge APIs. Use `KnowledgeRepository::connect` for durable service
//! storage; `new` is an isolated in-memory repository for tests and offline checks.
mod postgres_store;
use onjeon_ontology::{
    candidate_view, check_constraints, Abox, CheckProfile, CodeUniverse, Violation, SECTIONS,
};
use postgres_store::PostgresStore;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
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
    Database {
        code: Option<String>,
        constraint: Option<String>,
    },
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
            hashes: hashes.into_iter().filter(|h| is_sha256(h)).collect(),
        }
    }
    /// Reads both committed R2 formats: object-key -> checksum, or verified download
    /// results. A failed/mismatched result never contributes its source checksum.
    pub fn from_archive_listing(listing: &Value) -> Self {
        let mut hashes = BTreeSet::new();
        collect_sha256(listing, &mut hashes);
        Self { hashes }
    }
    pub fn contains(&self, hash: &str) -> bool {
        self.hashes.contains(hash)
    }
    pub fn len(&self) -> usize {
        self.hashes.len()
    }
    pub fn is_empty(&self) -> bool {
        self.hashes.is_empty()
    }
}
fn collect_sha256(value: &Value, hashes: &mut BTreeSet<String>) {
    match value {
        Value::Object(map) => {
            if map.contains_key("sha256_downloaded") || map.contains_key("sha256_source") {
                if map.get("status").and_then(Value::as_str) == Some("byte_identical")
                    && map.get("sha256_source") == map.get("sha256_downloaded")
                {
                    if let Some(h) = map
                        .get("sha256_downloaded")
                        .and_then(Value::as_str)
                        .filter(|h| is_sha256(h))
                    {
                        hashes.insert(h.to_owned());
                    }
                }
                return;
            }
            for (key, v) in map {
                if matches!(
                    key.as_str(),
                    "sha256" | "content_sha256" | "checksum_sha256"
                ) || key.starts_with("objects/sha256/")
                    || key.starts_with("observations/")
                {
                    if let Some(h) = v.as_str().filter(|h| is_sha256(h)) {
                        hashes.insert(h.to_owned());
                    }
                }
                collect_sha256(v, hashes);
            }
        }
        Value::Array(values) => values.iter().for_each(|v| collect_sha256(v, hashes)),
        _ => {}
    }
}
fn is_sha256(v: &str) -> bool {
    v.len() == 64
        && v.bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ReviewDecision {
    pub id: String,
    pub environment: String,
    pub outcome: String,
    pub provider_family_labels: Vec<String>,
    pub families_count: u32,
    pub code_checks_passed: bool,
    pub redteam_counterexamples: u32,
    pub cross_doc_conflict_free: bool,
    pub audit_log_sha256: String,
    pub prompt_version: String,
    pub decided_at: String,
}
impl ReviewDecision {
    fn valid_for_acceptance(&self) -> bool {
        let labels: BTreeSet<_> = self
            .provider_family_labels
            .iter()
            .filter(|s| !s.is_empty())
            .collect();
        matches!(self.environment.as_str(), "test" | "production")
            && self.outcome == "accepted"
            && self.families_count >= 2
            && labels.len() == self.families_count as usize
            && self.code_checks_passed
            && self.redteam_counterexamples == 0
            && self.cross_doc_conflict_free
            && is_sha256(&self.audit_log_sha256)
            && !self.prompt_version.is_empty()
            && !self.decided_at.is_empty()
    }
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct AcquisitionTask {
    pub id: String,
    pub gap_id: String,
    pub state: String,
    pub attempts: u32,
}

/// Assertions can only be appended or superseded; no update method exists.
/// ```compile_fail
/// use onjeon_knowledge::KnowledgeRepository;
/// let mut repository = KnowledgeRepository::new();
/// repository.update_assertion("a:existing", serde_json::json!({}));
/// ```
#[derive(Debug, Default)]
pub struct KnowledgeRepository {
    abox: Abox,
    decisions: BTreeMap<String, ReviewDecision>,
    tasks: BTreeMap<String, AcquisitionTask>,
    promoted_candidates: BTreeSet<String>,
    allowlist: ObservationAllowlist,
    store: Option<PostgresStore>,
}
impl KnowledgeRepository {
    pub fn new() -> Self {
        Self::default()
    }
    /// Migrations must already be applied. Credentials are never included in errors or Debug.
    pub fn connect(config: &str, allowlist: ObservationAllowlist) -> Result<Self, KnowledgeError> {
        let mut repo = Self {
            store: Some(PostgresStore::connect(config)?),
            allowlist,
            ..Self::default()
        };
        repo.refresh()?;
        Ok(repo)
    }
    /// Refresh the read cache after writes by another process. Candidate checks always
    /// read a fresh repeatable-read DB snapshot even without calling this method.
    pub fn refresh(&mut self) -> Result<(), KnowledgeError> {
        if let Some(store) = &self.store {
            let s = store.snapshot()?;
            self.abox = s.abox;
            self.decisions = s.decisions;
            self.tasks = s.tasks;
            self.promoted_candidates = s.candidates;
        }
        Ok(())
    }
    pub fn set_allowlist(&mut self, allowlist: ObservationAllowlist) {
        self.allowlist = allowlist;
    }
    pub fn insert_review_decision(
        &mut self,
        decision: ReviewDecision,
    ) -> Result<(), KnowledgeError> {
        self.refresh()?;
        self.ensure_unique(&decision.id)?;
        if let Some(store) = &self.store {
            store.insert("review_decisions", &json!(decision))?;
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
        self.refresh()?;
        self.validate_assertion(&assertion, allowlist)?;
        if let Some(store) = &self.store {
            store.insert("assertions", &assertion)?;
        }
        self.abox.section_mut("assertions").push(assertion);
        self.allowlist = allowlist.clone();
        Ok(())
    }
    fn validate_assertion(
        &self,
        assertion: &Value,
        allowlist: &ObservationAllowlist,
    ) -> Result<(), KnowledgeError> {
        self.ensure_unique(record_id(assertion)?)?;
        validate_acceptance(assertion, &self.decisions)?;
        self.check_raw_hashes(assertion, allowlist)?;
        if let Some(target) = assertion.get("supersedes").and_then(Value::as_str) {
            if self.abox.find("assertions", target).is_none() {
                return Err(KnowledgeError::MissingTarget(target.into()));
            }
        }
        Ok(())
    }
    /// Source, structure and node rows. A raw asset is the allowlist boundary itself: its
    /// hash must be in the R2 observation list and its id must be derived from that hash.
    pub fn insert_record(&mut self, section: &str, record: Value) -> Result<(), KnowledgeError> {
        if matches!(
            section,
            "assertions" | "premium_observations" | "gaps" | "conflicts"
        ) {
            return Err(KnowledgeError::InvalidShape(format!(
                "use the validated {section} API"
            )));
        }
        if section == "raw_assets" {
            validate_raw_asset(&record, &self.allowlist)?;
        }
        self.insert_section(section, record)
    }
    pub fn insert_premium(&mut self, premium: Value) -> Result<(), KnowledgeError> {
        self.refresh()?;
        validate_premium(&premium)?;
        validate_acceptance(&premium, &self.decisions)?;
        self.check_raw_hashes(&premium, &self.allowlist)?;
        self.insert_section("premium_observations", premium)
    }
    pub fn insert_conflict(&mut self, conflict: Value) -> Result<(), KnowledgeError> {
        self.refresh()?;
        let conflict = canonical_conflict(conflict)?;
        validate_conflict(&self.abox, &conflict)?;
        self.insert_section("conflicts", conflict)
    }
    /// Atomic API required by the DB's deferred branching-supersedes constraint.
    pub fn ingest_corrections(
        &mut self,
        path: &Path,
        assertions: Vec<Value>,
        conflict: Value,
        allowlist: &ObservationAllowlist,
    ) -> Result<(), KnowledgeError> {
        reject_fixture_path(path)?;
        self.refresh()?;
        let mut staged = Self {
            abox: self.abox.clone(),
            decisions: self.decisions.clone(),
            tasks: self.tasks.clone(),
            ..Self::default()
        };
        for assertion in &assertions {
            staged.validate_assertion(assertion, allowlist)?;
            staged
                .abox
                .section_mut("assertions")
                .push(assertion.clone());
        }
        let conflict = canonical_conflict(conflict)?;
        staged.ensure_unique(record_id(&conflict)?)?;
        validate_conflict(&staged.abox, &conflict)?;
        if let Some(store) = &self.store {
            store.insert_corrections(&assertions, &conflict)?;
        }
        self.abox = staged.abox;
        self.abox.section_mut("conflicts").push(conflict);
        self.allowlist = allowlist.clone();
        Ok(())
    }
    pub fn get(&self, section: &str, id: &str) -> Option<&Value> {
        self.abox.find(section, id)
    }
    pub fn list(&self, section: &str) -> &[Value] {
        self.abox.section(section)
    }
    pub fn superseding(&self, id: &str) -> Vec<&Value> {
        self.list("assertions")
            .iter()
            .filter(|r| r.get("supersedes").and_then(Value::as_str) == Some(id))
            .collect()
    }
    pub fn conflicts_for(&self, id: &str) -> Vec<&Value> {
        self.list("conflicts")
            .iter()
            .filter(|r| {
                r["assertions"]
                    .as_array()
                    .is_some_and(|ids| ids.iter().any(|v| v.as_str() == Some(id)))
            })
            .collect()
    }
    pub fn insert_gap(&mut self, gap: Value) -> Result<(), KnowledgeError> {
        self.insert_section("gaps", gap)
    }
    pub fn insert_task(&mut self, task: AcquisitionTask) -> Result<(), KnowledgeError> {
        self.refresh()?;
        self.ensure_unique(&task.id)?;
        validate_task_state(&task.state)?;
        if self.abox.find("gaps", &task.gap_id).is_none() {
            return Err(KnowledgeError::MissingTarget(task.gap_id));
        }
        if let Some(store) = &self.store {
            store.insert("acquisition_tasks", &json!(task))?;
        }
        self.tasks.insert(task.id.clone(), task);
        Ok(())
    }
    pub fn update_task_state(&mut self, id: &str, state: &str) -> Result<(), KnowledgeError> {
        self.refresh()?;
        validate_task_state(state)?;
        if !self.tasks.contains_key(id) {
            return Err(KnowledgeError::MissingTarget(id.into()));
        }
        if let Some(store) = &self.store {
            store.update_task(id, state)?;
        }
        self.tasks.get_mut(id).unwrap().state = state.into();
        Ok(())
    }
    pub fn task(&self, id: &str) -> Option<&AcquisitionTask> {
        self.tasks.get(id)
    }
    pub fn check_candidate(
        &self,
        universe: Option<CodeUniverse>,
    ) -> Result<Vec<Violation>, KnowledgeError> {
        if let Some(store) = &self.store {
            let snapshot = store.snapshot()?;
            return check_service_candidate(
                &snapshot.abox,
                &snapshot.decisions,
                &self.allowlist,
                universe,
            );
        }
        check_service_candidate(&self.abox, &self.decisions, &self.allowlist, universe)
    }
    pub fn promote_candidate(
        &mut self,
        id: &str,
        universe: Option<CodeUniverse>,
    ) -> Result<(), KnowledgeError> {
        self.refresh()?;
        // Freeze precisely the snapshot checked, even if another writer appends later.
        let violations =
            check_service_candidate(&self.abox, &self.decisions, &self.allowlist, universe)?;
        if !violations.is_empty() {
            return Err(KnowledgeError::ConstraintViolation(violations));
        }
        if let Some(store) = &self.store {
            store.promote(id, &self.abox)?;
        }
        self.promoted_candidates.insert(id.into());
        Ok(())
    }
    pub fn is_promoted(&self, id: &str) -> bool {
        self.promoted_candidates.contains(id)
    }
    fn insert_section(&mut self, section: &str, record: Value) -> Result<(), KnowledgeError> {
        if !SECTIONS.contains(&section) && !matches!(section, "observations" | "code_systems") {
            return Err(KnowledgeError::InvalidShape(section.into()));
        }
        self.refresh()?;
        self.ensure_unique(record_id(&record)?)?;
        if let Some(store) = &self.store {
            store.insert(section, &record)?;
        }
        self.abox.section_mut(section).push(record);
        Ok(())
    }
    fn ensure_unique(&self, id: &str) -> Result<(), KnowledgeError> {
        if self.abox.sections.values().any(|rows| {
            rows.iter()
                .any(|r| r.get("id").and_then(Value::as_str) == Some(id))
        }) || self.tasks.contains_key(id)
            || self.decisions.contains_key(id)
        {
            Err(KnowledgeError::DuplicateId(id.into()))
        } else {
            Ok(())
        }
    }
    fn check_raw_hashes(
        &self,
        record: &Value,
        allowlist: &ObservationAllowlist,
    ) -> Result<(), KnowledgeError> {
        check_evidence(&self.abox, record, allowlist, &mut BTreeSet::new())
    }
}
fn validate_task_state(state: &str) -> Result<(), KnowledgeError> {
    if matches!(
        state,
        "queued" | "running" | "done" | "failed" | "cancelled"
    ) {
        Ok(())
    } else {
        Err(KnowledgeError::InvalidShape(state.into()))
    }
}
fn validate_acceptance(
    record: &Value,
    decisions: &BTreeMap<String, ReviewDecision>,
) -> Result<(), KnowledgeError> {
    if record.get("review_status").and_then(Value::as_str) != Some("accepted") {
        return Ok(());
    }
    if record.get("origin").and_then(Value::as_str) == Some("fixture") {
        return Err(KnowledgeError::FixtureAccepted);
    }
    if record.get("origin").and_then(Value::as_str) != Some("pipeline") {
        return Err(KnowledgeError::InvalidShape("accepted origin".into()));
    }
    let id = record
        .get("review_decision_id")
        .and_then(Value::as_str)
        .ok_or(KnowledgeError::AcceptedWithoutDecision)?;
    if !decisions
        .get(id)
        .is_some_and(ReviewDecision::valid_for_acceptance)
        || record
            .pointer("/decision/by")
            .and_then(Value::as_str)
            .is_some_and(|by| by != "review_decision")
    {
        return Err(KnowledgeError::InvalidDecision);
    }
    Ok(())
}
fn canonical_conflict(mut record: Value) -> Result<Value, KnowledgeError> {
    if let Some(ids) = record.get("assertion_ids").cloned() {
        if record.get("assertions").is_some_and(|v| v != &ids) {
            return Err(KnowledgeError::InvalidShape(
                "conflicting member fields".into(),
            ));
        }
        record["assertions"] = ids;
        record.as_object_mut().unwrap().remove("assertion_ids");
    }
    Ok(record)
}
fn validate_conflict(abox: &Abox, record: &Value) -> Result<(), KnowledgeError> {
    let ids = record
        .get("assertions")
        .and_then(Value::as_array)
        .filter(|v| v.len() >= 2)
        .ok_or_else(|| KnowledgeError::InvalidShape("conflict needs two assertions".into()))?;
    let mut unique = BTreeSet::new();
    for id in ids {
        let id = id
            .as_str()
            .ok_or_else(|| KnowledgeError::InvalidShape("assertion id".into()))?;
        if !unique.insert(id) {
            return Err(KnowledgeError::InvalidShape(
                "duplicate conflict member".into(),
            ));
        }
        if abox.find("assertions", id).is_none() {
            return Err(KnowledgeError::MissingTarget(id.into()));
        }
    }
    Ok(())
}
fn record_id(record: &Value) -> Result<&str, KnowledgeError> {
    record
        .get("id")
        .and_then(Value::as_str)
        .ok_or(KnowledgeError::MissingId)
}
fn field_ref<'a>(
    record: &'a Value,
    canonical: &str,
    alias: &str,
) -> Result<&'a str, KnowledgeError> {
    record
        .get(canonical)
        .or_else(|| record.get(alias))
        .and_then(Value::as_str)
        .ok_or_else(|| KnowledgeError::InvalidShape(format!("missing {canonical}")))
}
fn resolve_raw(
    abox: &Abox,
    id: &str,
    allowlist: &ObservationAllowlist,
    visiting: &mut BTreeSet<String>,
) -> Result<(), KnowledgeError> {
    if !visiting.insert(id.into()) {
        return Err(KnowledgeError::InvalidShape("cyclic evidence".into()));
    }
    let (section, canonical, alias) = if id.starts_with("raw:") {
        ("raw_assets", "", "")
    } else if id.starts_with("seg:") {
        ("segments", "raw_asset_id", "raw_asset")
    } else if id.starts_with("clause:") {
        ("clauses", "segment_id", "segment")
    } else if id.starts_with("obs:") {
        ("observations", "raw_asset_id", "raw_asset")
    } else if id.starts_with("premium:") {
        ("premium_observations", "", "")
    } else {
        return Err(KnowledgeError::InvalidShape(
            "unsupported evidence reference".into(),
        ));
    };
    let row = abox
        .find(section, id)
        .ok_or_else(|| KnowledgeError::MissingTarget(id.into()))?;
    if section == "raw_assets" {
        validate_raw_asset(row, allowlist)?;
    } else if section == "premium_observations" {
        check_evidence(abox, row, allowlist, visiting)?;
    } else {
        resolve_raw(abox, field_ref(row, canonical, alias)?, allowlist, visiting)?;
    }
    visiting.remove(id);
    Ok(())
}
/// Raw assets are candidate members in their own right, so the allowlist applies to the
/// row itself and not only to the evidence chains that reach it.
fn validate_raw_asset(
    record: &Value,
    allowlist: &ObservationAllowlist,
) -> Result<(), KnowledgeError> {
    let id = record_id(record)?;
    let hash = field_ref(record, "sha256", "sha256")?;
    if !is_sha256(hash) || !allowlist.contains(hash) {
        return Err(KnowledgeError::HashNotObserved(hash.into()));
    }
    if id != format!("raw:sha256:{hash}") {
        return Err(KnowledgeError::InvalidShape(
            "raw asset id must be raw:sha256:<sha256>".into(),
        ));
    }
    Ok(())
}
fn check_evidence(
    abox: &Abox,
    record: &Value,
    allowlist: &ObservationAllowlist,
    visiting: &mut BTreeSet<String>,
) -> Result<(), KnowledgeError> {
    let evidence = record
        .get("evidence")
        .and_then(Value::as_array)
        .ok_or_else(|| KnowledgeError::InvalidShape("evidence array".into()))?;
    for e in evidence {
        resolve_raw(abox, field_ref(e, "ref", "ref")?, allowlist, visiting)?;
    }
    Ok(())
}
/// Resolve existing symlinks as well as lexical dot/parent components. Unresolvable
/// relative traversal is refused; prohibited directories also match absolute paths.
fn reject_fixture_path(path: &Path) -> Result<(), KnowledgeError> {
    fn forbidden(path: &Path) -> bool {
        let mut parts = Vec::new();
        for part in path.components() {
            match part {
                Component::ParentDir => {
                    parts.pop();
                }
                Component::Normal(p) => parts.push(p.to_string_lossy().into_owned()),
                _ => {}
            }
        }
        parts
            .windows(2)
            .any(|p| p == ["packages", "fixtures"] || p == ["docs", "blueprint"])
    }
    // Test the supplied path too: a symlink out of a forbidden tree is still input
    // from that tree. Canonicalize each existing ancestor for symlinked directories.
    if forbidden(path) {
        return Err(KnowledgeError::FixturePath);
    }
    let mut resolved = std::env::current_dir().map_err(|_| KnowledgeError::FixturePath)?;
    for component in path.components() {
        resolved.push(component.as_os_str());
        if let Ok(real) = resolved.canonicalize() {
            resolved = real;
        }
        if forbidden(&resolved) {
            return Err(KnowledgeError::FixturePath);
        }
    }
    if forbidden(&resolved) {
        Err(KnowledgeError::FixturePath)
    } else {
        Ok(())
    }
}
fn empty(value: Option<&Value>) -> bool {
    match value {
        None | Some(Value::Null) => true,
        Some(Value::Object(v)) => v.is_empty(),
        Some(Value::Array(v)) => v.is_empty(),
        Some(Value::String(v)) => v.is_empty(),
        _ => false,
    }
}
fn validate_premium(p: &Value) -> Result<(), KnowledgeError> {
    if p.get("raw_amount")
        .and_then(Value::as_i64)
        .is_none_or(|v| v <= 0)
        || empty(p.get("observed_at"))
        || empty(p.get("evidence"))
        || p.get("comparison_eligible")
            .and_then(Value::as_bool)
            .is_none()
    {
        return Err(KnowledgeError::InvalidPremium("required raw fields".into()));
    }
    if p.get("as_of")
        .is_some_and(|v| p.get("source_as_of") != Some(v))
    {
        return Err(KnowledgeError::InvalidPremium(
            "use canonical source_as_of".into(),
        ));
    }
    let missing = p
        .get("missing_dimensions")
        .and_then(Value::as_array)
        .ok_or_else(|| KnowledgeError::InvalidPremium("missing_dimensions".into()))?;
    let expected: BTreeSet<_> = [
        ("conditions", "conditions"),
        ("package_binding", "package_binding"),
        ("source_as_of", "as_of"),
    ]
    .into_iter()
    .filter(|(key, _)| empty(p.get(*key)))
    .map(|(_, name)| name)
    .collect();
    let actual: BTreeSet<_> = missing.iter().filter_map(Value::as_str).collect();
    if actual != expected || actual.len() != missing.len() {
        return Err(KnowledgeError::InvalidPremium(
            "inaccurate missing_dimensions".into(),
        ));
    }
    if p["comparison_eligible"] == true
        && (!expected.is_empty()
            || empty(p.get("comparison_basis_id"))
            || p["review_status"] != "accepted")
    {
        return Err(KnowledgeError::InvalidPremium(
            "ineligible comparison".into(),
        ));
    }
    Ok(())
}
/// Adapt canonical storage names at the ontology boundary; persisted data is untouched.
fn ontology_abox(abox: &Abox) -> Abox {
    let mut normalized = abox.clone();
    for row in normalized.section_mut("assertions") {
        if let Some(c) = row.get("criticality").and_then(Value::as_str) {
            row["criticality"] = json!(c.to_ascii_uppercase());
        }
        if let Some(v) = row.get("value").filter(|v| v.is_object()) {
            row["value"] = v
                .get("normalized")
                .or_else(|| v.get("raw"))
                .cloned()
                .unwrap_or(Value::Null);
        }
        if row.get("time").is_none() {
            row["time"] =
                json!({"valid_from":row.get("effective_from"),"valid_to":row.get("effective_to")});
        }
        if row.get("decision").is_none()
            && row.get("review_decision_id").is_some_and(|v| !v.is_null())
        {
            row["decision"] = json!({"by":"review_decision","ref":row["review_decision_id"]});
        }
    }
    for (section, pairs) in [
        ("segments", vec![("raw_asset_id", "raw_asset")]),
        ("clauses", vec![("segment_id", "segment")]),
        ("terms_editions", vec![("lineage_id", "lineage")]),
        ("premium_observations", vec![("source_as_of", "as_of")]),
    ] {
        for row in normalized.section_mut(section) {
            for (from, to) in &pairs {
                if let Some(v) = row.get(*from).cloned() {
                    row[*to] = v;
                }
            }
            if section == "segments" {
                if let Some(role) = row.get("doc_role").and_then(Value::as_str) {
                    let mapped = match role {
                        "terms" => "보통약관",
                        "rider_terms" => "특약 약관",
                        "annex" => "별표",
                        other => other,
                    };
                    row["doc_role"] = json!(mapped);
                }
            }
            if section == "segments"
                && (row.get("fingerprint_rule").is_some()
                    || row.get("fingerprint_sha256").is_some())
            {
                // SQL columns, including NULLs, are authoritative over extension aliases.
                row["fingerprint"] = if row.get("fingerprint_rule").is_some_and(Value::is_string)
                    && row.get("fingerprint_sha256").is_some_and(Value::is_string)
                {
                    json!({"rule":row["fingerprint_rule"],"sha256":row["fingerprint_sha256"]})
                } else {
                    Value::Null
                };
            }
        }
    }
    for row in normalized.section_mut("nodes") {
        // T-CT-05 rows always have `attrs` (default {}). Their `kind` column is the
        // class, even when an extension supplies a conflicting `class`. Only offline
        // ontology rows without `attrs` use `class` + an attribute such as kind=감액.
        if row.get("attrs").is_some() || row.get("class").is_none() {
            if let Some(kind) = row.get("kind").cloned() {
                row["class"] = kind;
            }
        }
        if let Some(attrs) = row.get("attrs").and_then(Value::as_object).cloned() {
            let object = row.as_object_mut().unwrap();
            for (k, v) in attrs {
                // Constrained columns stay authoritative. Every other attribute, including
                // the `kind` attribute K7 reads, is the ontology's value.
                if !NODE_COLUMNS.contains(&k.as_str()) {
                    object.insert(k, v);
                }
            }
        }
    }
    normalized
}
/// `public.node` columns an `attrs` entry may not override at the ontology boundary.
const NODE_COLUMNS: &[&str] = &[
    "id",
    "class",
    "label",
    "attrs",
    "origin",
    "onto_version",
    "recorded_at",
];
fn check_service_candidate(
    abox: &Abox,
    decisions: &BTreeMap<String, ReviewDecision>,
    allowlist: &ObservationAllowlist,
    universe: Option<CodeUniverse>,
) -> Result<Vec<Violation>, KnowledgeError> {
    let normalized = ontology_abox(abox);
    let view = candidate_view(&normalized)
        .map_err(|_| KnowledgeError::InvalidShape("candidate view".into()))?;
    let mut violations = check_constraints(&view, &CheckProfile::service_conformance(universe));
    // Raw assets become candidate members even when no assertion references them yet.
    for row in abox.section("raw_assets") {
        if let Err(e) = validate_raw_asset(row, allowlist) {
            violations.push(Violation::new("B4", record_id(row)?, e.to_string()));
        }
    }
    for section in ["assertions", "premium_observations"] {
        for row in abox.section(section) {
            let id = record_id(row)?;
            if let Err(e) = validate_acceptance(row, decisions) {
                violations.push(Violation::new("PROFILE", id, e.to_string()));
            }
            if let Err(e) = check_evidence(abox, row, allowlist, &mut BTreeSet::new()) {
                violations.push(Violation::new("B4", id, e.to_string()));
            }
            if section == "premium_observations" {
                if let Err(e) = validate_premium(row) {
                    violations.push(Violation::new("K13", id, e.to_string()));
                }
            }
        }
    }
    Ok(violations)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn candidate_rechecks_price_origin_and_review_in_degraded_snapshots() {
        let mut abox = Abox::default();
        let mut p = json!({"id":"premium:fixture_only","origin":"fixture","review_status":"accepted",
            "raw_amount":1,"observed_at":"2026-10-23T00:00:00Z","comparison_eligible":true,
            "conditions":{"age":40},"package_binding":"base","source_as_of":"2026-10-23",
            "comparison_basis_id":"fixture_only","missing_dimensions":[],"evidence":[]});
        abox.section_mut("premium_observations").push(p.clone());
        let violations = check_service_candidate(
            &abox,
            &BTreeMap::new(),
            &ObservationAllowlist::default(),
            None,
        )
        .unwrap();
        assert!(violations
            .iter()
            .any(|v| v.code == "PROFILE" && v.message == "FixtureAccepted"));
        p["origin"] = json!("pipeline");
        abox.section_mut("premium_observations")[0] = p;
        let violations = check_service_candidate(
            &abox,
            &BTreeMap::new(),
            &ObservationAllowlist::default(),
            None,
        )
        .unwrap();
        assert!(violations
            .iter()
            .any(|v| v.code == "PROFILE" && v.message == "AcceptedWithoutDecision"));
    }
}
