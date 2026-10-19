//! The input-stage link check (02_구현계약 §1.7, C-26) on the service side.
//!
//! [`resolve_chain`] answers the question for one already-selected sales configuration
//! and delegates to the ontology reference implementation. [`resolve_request`] runs the
//! whole front of the pipeline — [`config_select`] first, then the chain — and folds a
//! selection block into the same `Chain` type, so a caller has exactly one result and a
//! blocked result always means zero engine calls.

use crate::config_select::{config_select, ConfigSelection};
use crate::input_stage::{fill, FillRequest, OutsideInput, StageJudgement};
use crate::snapshot::Snapshot;
use onjeon_ontology::{resolve_chain as onto_resolve, Blocked, Chain};
use onjeon_rules_engine::{EvaluationResult, Rule};
use serde_json::{Map, Value};

/// Links the request to a rule, or says why it is held, for the sales configuration
/// `config` (already chosen). The coverage the request names is never trusted on its
/// own: it must be defined in an edition this configuration uses on `as_of`.
pub fn resolve_chain(snap: &Snapshot, config: &str, as_of: &str, requested_cov: &str) -> Chain {
    onto_resolve(snap.view(), &[config], as_of, requested_cov)
}

/// Selection plus link check: picks the one sales configuration applicable on
/// `contract_date` out of `candidates`, then links coverage to rule.
pub fn resolve_request(
    snap: &Snapshot,
    candidates: &[&str],
    contract_date: &str,
    requested_cov: &str,
) -> Chain {
    match config_select(snap, candidates, contract_date) {
        ConfigSelection::Selected { sales_config, .. } => {
            resolve_chain(snap, &sales_config, contract_date, requested_cov)
        }
        ConfigSelection::Blocked(b) => {
            let mut held: Vec<String> = match &b {
                crate::config_select::ConfigBlock::MultipleCandidates { candidates, .. } => {
                    vec![format!("판매본 후보 복수: {}", candidates.join(","))]
                }
                crate::config_select::ConfigBlock::NoApplicableConfig { .. } => {
                    vec!["판매본 미확인".to_string()]
                }
            };
            held.extend(b.held().iter().map(|h| {
                if h.applies_on_date {
                    format!("{}:{}", h.assertion_id, h.status)
                } else {
                    format!("{}:not_valid_on {}", h.assertion_id, contract_date)
                }
            }));
            Chain::Blocked(Blocked {
                reason: b.reason(),
                held,
                sales_config: None,
            })
        }
    }
}

/// One scenario request: candidates and the contract date that selects between them, the
/// coverage asked about, the outside-DSL declaration of the rule, and the flat facts.
pub struct Request<'a> {
    pub candidates: &'a [&'a str],
    /// The contract date (`YYYY-MM-DD`); picks the sales configuration and the links in force.
    pub contract_date: &'a str,
    pub coverage: &'a str,
    /// The rule's `inputs_from_outside_dsl` (C-08). Empty: every input is a plain fact.
    pub outside: &'a [OutsideInput],
    /// Flat facts: assumptions merged with `contract_date`, `diagnosis_date`, `dx_code`, ...
    pub facts: &'a Map<String, Value>,
}

/// Everything one request produced: the chain, the judgements, the engine result and how
/// many times the engine ran (always 0 when the chain is blocked).
pub struct RequestOutcome {
    pub chain: Chain,
    /// The loaded rule and the filled inputs, when the chain linked.
    pub filled: Option<crate::input_stage::Filled>,
    pub judgements: Vec<StageJudgement>,
    /// The engine result, when the chain linked and the rule was evaluated.
    pub eval: Option<Result<EvaluationResult, onjeon_rules_engine::EvalError>>,
    /// The rule the engine ran (kept for its hash/version/publication_state).
    pub rule: Option<Rule>,
    /// Why the linked chain still produced no engine call (rule bytes absent from the
    /// snapshot, rule failed to load, or `fill` refused).
    pub pre_engine_error: Option<String>,
    pub engine_calls: usize,
}

/// Runs one request end to end: selection → link check → fill → engine. A blocked chain
/// short-circuits before the engine; a rule is read only from bytes the snapshot pinned.
pub fn evaluate_request(snap: &Snapshot, req: &Request<'_>) -> RequestOutcome {
    let chain = resolve_request(snap, req.candidates, req.contract_date, req.coverage);
    let Chain::Linked(linked) = &chain else {
        return RequestOutcome {
            chain,
            filled: None,
            judgements: Vec::new(),
            eval: None,
            rule: None,
            pre_engine_error: None,
            engine_calls: 0,
        };
    };
    let fail = |e: String| RequestOutcome {
        chain: chain.clone(),
        filled: None,
        judgements: Vec::new(),
        eval: None,
        rule: None,
        pre_engine_error: Some(e),
        engine_calls: 0,
    };
    let Some(bytes) = snap.rule_bytes(&linked.rule_path) else {
        return fail(format!(
            "{}: rule file absent from snapshot",
            linked.rule_path
        ));
    };
    let rule = match std::str::from_utf8(bytes)
        .map_err(|e| e.to_string())
        .and_then(|t| Rule::from_json_str(t).map_err(|e| e.to_string()))
    {
        Ok(r) => r,
        Err(e) => return fail(format!("{}: rule load failed: {e}", linked.rule_path)),
    };
    let filled = match fill(
        req.outside,
        &FillRequest {
            snapshot: snap,
            linked,
            rule: &rule,
            facts: req.facts,
        },
    ) {
        Ok(f) => f,
        Err(e) => return fail(format!("fill: {e}")),
    };
    let eval = rule.evaluate(&Value::Object(filled.inputs.clone()));
    RequestOutcome {
        chain,
        judgements: filled.judgements.clone(),
        filled: Some(filled),
        eval: Some(eval),
        rule: Some(rule),
        pre_engine_error: None,
        engine_calls: 1,
    }
}
