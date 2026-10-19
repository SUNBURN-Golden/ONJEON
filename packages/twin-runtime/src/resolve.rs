//! The input-stage link check (02_구현계약 §1.7, C-26) on the service side.
//!
//! [`resolve_chain`] answers the question for one already-selected sales configuration
//! and delegates to the ontology reference implementation; [`resolve_request`] runs the
//! whole front of the pipeline — [`config_select`] first, then the chain — and folds a
//! selection block into the same `Chain` type, so a caller has exactly one result and a
//! blocked result always means zero engine calls.
//!
//! The [`BlockReason`] set is exactly the contract's (§1.7): the ontology checker has
//! one extra internal reason, `simulate_blocked` (unaccepted C0 claims around the
//! coverage, or an unresolved conflict — the claims a rule would execute on are not all
//! approved), which surfaces here as `link_unapproved` with the specifics kept in
//! `held`. A `Blocked` reason is therefore always one of the ten contract reasons.
//!
//! [`evaluate_request`] gates before the chain: K15 release-integrity findings on the
//! snapshot block immediately (a tampered member or a swapped rule file can never reach
//! the engine), and a malformed `contract_date` is rejected rather than silently
//! mis-selecting the sales configuration. The judged-input declaration a rule needs is
//! read from the rule artifact itself ([`load_rule_artifact`]), never from the request.

use crate::config_select::{config_select, ConfigSelection};
use crate::input_stage::{fill, load_rule_artifact, FillRequest, StageJudgement};
use crate::snapshot::Snapshot;
use onjeon_ontology::{resolve_chain as onto_resolve, Linked, Violation};
use onjeon_rules_engine::{EvaluationResult, Rule};
use serde_json::{json, Map, Value};

/// Why a request is held — exactly the contract's reasons (02_구현계약 §1.7).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BlockReason {
    NoUsesEdition,
    MultipleCandidates,
    ScopeUnknown,
    ApplicationScopeUnverified,
    AppliesFromOtherEditionUnmodeled,
    CompetingEditions,
    LinkUnapproved,
    EditionIdentityUnconfirmed,
    CovNotInEdition,
    NoRule,
}

impl BlockReason {
    pub fn as_str(self) -> &'static str {
        match self {
            BlockReason::NoUsesEdition => "no_uses_edition",
            BlockReason::MultipleCandidates => "multiple_candidates",
            BlockReason::ScopeUnknown => "scope_unknown",
            BlockReason::ApplicationScopeUnverified => "application_scope_unverified",
            BlockReason::AppliesFromOtherEditionUnmodeled => "applies_from_other_edition_unmodeled",
            BlockReason::CompetingEditions => "competing_editions",
            BlockReason::LinkUnapproved => "link_unapproved",
            BlockReason::EditionIdentityUnconfirmed => "edition_identity_unconfirmed",
            BlockReason::CovNotInEdition => "cov_not_in_edition",
            BlockReason::NoRule => "no_rule",
        }
    }

    fn from_ontology(r: onjeon_ontology::BlockReason) -> BlockReason {
        use onjeon_ontology::BlockReason as O;
        match r {
            O::NoUsesEdition => BlockReason::NoUsesEdition,
            O::MultipleCandidates => BlockReason::MultipleCandidates,
            O::ScopeUnknown => BlockReason::ScopeUnknown,
            O::ApplicationScopeUnverified => BlockReason::ApplicationScopeUnverified,
            O::AppliesFromOtherEditionUnmodeled => BlockReason::AppliesFromOtherEditionUnmodeled,
            O::CompetingEditions => BlockReason::CompetingEditions,
            O::LinkUnapproved => BlockReason::LinkUnapproved,
            O::EditionIdentityUnconfirmed => BlockReason::EditionIdentityUnconfirmed,
            O::CovNotInEdition => BlockReason::CovNotInEdition,
            O::NoRule => BlockReason::NoRule,
            // unaccepted C0 claims / an unresolved conflict mean the claims the rule
            // would execute on are not approved — on the service surface that is an
            // unapproved link; `held` keeps the assertion ids and the conflict note
            O::SimulateBlocked => BlockReason::LinkUnapproved,
        }
    }
}

/// What held the conclusion back (assertion ids with status, unmet conditions).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Blocked {
    pub reason: BlockReason,
    pub held: Vec<String>,
    pub sales_config: Option<String>,
}

/// The link check's answer: a rule to run, or the contract reason the request holds.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Chain {
    Linked(Linked),
    Blocked(Blocked),
}

impl Chain {
    pub fn linked(&self) -> Option<&Linked> {
        match self {
            Chain::Linked(l) => Some(l),
            Chain::Blocked(_) => None,
        }
    }

    pub fn blocked(&self) -> Option<&Blocked> {
        match self {
            Chain::Linked(_) => None,
            Chain::Blocked(b) => Some(b),
        }
    }
}

