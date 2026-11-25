//! Cross-field invariants of the contract types.
//!
//! JSON Schema in this package has no `enum`/`const` of its own (enums come only
//! from the vocabulary), so rules like "accepted needs a review decision" are
//! checked here, against the typed vocabulary enums. Each violation carries the
//! name of the database constraint or contract rule it mirrors.

use std::collections::HashSet;

use crate::evidence_ref::{
    is_hex, is_iso_date, is_rfc3339, is_ulid, kind_of, no_ws, validate, ParsedRef, RefKind,
};
use crate::{
    Amount, AmountKind, AmountOut, Assertion, AssertionOrigin, CompareView, ConfirmParty,
    ContractSnapshot, CoverageDetail, DisplayStatus, ErrorClass, ErrorResponse, EvaluationResult,
    EvidenceView, FactSource, NeedReason, NeedResult, Payout, PlanView, PremiumObservation,
    ReleaseManifest, ReviewStatus, ScenarioResult, Sensitivity, Tri, ValueState,
};

/// `origin` value of rows that exist only for tests (02_구현계약 §1.2, §8): vocabulary axis
/// `assertion_origin` (1.6.0). A fixture row is never accepted and never comparison-eligible.
pub const ORIGIN_FIXTURE: AssertionOrigin = AssertionOrigin::Fixture;

/// `contract_effect.kind` values (02_구현계약 G23, rule-0.2): the engine's `ContractEffectOut`
/// tag. Strings until the `contract_effect_kind` axis enters the vocabulary.
pub const CONTRACT_EFFECT_NONE: &str = "none";
pub const CONTRACT_EFFECT_APPLIES: &str = "applies";
pub const CONTRACT_EFFECT_UNDETERMINED: &str = "undetermined";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Violation {
    /// Constraint or rule name, for example `chk_accepted_needs_decision`.
    pub rule: &'static str,
    pub message: String,
}

fn v(rule: &'static str, message: &str) -> Violation {
    Violation {
        rule,
        message: message.to_string(),
    }
}

pub fn check_assertion(a: &Assertion) -> Vec<Violation> {
    let mut out = Vec::new();
    if a.review_status == ReviewStatus::Accepted && a.review_decision_id.is_none() {
        out.push(v(
            "chk_accepted_needs_decision",
            "accepted assertion has no review_decision_id",
        ));
    }
    if a.origin == ORIGIN_FIXTURE && a.review_status == ReviewStatus::Accepted {
        out.push(v(
            "chk_fixture_never_accepted",
            "origin=fixture can never be accepted (ONJ-KN-S-050)",
        ));
    }
    if a.object.is_some() == a.value.is_some() {
        out.push(v(
            "assertion_object_xor_value",
            "exactly one of object (relation) and value (attribute) is required",
        ));
    }
    out
}

