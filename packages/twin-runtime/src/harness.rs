//! The `case-runner` harness: stdin jobs in, JSON results out.
//!
//! Two job shapes:
//!
//! - **twin job** — the full input stage. `{case_id, abox, release?, configs[], cov,
//!   contract_date, facts{}, assume{}, outside[]}`. The A-box directory is read once,
//!   the named release (or a candidate view, when `release` is absent) is the snapshot,
//!   and the engine runs only when the chain links — rule bytes come from the snapshot,
//!   not the file system.
//! - **legacy job** — the absorbed verifier runner: `{case_id, rule_path, inputs}` goes
//!   straight to the engine and reports the same fields the old runner printed, plus
//!   `judgements` (always empty — there is no input stage on that path).
//!
//! `root` prefixes relative `abox`/`rule_path` values. No database, no network: the only
//! I/O is reading the A-box and legacy rule files the job names.

use crate::input_stage::OutsideInput;
use crate::resolve::{evaluate_request, Request, RequestOutcome};
use crate::snapshot::Snapshot;
use onjeon_ontology::{Abox, OntologyError};
use onjeon_rules_engine::Rule;
use serde_json::{json, Map, Value};
use std::fmt;
use std::path::{Path, PathBuf};

#[derive(Debug)]
pub enum HarnessError {
    Io(std::io::Error),
    Json(serde_json::Error),
    Ontology(OntologyError),
}

impl fmt::Display for HarnessError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            HarnessError::Io(e) => write!(f, "io: {e}"),
            HarnessError::Json(e) => write!(f, "json: {e}"),
            HarnessError::Ontology(e) => write!(f, "ontology: {e}"),
        }
    }
}

impl std::error::Error for HarnessError {}

impl From<std::io::Error> for HarnessError {
    fn from(e: std::io::Error) -> Self {
        HarnessError::Io(e)
    }
}
impl From<serde_json::Error> for HarnessError {
    fn from(e: serde_json::Error) -> Self {
        HarnessError::Json(e)
    }
}
impl From<OntologyError> for HarnessError {
    fn from(e: OntologyError) -> Self {
        HarnessError::Ontology(e)
    }
}

/// Runs the job list from `jobs_json` (a JSON array) under `root`; returns the results
/// as a JSON array. Each job fails on its own — one bad job never stops the rest.
pub fn run_jobs_str(jobs_json: &str, root: &Path) -> Result<Value, HarnessError> {
    let jobs: Value = serde_json::from_str(jobs_json)?;
    let list = jobs
        .as_array()
        .ok_or_else(|| HarnessError::Json(serde::de::Error::custom("jobs must be an array")))?;
    Ok(Value::Array(
        list.iter().map(|j| run_job(j, root)).collect(),
    ))
}

fn s<'a>(v: &'a Value, k: &str) -> Option<&'a str> {
    v.get(k).and_then(Value::as_str)
}

fn run_job(job: &Value, root: &Path) -> Value {
    let case_id = s(job, "case_id").unwrap_or("?").to_string();
    let out = if job.get("rule_path").is_some() {
        run_legacy(job, root)
    } else {
        run_twin(job, root)
    };
    let mut o = out.unwrap_or_else(
        |e| json!({"outcome": "job_error", "error": e.to_string(), "engine_calls": 0}),
    );
    o.as_object_mut()
        .expect("object")
        .insert("case_id".to_string(), json!(case_id));
    o
}

fn legacy_engine_fields(rule: &Rule, r: &onjeon_rules_engine::EvaluationResult) -> Value {
    json!({
        "rule_id": r.rule_id,
        "rule_version": r.rule_version,
        "release_id": r.release_id,
        "rule_content_hash": r.rule_content_hash,
        "publication_state": rule.publication_state(),
        "schema_version": r.schema_version,
        "evidence_refs": r.evidence_refs,
        "engine_version": r.engine_version,
        "eligibility": serde_json::to_value(r.eligibility).expect("tri serializes"),
        "payout": serde_json::to_value(&r.payout).expect("payout serializes"),
        "contract_effect": serde_json::to_value(&r.contract_effect).expect("effect serializes"),
        "missing_inputs": r.missing_inputs,
        "input_snapshot_hash": r.input_snapshot_hash,
        "trace_len": r.trace.len(),
        "trace_head": r.trace.iter().take(6).map(|t| json!({"path": t.path, "op": t.op, "result": t.result})).collect::<Vec<_>>(),
    })
}

