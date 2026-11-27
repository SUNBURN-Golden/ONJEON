//! The in-process calculation handler for scenario API callers. The caller supplies the
//! resolved scenario context and the release metadata. The twin runtime checks the
//! snapshot and coverage links before evaluating.

use onjeon_api_types::{EvaluationRequest, ScenarioRequest};
use onjeon_contracts::{
    BlockedBy, DisplayStatus, Explain, InputJudgement, ResultState, ScenarioResult,
};
use onjeon_rules_engine::confirmed_empty_class_money_list;
use onjeon_twin_runtime::{evaluate_request, Chain, Request, Snapshot};
use serde_json::{Map, Value};
use std::collections::BTreeMap;

type Facts = BTreeMap<String, Value>;

pub struct ScenarioContext<'a> {
    pub snapshot: &'a Snapshot,
    pub candidates: &'a [&'a str],
    pub contract_date: &'a str,
    pub result_state: ResultState,
    /// Facts verified by the caller for this coverage, event window and scenario.
    /// An empty list here requires an explicit user confirmation or complete evidence.
    pub verified_facts: &'a Facts,
    /// Status supplied by the caller for results with all required inputs.
    pub display_status: DisplayStatus,
}

#[derive(Debug)]
pub enum ScenarioError {
    ReleaseRequired,
    Integrity,
    Request(String),
    InputStage(String),
    Evaluation(onjeon_rules_engine::EvalError),
    Contract(serde_json::Error),
}

/// Calculation for `POST /v1/scenarios` after release and scenario selection.
pub fn create_scenario(
    ctx: &ScenarioContext<'_>,
    req: &ScenarioRequest,
) -> Result<ScenarioResult, ScenarioError> {
    let facts = prepare_facts(
        &req.facts,
        req.assumptions.as_ref(),
        None,
        ctx.verified_facts,
    );
    evaluate(ctx, &req.cov_id, &facts)
}

/// Calculation for one selected coverage in `POST /v1/me/evaluations`.
pub fn evaluate_coverage(
    ctx: &ScenarioContext<'_>,
    coverage: &str,
    req: &EvaluationRequest,
) -> Result<ScenarioResult, ScenarioError> {
    let facts = prepare_facts(
        &req.scenario.facts,
        req.scenario.assumptions.as_ref(),
        req.confirmed_facts.as_ref(),
        ctx.verified_facts,
    );
    evaluate(ctx, coverage, &facts)
}

fn prepare_facts(
    facts: &Facts,
    assumptions: Option<&Facts>,
    confirmed: Option<&Facts>,
    verified: &Facts,
) -> Map<String, Value> {
    let empty_list = confirmed_empty_class_money_list();
    let from_source = |(key, value): (&String, &Value), explicit| {
        let empty_array = value.as_array().is_some_and(Vec::is_empty);
        let value = match (empty_array, explicit) {
            (true, true) => empty_list.clone(),
            (true, false) => Value::Null,
            // The engine's marker is minted here from a recognized source.
            (false, _) if value == &empty_list => Value::Null,
            (false, _) => value.clone(),
        };
        (key.clone(), value)
    };
    assumptions
        .into_iter()
        .flatten()
        .map(|fact| from_source(fact, true))
        .chain(facts.iter().map(|fact| from_source(fact, false)))
        .chain(
            confirmed
                .into_iter()
                .flatten()
                .map(|fact| from_source(fact, true)),
        )
        .chain(verified.iter().map(|fact| from_source(fact, true)))
        .collect()
}

fn evaluate(
    ctx: &ScenarioContext<'_>,
    coverage: &str,
    facts: &Map<String, Value>,
) -> Result<ScenarioResult, ScenarioError> {
    let release_id = ctx
        .snapshot
        .release_id
        .clone()
        .ok_or(ScenarioError::ReleaseRequired)?;
    let outcome = evaluate_request(
        ctx.snapshot,
        &Request {
            candidates: ctx.candidates,
            contract_date: ctx.contract_date,
            coverage,
            facts,
        },
    );
    if !outcome.integrity_findings.is_empty() {
        return Err(ScenarioError::Integrity);
    }
    if let Some(error) = outcome.request_error {
        return Err(ScenarioError::Request(error));
    }
    if let Some(error) = outcome.pre_engine_error {
        return Err(ScenarioError::InputStage(error));
    }

    let mut result = ScenarioResult {
        release_id,
        cov_id: coverage.to_owned(),
        evaluation: None,
        judgements: outcome
            .judgements
            .into_iter()
            .map(|j| InputJudgement {
                input_name: j.input_name,
                value: j.value,
                judged_by: j.judged_by.as_str().to_owned(),
                evidence_assertion_ids: j.evidence_assertion_ids,
            })
            .collect(),
        blocked_by: Vec::new(),
        remaining_gaps: Vec::new(),
        explain: None,
        display_status: ctx.display_status,
        result_state: ctx.result_state.clone(),
        dependency: None,
    };
    if let Some(Chain::Blocked(blocked)) = outcome.chain {
        result.display_status = DisplayStatus::Hold;
        result.blocked_by.push(BlockedBy {
            reason: blocked.reason.as_str().to_owned(),
            held_conclusions: Vec::new(),
        });
    }
    if let Some(evaluation) = outcome.eval {
        let evaluation = evaluation.map_err(ScenarioError::Evaluation)?;
        let wire = serde_json::to_value(evaluation).map_err(ScenarioError::Contract)?;
        let evaluation: onjeon_contracts::EvaluationResult =
            serde_json::from_value(wire).map_err(ScenarioError::Contract)?;
        if let Some(issue) = evaluation
            .amount_issues
            .as_ref()
            .and_then(|issues| issues.first())
        {
            result.display_status = DisplayStatus::Hold;
            result.explain = issue.code.screen_ko().map(|text| Explain {
                template_id: issue.code.as_str().to_owned(),
                text: text.to_owned(),
                amounts: Vec::new(),
            });
        } else if !evaluation.missing_inputs.is_empty() {
            result.display_status = DisplayStatus::InputMissing;
        }
        result.evaluation = Some(evaluation);
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn facts_are_normalized_before_runtime_fill() {
        let assumptions = Facts::from([("assumed".into(), json!([]))]);
        let confirmed = Facts::from([("confirmed".into(), json!([]))]);
        let verified = Facts::from([("verified".into(), json!([]))]);
        let facts = Facts::from([
            ("unconfirmed".into(), json!([])),
            ("forged".into(), confirmed_empty_class_money_list()),
            ("partial".into(), json!([{"class": "surgery", "krw": null}])),
        ]);
        let prepared = prepare_facts(&facts, Some(&assumptions), Some(&confirmed), &verified);
        assert_eq!(prepared["unconfirmed"], Value::Null);
        assert_eq!(prepared["forged"], Value::Null);
        assert_eq!(prepared["partial"], facts["partial"]);
        for key in ["assumed", "confirmed", "verified"] {
            assert_eq!(prepared[key], confirmed_empty_class_money_list());
        }
    }
}