fn convert(c: onjeon_ontology::Chain) -> Chain {
    match c {
        onjeon_ontology::Chain::Linked(l) => Chain::Linked(l),
        onjeon_ontology::Chain::Blocked(b) => Chain::Blocked(Blocked {
            reason: BlockReason::from_ontology(b.reason),
            held: b.held,
            sales_config: b.sales_config,
        }),
    }
}

/// Links the request to a rule, or says why it is held, for the sales configuration
/// `config` (already chosen). The coverage the request names is never trusted on its
/// own: it must be defined in an edition this configuration uses on `as_of`.
pub fn resolve_chain(snap: &Snapshot, config: &str, as_of: &str, requested_cov: &str) -> Chain {
    convert(onto_resolve(snap.view(), &[config], as_of, requested_cov))
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

/// One scenario request: candidate sales configurations, the contract date that selects
/// between them, the coverage asked about, and the flat facts. The judged inputs a rule
/// needs are declared by the rule artifact (`inputs_from_outside_dsl`, C-08), not by
/// the request.
pub struct Request<'a> {
    pub candidates: &'a [&'a str],
    /// The contract date (`YYYY-MM-DD`); picks the sales configuration and the links in force.
    pub contract_date: &'a str,
    pub coverage: &'a str,
    /// Flat facts: assumptions merged with `contract_date`, `diagnosis_date`, `dx_code`, ...
    /// A `contract_date` key absent here is filled from `contract_date`.
    pub facts: &'a Map<String, Value>,
}

/// Everything one request produced: the chain, the judgements, the engine result and how
/// many times the engine ran (always 0 when the chain is blocked or a gate stopped first).
pub struct RequestOutcome {
    /// K15 release-integrity findings of the snapshot. Non-empty means the run stopped
    /// before the chain — a missing member, an in-place edit or a swapped rule file
    /// blocks immediately (02_구현계약 §1.3), not merely after computing.
    pub integrity_findings: Vec<Violation>,
    /// A malformed request rejected before the chain (e.g. `contract_date` not a date).
    pub request_error: Option<String>,
    /// The link-check result — `None` when a gate above stopped the run first.
    pub chain: Option<Chain>,
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

impl RequestOutcome {
    fn gated(integrity_findings: Vec<Violation>, request_error: Option<String>) -> RequestOutcome {
        RequestOutcome {
            integrity_findings,
            request_error,
            chain: None,
            filled: None,
            judgements: Vec::new(),
            eval: None,
            rule: None,
            pre_engine_error: None,
            engine_calls: 0,
        }
    }
}

/// Runs one request end to end: gates → selection → link check → fill → engine. A K15
/// integrity finding or a malformed request stops before the chain; a blocked chain
/// short-circuits before the engine; a rule is read only from bytes the snapshot pinned,
/// and its `inputs_from_outside_dsl` declaration is part of those bytes (C-08).
pub fn evaluate_request(snap: &Snapshot, req: &Request<'_>) -> RequestOutcome {
    if !snap.integrity_findings().is_empty() {
        return RequestOutcome::gated(snap.integrity_findings().to_vec(), None);
    }
    if onjeon_rules_engine::date::parse_date(req.contract_date).is_none() {
        return RequestOutcome::gated(
            Vec::new(),
            Some(format!(
                "contract_date is not a date: {}",
                req.contract_date
            )),
        );
    }
    let chain = resolve_request(snap, req.candidates, req.contract_date, req.coverage);
    let Chain::Linked(linked) = &chain else {
        return RequestOutcome {
            integrity_findings: Vec::new(),
            request_error: None,
            chain: Some(chain),
            filled: None,
            judgements: Vec::new(),
            eval: None,
            rule: None,
            pre_engine_error: None,
            engine_calls: 0,
        };
    };
    let fail = |e: String| RequestOutcome {
        integrity_findings: Vec::new(),
        request_error: None,
        chain: Some(chain.clone()),
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
    let (rule, outside) = match load_rule_artifact(bytes) {
        Ok(x) => x,
        Err(e) => return fail(format!("{}: rule load failed: {e}", linked.rule_path)),
    };
    let mut facts = req.facts.clone();
    facts
        .entry("contract_date".to_string())
        .or_insert_with(|| json!(req.contract_date));
    let filled = match fill(
        &outside,
        &FillRequest {
            snapshot: snap,
            linked,
            rule: &rule,
            facts: &facts,
        },
    ) {
        Ok(f) => f,
        Err(e) => return fail(format!("fill: {e}")),
    };
    let eval = rule.evaluate(&Value::Object(filled.inputs.clone()));
    RequestOutcome {
        integrity_findings: Vec::new(),
        request_error: None,
        chain: Some(chain),
        judgements: filled.judgements.clone(),
        filled: Some(filled),
        eval: Some(eval),
        rule: Some(rule),
        pre_engine_error: None,
        engine_calls: 1,
    }
}