pub fn check_premium_observation(p: &PremiumObservation) -> Vec<Violation> {
    let mut out = Vec::new();
    let amount_known = match p.value_state {
        ValueState::Observed | ValueState::Derived => true,
        ValueState::NotFound
        | ValueState::Unreadable
        | ValueState::Conflicting
        | ValueState::NotApplicable
        | ValueState::NotDisclosed => false,
    };
    if p.raw_amount.is_some() != amount_known {
        out.push(v(
            "chk_premium_amount_matches_value_state",
            "raw_amount is required for observed or derived and forbidden for other value states",
        ));
    }
    let reason_valid = match &p.unknown_reason {
        Some(reason) => !amount_known && !reason.trim().is_empty(),
        None => amount_known,
    };
    if !reason_valid {
        out.push(v(
            "chk_premium_unknown_reason_matches_value_state",
            "a non-blank unknown_reason is required for unavailable amounts and forbidden for observed or derived",
        ));
    }
    if p.review_status == ReviewStatus::Accepted && p.review_decision_id.is_none() {
        out.push(v(
            "chk_accepted_needs_decision",
            "accepted observation has no review_decision_id",
        ));
    }
    if p.origin == ORIGIN_FIXTURE && p.review_status == ReviewStatus::Accepted {
        out.push(v(
            "chk_fixture_never_accepted",
            "origin=fixture can never be accepted (ONJ-KN-S-050)",
        ));
    }
    let has_value = |value: Option<&str>| value.is_some_and(|value| !value.trim().is_empty());
    let fixed_dimensions = [
        (
            "conditions",
            p.conditions.as_ref().is_some_and(|c| !c.is_empty()),
        ),
        ("package_binding", has_value(p.package_binding.as_deref())),
        ("source_as_of", has_value(p.source_as_of.as_deref())),
        ("payment_cycle", has_value(p.payment_cycle.as_deref())),
        (
            "comparison_basis_id",
            has_value(p.comparison_basis_id.as_deref()),
        ),
    ];
    // The label dictionary defines the open set of condition keys. Locally we can
    // check the values carried by the record and let it report other missing keys.
    let condition_dimensions = p
        .conditions
        .iter()
        .flatten()
        .map(|(dimension, value)| (dimension.as_str(), !value.trim().is_empty()));
    let mut dimensions_complete = true;
    for (dimension, present) in fixed_dimensions.into_iter().chain(condition_dimensions) {
        dimensions_complete &= present;
        let marked_missing = p
            .missing_dimensions
            .iter()
            .any(|missing| missing == dimension);
        if marked_missing == present {
            let message = if present {
                format!("{dimension} has a value and must be removed from missing_dimensions")
            } else {
                format!("{dimension} is absent and must be listed in missing_dimensions")
            };
            out.push(v("chk_premium_missing_dimensions", &message));
        }
    }

    let components = p.components.as_deref().unwrap_or_default();
    let mut component_refs = HashSet::new();
    if p.product_ref.as_deref().is_some_and(|id| !no_ws(id))
        || p.sales_config_ref
            .as_deref()
            .is_some_and(|id| !id.strip_prefix("sc:").is_some_and(is_ulid))
        || p.coverage_ref
            .as_deref()
            .is_some_and(|id| !is_coverage_ref(id))
        || p.components.as_ref().is_some_and(Vec::is_empty)
        || components.iter().any(|component| {
            !is_coverage_ref(&component.cov_ref)
                || !component_refs.insert(&component.cov_ref)
                || component
                    .insured_amount_krw
                    .is_some_and(|amount| amount < 0)
        })
    {
        out.push(v(
            "chk_premium_priced_subject",
            "priced subject references must be valid and component coverage references must be unique with non-negative amounts",
        ));
    }
    if p.source_revision
        .as_deref()
        .is_some_and(|id| kind_of(id) != Some(RefKind::Raw))
    {
        out.push(v(
            "chk_premium_source_revision",
            "source_revision must identify immutable source bytes with a raw:sha256 reference",
        ));
    }
    let start = p.effective_from.as_deref();
    let end = p.effective_to.as_deref();
    let open_ended = p.effective_open_ended == Some(true);
    let period_valid = start.is_none_or(is_iso_date)
        && end.is_none_or(is_iso_date)
        && start.zip(end).is_none_or(|(from, to)| from <= to)
        && !(open_ended && end.is_some());
    if !period_valid {
        out.push(v(
            "chk_premium_effective_period",
            "the effective period must use valid dates in order and cannot have both an end date and an open end",
        ));
    }
    if p.comparison_eligible {
        if !amount_known || p.raw_amount.is_none() {
            out.push(v(
                "chk_premium_raw_vs_eligible",
                "comparison_eligible needs an observed or derived amount",
            ));
        }
        let conditions_missing = p.conditions.as_ref().is_none_or(|c| c.is_empty());
        let composition_complete = !components.is_empty()
            && components.iter().all(|c| c.insured_amount_krw.is_some())
            && p.coverage_ref
                .as_ref()
                .is_none_or(|id| components.len() == 1 && components[0].cov_ref == *id)
            && (p.package_binding.as_deref() != Some("source_bundle") || components.len() >= 2);
        let covers_basis_date = period_valid
            && p.source_as_of.as_deref().is_some_and(|as_of| {
                is_iso_date(as_of)
                    && start.is_some_and(|from| from <= as_of)
                    && (open_ended || end.is_some_and(|to| as_of <= to))
            });
        if !dimensions_complete
            || conditions_missing
            || p.evidence.is_empty()
            || p.payment_cycle.as_deref().is_none_or(|id| !no_ws(id))
            || p.comparison_basis_id.as_deref().is_none_or(|id| !no_ws(id))
            || p.package_binding.is_none()
            || p.product_ref.is_none()
            || p.sales_config_ref.is_none()
            || p.source_revision.is_none()
            || !composition_complete
            || !covers_basis_date
            || !p.missing_dimensions.is_empty()
        {
            out.push(v(
                "chk_premium_raw_vs_eligible",
                "comparison_eligible needs an observed or derived amount, evidenced conditions, package_binding, source_as_of, payment_cycle, comparison_basis_id, a complete priced subject, a source revision and a period covering source_as_of with no missing_dimensions (K13)",
            ));
        }
        if p.review_status != ReviewStatus::Accepted {
            out.push(v(
                "chk_premium_raw_vs_eligible",
                "comparison_eligible needs review_status=accepted",
            ));
        }
    }
    out
}

