//! AI gateway (T-KN-03, 제3부 §47.3, 02_구현계약 C-19).
//!
//! Provider SDKs are called only from adapters implementing [`Provider`]; no
//! other workspace crate may depend on one (test `provider_sdk_only_here`).
//! This crate ships no SDK adapter yet: real adapters arrive with the
//! provider decision (D-02), and [`fixture_only`] is the only implementation.
//!
//! Operating rule 7: this crate only calls models. Which family writes,
//! approves or red-teams knowledge is `review_policy.json`'s business and has
//! nothing to do with the development role table; nothing here reads either.
//!
//! Guarantees:
//! - every provider call yields one [`CallRecord`] (C-19) holding labels,
//!   a model-ref hash, versions, cost, latency and run id, and never the
//!   prompt, the model output or any user document text;
//! - output must satisfy the caller's JSON Schema; after the retry limit the
//!   result is [`Outcome::Unresolved`], never a guessed value;
//! - a monthly cap and a per-user daily cap, once reached, return
//!   `ONJ-AP-L-020` with `degraded = true` (shown, not hidden) before any
//!   further provider call.
//!
//! Costs are integer micro-units; no floating point.

pub mod fixture_only;
pub mod schema;

use onjeon_contracts::{ErrorClass, ErrorResponse, ModelVersion};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::sync::Mutex;
use std::time::Instant;

/// Error code for exceeding an AI call cost cap (02_구현계약 §4).
pub const CODE_COST_CAP: &str = "ONJ-AP-L-020";

/// What a provider adapter returns for one call.
#[derive(Debug, Clone)]
pub struct ProviderReply {
    /// Raw model text, expected to be JSON. Never stored by the gateway.
    pub text: String,
    /// Provider's model reference. Only its hash leaves the gateway.
    pub model_ref: String,
    pub cost_micro_units: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProviderError {
    pub retryable: bool,
}

/// One model family behind the gateway. SDK calls live only in implementors.
pub trait Provider: Send + Sync {
    /// Family label such as a vendor family name; not a model identifier.
    fn family_label(&self) -> &str;
    fn complete(&self, prompt: &str) -> Result<ProviderReply, ProviderError>;
}

#[derive(Debug, Clone)]
pub struct Limits {
    pub monthly_cap_micro_units: u64,
    pub user_daily_cap_micro_units: u64,
    /// Extra attempts after the first when output fails schema or the provider
    /// reports a retryable error.
    pub max_retries: u32,
}

/// Calendar keys come from the caller so the gateway has no clock dependency.
#[derive(Debug, Clone)]
pub struct Request<'a> {
    pub run_id: &'a str,
    pub user_id: Option<&'a str>,
    /// `YYYY-MM`
    pub month: &'a str,
    /// `YYYY-MM-DD`
    pub day: &'a str,
    pub prompt_version: &'a str,
    pub schema_version: &'a str,
    pub schema: &'a serde_json::Value,
    /// Passed to the provider only; never recorded.
    pub prompt: &'a str,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AttemptStatus {
    Ok,
    SchemaInvalid,
    ProviderError,
}

/// C-19 call record. Contains no prompt, output or document text.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CallRecord {
    pub model: ModelVersion,
    pub schema_version: String,
    pub cost_micro_units: u64,
    pub latency_ms: u64,
    pub run_id: String,
    pub attempt: u32,
    pub status: AttemptStatus,
}

