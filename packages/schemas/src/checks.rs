//! Cross-field invariants of the contract types.
//!
//! JSON Schema in this package has no `enum`/`const` of its own (enums come only
//! from the vocabulary), so rules like "accepted needs a review decision" are
//! checked here, against the typed vocabulary enums. Each violation carries the
//! name of the database constraint or contract rule it mirrors.

use std::collections::HashSet;

use crate::evidence_ref::{is_iso_date, is_ulid, kind_of, no_ws, RefKind};
use crate::{
    AmountKind, AmountOut, Assertion, AssertionOrigin, DisplayStatus, ErrorClass, ErrorResponse,
    EvaluationResult, Payout, PremiumObservation, ReviewStatus, ScenarioResult, Tri, ValueState,
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