fn is_coverage_ref(id: &str) -> bool {
    id.strip_prefix("cov:ted:")
        .and_then(|id| id.split_once('/'))
        .is_some_and(|(edition, path)| is_ulid(edition) && no_ws(path))
}

fn valid_refs(refs: &[String]) -> bool {
    refs.iter().all(|reference| validate(reference).is_ok())
}

fn valid_amount(amount: &Amount) -> bool {
    amount.krw >= 0
        && amount.source.split_once(':').is_some_and(|(kind, id)| {
            matches!(kind, "scenario" | "premium" | "candidate" | "clause") && no_ws(id)
        })
}

/// Checks the two-plan diff classification and the evidence for display rows.
pub fn check_plan_view(plan: &PlanView) -> Vec<Violation> {
    let mut out = Vec::new();
    if let Some(diff) = &plan.diff {
        if !plan.diff_available {
            out.push(v(
                "plan_diff_is_available",
                "a diff payload requires diff_available",
            ));
        }
        let mut groups = HashSet::new();
        for group in &diff.groups {
            if !groups.insert(group.group) {
                out.push(v(
                    "plan_diff_group_unique",
                    "a diff group appears more than once",
                ));
            }
            for item in &group.items {
                let expected = item.diff_type.group();
                if group.group != expected {
                    out.push(v(
                        "plan_diff_type_matches_group",
                        &format!(
                            "{} belongs to {}, found {}",
                            item.diff_type.as_str(),
                            expected.as_str(),
                            group.group.as_str()
                        ),
                    ));
                }
                if !item.amounts.iter().all(valid_amount) {
                    out.push(v(
                        "plan_diff_amount_has_source",
                        "diff amounts need valid sources",
                    ));
                }
            }
        }
    }
    for group in &plan.groups {
        let price = &group.price_line;
        let valid_price = match &price.man {
            None => price.price_unavailable_reason.is_some(),
            Some(values) => {
                price.price_unavailable_reason.is_none()
                    && price.basis.is_some()
                    && price.as_of.as_deref().is_some_and(is_iso_date)
                    && (1..=2).contains(&values.len())
                    && values.iter().all(|n| n.is_finite() && *n >= 0.0)
                    && values.windows(2).all(|pair| pair[0] <= pair[1])
            }
        };
        if !valid_price {
            out.push(v(
                "plan_price_has_basis_or_unavailable_reason",
                "a displayed price needs its basis and date, or an unavailable price needs its reason",
            ));
        }
        for item in &group.unresolved_items {
            if !valid_refs(&item.refs) {
                out.push(v(
                    "plan_unresolved_refs_valid",
                    "invalid unresolved item reference",
                ));
            }
        }
        if let Some(need) = &group.need {
            check_need_reasons(&need.reasons, &mut out);
        }
    }
    out
}