/// The absorbed verifier job: `{case_id, rule_path, inputs}` → engine result.
fn run_legacy(job: &Value, root: &Path) -> Result<Value, HarnessError> {
    let path: PathBuf = root.join(s(job, "rule_path").expect("rule_path"));
    let text = std::fs::read_to_string(&path).map_err(|e| {
        HarnessError::Io(std::io::Error::new(
            e.kind(),
            format!("{}: {e}", path.display()),
        ))
    })?;
    let rule = match Rule::from_json_str(&text) {
        Ok(r) => r,
        Err(e) => {
            return Ok(json!({
                "outcome": "load_error", "error": format!("{e}"),
                "engine_calls": 0, "judgements": [],
            }))
        }
    };
    let inputs = job.get("inputs").cloned().unwrap_or(Value::Null);
    match rule.evaluate(&inputs) {
        Ok(r) => Ok(json!({
            "outcome": "evaluated",
            "engine_calls": 1,
            "judgements": [],
            "engine": legacy_engine_fields(&rule, &r),
        })),
        Err(e) => Ok(json!({
            "outcome": "eval_error", "error": format!("{e:?}"),
            "engine_calls": 1, "judgements": [],
        })),
    }
}

fn run_twin(job: &Value, root: &Path) -> Result<Value, HarnessError> {
    let missing =
        |k: &str| HarnessError::Json(serde::de::Error::custom(format!("job needs `{k}`")));
    let abox_dir = root.join(s(job, "abox").ok_or_else(|| missing("abox"))?);
    let abox = Abox::from_dir(&abox_dir)?;
    let snap = match s(job, "release") {
        Some(rel) => Snapshot::release(&abox, rel)?,
        None => Snapshot::candidate(&abox)?,
    };
    let configs: Vec<String> = job
        .get("configs")
        .and_then(Value::as_array)
        .ok_or_else(|| missing("configs"))?
        .iter()
        .filter_map(|c| c.as_str().map(str::to_string))
        .collect();
    let contract_date = s(job, "contract_date")
        .or_else(|| job.pointer("/facts/contract_date").and_then(Value::as_str))
        .ok_or_else(|| missing("contract_date"))?;
    let cov = s(job, "cov").ok_or_else(|| missing("cov"))?;
    let outside: Vec<OutsideInput> = match job.get("outside") {
        None | Some(Value::Null) => Vec::new(),
        Some(v) => serde_json::from_value(v.clone())?,
    };
    // flat facts: assumptions ∪ facts ∪ contract_date (the rule sees one input map)
    let mut facts: Map<String, Value> = job
        .get("assume")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    if let Some(f) = job.get("facts").and_then(Value::as_object) {
        facts.extend(f.iter().map(|(k, v)| (k.clone(), v.clone())));
    }
    facts.insert("contract_date".to_string(), json!(contract_date));
    let cfg_refs: Vec<&str> = configs.iter().map(String::as_str).collect();
    let out = evaluate_request(
        &snap,
        &Request {
            candidates: &cfg_refs,
            contract_date,
            coverage: cov,
            outside: &outside,
            facts: &facts,
        },
    );
    Ok(twin_result(&snap, job, &out))
}

fn twin_result(snap: &Snapshot, job: &Value, out: &RequestOutcome) -> Value {
    let mut o = Map::new();
    o.insert(
        "release_id".into(),
        snap.release_id.clone().map_or(Value::Null, Value::String),
    );
    let k15 = snap.integrity_findings().len();
    if k15 > 0 {
        o.insert("integrity_findings".into(), json!(k15));
    }
    o.insert("engine_calls".into(), json!(out.engine_calls));
    match &out.chain {
        crate::Chain::Linked(l) => {
            o.insert(
                "chain".into(),
                json!({
                    "outcome": "linked",
                    "sales_config": l.sales_config,
                    "edition": l.edition,
                    "coverage": l.coverage,
                    "category": l.category,
                    "rule_assertion": l.rule_assertion,
                    "rule_path": l.rule_path,
                    "link_assertions": l.link_assertions,
                }),
            );
        }
        crate::Chain::Blocked(b) => {
            o.insert(
                "chain".into(),
                json!({
                    "outcome": "blocked",
                    "reason": b.reason.as_str(),
                    "held": b.held,
                    "sales_config": b.sales_config,
                }),
            );
        }
    }
    o.insert(
        "judgements".into(),
        serde_json::to_value(&out.judgements).expect("judgements serialize"),
    );
    if let Some(f) = &out.filled {
        o.insert("inputs".into(), Value::Object(f.inputs.clone()));
    }
    let outcome = match (&out.eval, &out.pre_engine_error) {
        (Some(Ok(_)), _) => "evaluated",
        (Some(Err(_)), _) => "eval_error",
        (None, Some(_)) if out.chain.linked().is_some() => "pre_engine_error",
        _ => "blocked",
    };
    o.insert("outcome".into(), json!(outcome));
    match &out.eval {
        Some(Ok(r)) => {
            if let Some(rule) = &out.rule {
                o.insert("engine".into(), legacy_engine_fields(rule, r));
            }
        }
        Some(Err(e)) => {
            o.insert("error".into(), json!(format!("{e:?}")));
        }
        None => {
            if let Some(e) = &out.pre_engine_error {
                o.insert("error".into(), json!(e));
            }
        }
    }
    let _ = job;
    Value::Object(o)
}