#[derive(Debug, Clone, PartialEq)]
pub enum Outcome {
    Resolved(serde_json::Value),
    /// Retry limit reached without schema-valid output.
    Unresolved,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Degraded {
    /// `ONJ-AP-L-020`
    pub error: ErrorResponse,
    /// Always true: callers must show the reduced mode (cache or deferral).
    pub degraded: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub enum GatewayError {
    CapExceeded(Degraded),
    UnknownFamily,
    /// The caller's schema uses keywords the validator cannot enforce; no provider was called.
    UnsupportedSchema(Vec<String>),
}

#[derive(Default)]
struct State {
    month: BTreeMap<String, u64>,
    user_day: BTreeMap<(String, String), u64>,
    records: Vec<CallRecord>,
}

pub struct Gateway {
    providers: Vec<Box<dyn Provider>>,
    limits: Limits,
    state: Mutex<State>,
}

pub fn model_ref_hash(model_ref: &str) -> String {
    Sha256::digest(model_ref.as_bytes())
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

impl Gateway {
    pub fn new(providers: Vec<Box<dyn Provider>>, limits: Limits) -> Self {
        Self {
            providers,
            limits,
            state: Mutex::new(State::default()),
        }
    }

    pub fn families(&self) -> Vec<&str> {
        self.providers.iter().map(|p| p.family_label()).collect()
    }

    /// Snapshot of all call records so far (feeds the control console).
    pub fn records(&self) -> Vec<CallRecord> {
        self.state.lock().unwrap().records.clone()
    }

    fn cap_hit(&self, req: &Request) -> bool {
        let s = self.state.lock().unwrap();
        let month = s.month.get(req.month).copied().unwrap_or(0);
        let user = req
            .user_id
            .and_then(|u| {
                s.user_day
                    .get(&(u.to_string(), req.day.to_string()))
                    .copied()
            })
            .unwrap_or(0);
        month >= self.limits.monthly_cap_micro_units
            || (req.user_id.is_some() && user >= self.limits.user_daily_cap_micro_units)
    }

    fn degraded(req: &Request) -> GatewayError {
        GatewayError::CapExceeded(Degraded {
            error: ErrorResponse {
                error_class: ErrorClass::Limit,
                code: CODE_COST_CAP.to_string(),
                message_key: "ai_cost_cap_degraded".to_string(),
                retryable: false,
                trace_id: req.run_id.to_string(),
            },
            degraded: true,
        })
    }

    /// Calls one family. The cap is checked before every attempt, so a call
    /// that crosses the cap stops further retries instead of overspending.
    pub fn call(&self, family: &str, req: &Request) -> Result<Outcome, GatewayError> {
        let provider = self
            .providers
            .iter()
            .find(|p| p.family_label() == family)
            .ok_or(GatewayError::UnknownFamily)?;
        let bad = schema::unsupported(req.schema);
        if !bad.is_empty() {
            return Err(GatewayError::UnsupportedSchema(bad));
        }
        for attempt in 0..=self.limits.max_retries {
            if self.cap_hit(req) {
                return Err(Self::degraded(req));
            }
            let started = Instant::now();
            let reply = provider.complete(req.prompt);
            let latency_ms = started.elapsed().as_millis() as u64;
            let mut retry = true;
            let (status, cost, model_ref, parsed) = match reply {
                Err(e) => {
                    retry = e.retryable;
                    (AttemptStatus::ProviderError, 0, None, None)
                }
                Ok(r) => {
                    let ok = serde_json::from_str::<serde_json::Value>(&r.text)
                        .ok()
                        .filter(|v| schema::validate(req.schema, v).is_empty());
                    let st = if ok.is_some() {
                        AttemptStatus::Ok
                    } else {
                        AttemptStatus::SchemaInvalid
                    };
                    (st, r.cost_micro_units, Some(r.model_ref), ok)
                }
            };
            {
                let mut s = self.state.lock().unwrap();
                let m = s.month.entry(req.month.to_string()).or_default();
                *m = m.saturating_add(cost);
                if let Some(u) = req.user_id {
                    let d = s
                        .user_day
                        .entry((u.to_string(), req.day.to_string()))
                        .or_default();
                    *d = d.saturating_add(cost);
                }
                s.records.push(CallRecord {
                    model: ModelVersion {
                        provider_family_label: family.to_string(),
                        model_ref_hash: model_ref
                            .as_deref()
                            .map(model_ref_hash)
                            .unwrap_or_default(),
                        prompt_version: req.prompt_version.to_string(),
                    },
                    schema_version: req.schema_version.to_string(),
                    cost_micro_units: cost,
                    latency_ms,
                    run_id: req.run_id.to_string(),
                    attempt,
                    status,
                });
            }
            if let Some(v) = parsed {
                return Ok(Outcome::Resolved(v));
            }
            if !retry {
                break;
            }
        }
        Ok(Outcome::Unresolved)
    }
}