/// Checks I6 references and the position of the exclusion layer.
pub fn check_coverage_detail(detail: &CoverageDetail) -> Vec<Violation> {
    let mut out = Vec::new();
    for (index, layer) in detail.layers.iter().enumerate() {
        if layer.layer == "when_not_paid"
            && (index != 1 || detail.layers[0].layer != "what_is_covered")
        {
            out.push(v(
                "coverage_exclusion_layer_position",
                "when_not_paid must be the second layer after what_is_covered",
            ));
        }
        for line in &layer.lines {
            if line.refs.is_empty() || !valid_refs(&line.refs) {
                out.push(v(
                    "coverage_line_has_evidence",
                    "each view line needs valid evidence",
                ));
            }
            if !line.amounts.iter().flatten().all(valid_amount)
                || !line
                    .values
                    .iter()
                    .flatten()
                    .all(|value| no_ws(&value.source))
            {
                out.push(v(
                    "coverage_line_values_have_sources",
                    "each amount or value needs its source",
                ));
            }
        }
    }
    out
}

/// Checks the alignment of comparison columns, cells and price availability.
pub fn check_compare_view(view: &CompareView) -> Vec<Violation> {
    let mut out = Vec::new();
    let columns: HashSet<_> = view
        .columns
        .iter()
        .map(|column| column.sc_id.as_str())
        .collect();
    if columns.len() != view.columns.len() {
        out.push(v(
            "compare_columns_unique",
            "sc_id must identify a single column",
        ));
    }
    for axis in &view.axes {
        let cells: HashSet<_> = axis
            .per_column
            .iter()
            .map(|cell| cell.sc_id.as_str())
            .collect();
        if cells != columns || cells.len() != axis.per_column.len() {
            out.push(v(
                "compare_cells_match_columns",
                "each axis needs one cell for each column",
            ));
        }
        for cell in &axis.per_column {
            let has_amounts = cell
                .amounts
                .as_ref()
                .is_some_and(|amounts| !amounts.is_empty());
            let needs_refs = has_amounts
                || matches!(
                    cell.display_status,
                    DisplayStatus::Confirmed | DisplayStatus::NotApplicable
                )
                || matches!(cell.applicability.as_str(), "applies" | "not_applies");
            let refs_ok = cell
                .refs
                .as_ref()
                .map_or(!needs_refs, |refs| !refs.is_empty() && valid_refs(refs));
            if !refs_ok {
                out.push(v(
                    "compare_cell_has_evidence",
                    "a factual cell or amount needs valid evidence",
                ));
            }
            if !cell.amounts.iter().flatten().all(valid_amount) {
                out.push(v(
                    "compare_cell_amount_has_source",
                    "comparison amounts require a valid source",
                ));
            }
        }
    }
    if let Some(price) = &view.price {
        if view.comparison_basis_id.as_ref() != Some(&price.basis_id) || !no_ws(&price.basis_id) {
            out.push(v(
                "compare_price_matches_basis",
                "the price block must use the view's comparison basis",
            ));
        }
        let priced_and_unpriced: HashSet<_> = price
            .comparable_columns
            .iter()
            .map(String::as_str)
            .chain(
                price
                    .unpriced_columns
                    .iter()
                    .map(|column| column.sc_id.as_str()),
            )
            .collect();
        if priced_and_unpriced != columns
            || priced_and_unpriced.len()
                != price.comparable_columns.len() + price.unpriced_columns.len()
        {
            out.push(v(
                "compare_price_partitions_columns",
                "each column must appear once as priced or unpriced",
            ));
        }
    }
    out
}

/// Validates the local links of an evidence chain. Storage proves membership and provenance.
pub fn check_evidence_view(view: &EvidenceView) -> Vec<Violation> {
    let mut out = Vec::new();
    if validate(&view.ref_).is_err() || view.chain.first().is_none_or(|step| step.ref_ != view.ref_)
    {
        out.push(v(
            "evidence_chain_starts_at_ref",
            "the evidence chain must start at the requested reference",
        ));
    }
    let parsed: Vec<_> = view
        .chain
        .iter()
        .map(|step| validate(&step.ref_).ok())
        .collect();
    for (index, step) in view.chain.iter().enumerate() {
        let reference = parsed[index].as_ref();
        let valid_level = match step.level.as_str() {
            "viewmodel" => no_ws(&step.ref_),
            "evaluation" => matches!(reference, Some(ParsedRef::Evaluation(_))),
            "rule" => matches!(reference, Some(ParsedRef::Rule(_))),
            "assertion" => matches!(reference, Some(ParsedRef::Assertion(_))),
            "clause" => matches!(reference, Some(ParsedRef::Clause(_))),
            "segment" => matches!(reference, Some(ParsedRef::Segment(_))),
            "edition" => matches!(reference, Some(ParsedRef::Edition(_))),
            "premium" => matches!(reference, Some(ParsedRef::Premium(_))),
            "raw" => matches!(reference, Some(ParsedRef::Raw(_))),
            "source" => matches!(reference, Some(ParsedRef::Observation(_))),
            "criterion" => matches!(reference, Some(ParsedRef::Criterion(_))),
            _ => false,
        };
        if !valid_level {
            out.push(v(
                "evidence_chain_ref_matches_level",
                "a chain step needs a valid reference of its level",
            ));
        }
        let next = parsed.get(index + 1).and_then(Option::as_ref);
        let linked = match reference {
            Some(ParsedRef::Clause(clause)) => {
                matches!(next, Some(ParsedRef::Segment(segment)) if *segment == clause.segment)
            }
            Some(ParsedRef::Segment(segment)) => {
                let raw = if matches!(next, Some(ParsedRef::Edition(_))) {
                    parsed.get(index + 2).and_then(Option::as_ref)
                } else {
                    next
                };
                matches!(raw, Some(ParsedRef::Raw(sha)) if sha.starts_with(&segment.raw_sha))
            }
            Some(ParsedRef::Raw(sha)) => {
                matches!(next, Some(ParsedRef::Observation(obs)) if sha.starts_with(&obs.sha16))
            }
            _ => true,
        };
        if !linked {
            out.push(v(
                "evidence_document_chain_link",
                "clause, segment, raw and observation must link to the same document",
            ));
        }
    }
    if view.quote_shown
        && !parsed
            .iter()
            .any(|reference| matches!(reference, Some(ParsedRef::Clause(_))))
    {
        out.push(v(
            "evidence_quote_has_clause",
            "a shown quote needs its clause",
        ));
    }
    out
}

fn check_need_reasons(reasons: &[NeedReason], out: &mut Vec<Violation>) {
    if reasons.is_empty() {
        out.push(v(
            "need_has_reasons",
            "a need verdict requires at least one reason",
        ));
    }
    for reason in reasons {
        let has_basis = match reason.statement_kind.as_str() {
            "fact" => {
                !reason.assertion_refs.is_empty()
                    && reason
                        .assertion_refs
                        .iter()
                        .all(|id| id.strip_prefix("a:").is_some_and(is_ulid))
            }
            "criteria_eval" => {
                reason.criterion_version_ref.as_deref().and_then(kind_of)
                    == Some(RefKind::Criterion)
            }
            "user_assumption" => reason
                .user_assumption_ref
                .as_deref()
                .and_then(|id| id.strip_prefix("assume:"))
                .and_then(|id| id.split_once('@'))
                .is_some_and(|(id, version)| {
                    is_ulid(id)
                        && !version.is_empty()
                        && version.bytes().all(|byte| byte.is_ascii_digit())
                }),
            "calc_result" => {
                reason.eval_ref.as_deref().and_then(kind_of) == Some(RefKind::Evaluation)
            }
            "unknown" => reason.unknown_overlap.as_ref().is_some_and(|items| {
                !items.is_empty() && items.iter().all(|item| no_ws(&item.ref_))
            }),
            _ => false,
        };
        if !has_basis || !valid_refs(&reason.evidence) {
            out.push(v(
                "need_reason_has_basis_by_kind",
                "each need reason requires evidence for its statement kind",
            ));
        }
    }
}

/// Checks the reason payload and the presence of the criteria release reference when used.
pub fn check_need_result(result: &NeedResult) -> Vec<Violation> {
    let mut out = Vec::new();
    check_need_reasons(&result.reasons, &mut out);
    if result
        .criteria_release_id
        .as_deref()
        .is_none_or(|id| !no_ws(id))
        && result
            .reasons
            .iter()
            .any(|reason| reason.statement_kind == "criteria_eval")
    {
        out.push(v(
            "need_criteria_has_release",
            "a criteria evaluation requires a criteria release",
        ));
    }
    out
}

/// Checks manifest metadata locally. Rehashing needs the frozen rows and rule file bytes.
pub fn check_release_manifest(manifest: &ReleaseManifest) -> Vec<Violation> {
    let mut out = Vec::new();
    let members = &manifest.members;
    for (name, ids) in [
        ("raw_assets", &members.raw_assets),
        ("segments", &members.segments),
        ("terms_editions", &members.terms_editions),
        ("terms_lineages", &members.terms_lineages),
        ("clauses", &members.clauses),
        ("nodes", &members.nodes),
        ("assertions", &members.assertions),
        ("conflicts", &members.conflicts),
        ("gaps", &members.gaps),
        ("premium_observations", &members.premium_observations),
    ] {
        if !ids.iter().all(|id| no_ws(id)) || !ids.windows(2).all(|pair| pair[0] < pair[1]) {
            out.push(v(
                "release_members_sorted_unique",
                &format!("{name} must contain sorted, unique IDs"),
            ));
        }
    }
    let sha256 = |hash: &str| is_hex(hash, 64, 64);
    if ![
        &manifest.content_sha256,
        &manifest.capability_table_hash,
        &manifest.explain_template_hash,
    ]
    .into_iter()
    .all(|hash| sha256(hash))
        || !manifest
            .rule_files
            .iter()
            .all(|(path, hash)| !path.trim().is_empty() && sha256(hash))
        || !manifest
            .model_versions
            .iter()
            .all(|model| sha256(&model.model_ref_hash))
    {
        out.push(v(
            "release_hashes_valid",
            "manifest hashes must be lowercase SHA-256 values and rule paths must be non-blank",
        ));
    }
    if !is_rfc3339(&manifest.created_at) || !is_rfc3339(&manifest.frozen_at) {
        out.push(v(
            "release_timestamps_valid",
            "created_at and frozen_at must be valid timestamps",
        ));
    }
    let withdrawal_ok = match (&manifest.withdrawn_at, &manifest.withdrawal_reason) {
        (None, None) => true,
        (Some(at), Some(reason)) => is_rfc3339(at) && !reason.trim().is_empty(),
        _ => false,
    };
    if !withdrawal_ok {
        out.push(v(
            "release_withdrawal_has_time_and_reason",
            "a withdrawal needs a valid time and reason",
        ));
    }
    if manifest.superseded_by.as_ref() == Some(&manifest.release_id) {
        out.push(v(
            "release_cannot_supersede_itself",
            "superseded_by must name another release",
        ));
    }
    out
}

/// Checks the private snapshot's edition evidence and component confirmation metadata.
pub fn check_contract_snapshot(snapshot: &ContractSnapshot) -> Vec<Violation> {
    let mut out = Vec::new();
    if !matches!(
        snapshot.sensitivity,
        Sensitivity::PrivatePolicy | Sensitivity::PrivateHealth
    ) {
        out.push(v(
            "contract_snapshot_sensitivity_private",
            "a contract snapshot requires private policy or health sensitivity",
        ));
    }
    for edition in &snapshot.applied_editions {
        if validate(&edition.basis_evidence).is_err() {
            out.push(v(
                "contract_edition_has_evidence",
                "an applied edition needs valid basis evidence",
            ));
        }
        if !is_iso_date(&edition.from)
            || edition
                .to
                .as_ref()
                .is_some_and(|to| !is_iso_date(to) || to < &edition.from)
        {
            out.push(v(
                "contract_edition_period_valid",
                "applied edition dates must be valid and in order",
            ));
        }
    }
    for component in &snapshot.components {
        if !is_coverage_ref(&component.cov_ref)
            || component.insured_amount_krw < 0
            || !is_iso_date(&component.as_of)
        {
            out.push(v(
                "contract_component_valid",
                "a component needs a coverage reference, a non-negative amount and a valid date",
            ));
        }
        if component.fact_source == FactSource::UserConfirmedExtract
            && component.confirm_party != ConfirmParty::User
        {
            out.push(v(
                "contract_component_confirmed_by_user",
                "user_confirmed_extract requires confirm_party=user",
            ));
        }
    }
    if snapshot
        .user_confirmed_at
        .as_deref()
        .is_some_and(|at| !is_rfc3339(at))
    {
        out.push(v(
            "contract_confirmation_time_valid",
            "user_confirmed_at must be a valid timestamp",
        ));
    }
    out
}

/// A blocked scenario makes no engine call, so it carries no evaluation or explanation (02 §1.7).
pub fn check_scenario_result(s: &ScenarioResult) -> Vec<Violation> {
    let mut out = Vec::new();
    if !s.blocked_by.is_empty() && (s.evaluation.is_some() || s.explain.is_some()) {
        out.push(v(
            "blocked_means_no_engine_call",
            "blocked_by is set but evaluation or explain is present",
        ));
    }
    if let Some(e) = &s.evaluation {
        out.extend(check_evaluation_result(e));
        if e.amount_issues
            .as_ref()
            .is_some_and(|issues| !issues.is_empty())
            && s.display_status != DisplayStatus::Hold
        {
            out.push(v(
                "calculation_issue_means_hold",
                "an amount calculation issue requires display_status=hold",
            ));
        }
    }
    out
}

/// Engine result shape (packages/rules-engine `Rule::evaluate`): payout and contract effect follow
/// eligibility, and every `kind` carries exactly the fields of that kind.
pub fn check_evaluation_result(e: &EvaluationResult) -> Vec<Violation> {
    let mut out = Vec::new();
    let expected = match e.eligibility {
        Tri::True => Payout::Payable,
        Tri::False => Payout::NotPayable,
        Tri::Unknown => Payout::Undetermined,
    };
    if e.payout.kind != expected {
        out.push(v(
            "payout_matches_eligibility",
            &format!(
                "eligibility={} needs payout.kind={}, found {}",
                e.eligibility.as_str(),
                expected.as_str(),
                e.payout.kind.as_str()
            ),
        ));
    }
    let (want_amount, want_conditional) = match e.payout.kind {
        Payout::Payable => (true, false),
        Payout::Undetermined => (false, true),
        Payout::NotPayable => (false, false),
    };
    if e.payout.amount.is_some() != want_amount
        || e.payout.conditional_amount.is_some() != want_conditional
    {
        out.push(v(
            "payout_fields_match_kind",
            "payable carries amount only, undetermined conditional_amount only, not_payable neither",
        ));
    }
    for a in [&e.payout.amount, &e.payout.conditional_amount]
        .into_iter()
        .flatten()
    {
        out.extend(check_amount_out(a));
    }
    if e.amount_issues
        .as_ref()
        .is_some_and(|issues| !issues.is_empty())
        && !e
            .payout
            .amount
            .as_ref()
            .or(e.payout.conditional_amount.as_ref())
            .is_some_and(|amount| amount.kind == AmountKind::Unknown)
    {
        out.push(v(
            "calculation_issue_means_unknown_amount",
            "an amount calculation issue requires an unknown amount",
        ));
    }
    if let Some(ce) = &e.contract_effect {
        let fields = match ce.kind.as_str() {
            CONTRACT_EFFECT_NONE => Some((false, false)),
            CONTRACT_EFFECT_APPLIES => Some((true, false)),
            CONTRACT_EFFECT_UNDETERMINED => Some((false, true)),
            _ => None,
        };
        match fields {
            None => out.push(v(
                "contract_effect_kind_known",
                &format!(
                    "contract_effect.kind {:?} is not none, applies or undetermined",
                    ce.kind
                ),
            )),
            Some((want_effect, want_conditional)) => {
                if ce.effect.is_some() != want_effect
                    || ce.conditional_effect.is_some() != want_conditional
                {
                    out.push(v(
                        "contract_effect_fields_match_kind",
                        "applies carries effect only, undetermined conditional_effect only, none neither",
                    ));
                }
                let allowed = match e.eligibility {
                    Tri::False => ce.kind == CONTRACT_EFFECT_NONE,
                    Tri::True => {
                        ce.kind == CONTRACT_EFFECT_NONE || ce.kind == CONTRACT_EFFECT_APPLIES
                    }
                    Tri::Unknown => {
                        ce.kind == CONTRACT_EFFECT_NONE || ce.kind == CONTRACT_EFFECT_UNDETERMINED
                    }
                };
                if !allowed {
                    out.push(v(
                        "contract_effect_matches_eligibility",
                        &format!(
                            "eligibility={} cannot have contract_effect.kind={}",
                            e.eligibility.as_str(),
                            ce.kind
                        ),
                    ));
                }
            }
        }
    }
    out
}

fn check_amount_out(a: &AmountOut) -> Vec<Violation> {
    let (krw, min, max) = (a.krw.is_some(), a.min_krw.is_some(), a.max_krw.is_some());
    let ok = match a.kind {
        AmountKind::Exact => krw && !min && !max,
        AmountKind::Range => !krw && min && max && a.min_krw <= a.max_krw,
        AmountKind::Unknown => !krw && !min && !max,
    };
    if ok {
        Vec::new()
    } else {
        vec![v(
            "amount_fields_match_kind",
            "exact carries krw only, range min_krw <= max_krw only, unknown no amount",
        )]
    }
}

/// The class letter that an `error_class` value carries inside `code`
/// (`ONJ-<zone>-<class letter>-<nnn>`, 02_구현계약 §4.2). The vocabulary axis `error_class`
/// names the classes with words; the letter set `VANSLUXT` of the `code` pattern is fixed here.
pub fn error_class_letter(class: ErrorClass) -> char {
    match class {
        ErrorClass::Validation => 'V',
        ErrorClass::Auth => 'A',
        ErrorClass::NotFound => 'N',
        ErrorClass::StateConflict => 'S',
        ErrorClass::Limit => 'L',
        ErrorClass::Unsupported => 'U',
        ErrorClass::Internal => 'X',
        ErrorClass::Timeout => 'T',
    }
}

/// The `error_class` value for a class letter of `code`; `None` for a letter outside `VANSLUXT`.
pub fn error_class_for_letter(letter: &str) -> Option<ErrorClass> {
    ErrorClass::ALL
        .iter()
        .copied()
        .find(|c| error_class_letter(*c).to_string() == letter)
}

/// `error_class` is the vocabulary word for the class letter of `code` (`ONJ-<zone>-<class>-<nnn>`).
pub fn check_error_response(e: &ErrorResponse) -> Vec<Violation> {
    let class = e.code.split('-').nth(2).unwrap_or("");
    if error_class_for_letter(class) != Some(e.error_class) {
        return vec![v(
            "error_class_matches_code",
            "error_class does not correspond to the class letter in code",
        )];
    }
    Vec::new()
}
