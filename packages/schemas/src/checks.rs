//! Cross-field invariants of the contract types.
//!
//! JSON Schema in this package has no `enum`/`const` of its own (enums come only
//! from the vocabulary), so rules like "accepted needs a review decision" are
//! checked here, against the typed vocabulary enums. Each violation carries the
//! name of the database constraint or contract rule it mirrors.

use crate::{Assertion, ErrorResponse, PremiumObservation, ReviewStatus, ScenarioResult};

/// `origin` value of rows that exist only for tests (02_구현계약 §1.2, §8).
/// Stays a string until the `assertion_origin` axis enters the vocabulary.
pub const ORIGIN_FIXTURE: &str = "fixture";

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
    if p.comparison_eligible {
        let conditions_missing = p.conditions.as_ref().is_none_or(|c| c.is_empty());
        if conditions_missing
            || p.package_binding.is_none()
            || p.source_as_of.is_none()
            || !p.missing_dimensions.is_empty()
        {
            out.push(v(
                "chk_premium_raw_vs_eligible",
                "comparison_eligible needs conditions, package_binding, source_as_of and no missing_dimensions (K13)",
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

/// A blocked scenario makes no engine call, so it carries no evaluation or explanation (02 §1.7).
pub fn check_scenario_result(s: &ScenarioResult) -> Vec<Violation> {
    let mut out = Vec::new();
    if !s.blocked_by.is_empty() && (s.evaluation.is_some() || s.explain.is_some()) {
        out.push(v(
            "blocked_means_no_engine_call",
            "blocked_by is set but evaluation or explain is present",
        ));
    }
    out
}

/// `error_class` is the class letter of `code` (`ONJ-<zone>-<class>-<nnn>`).
pub fn check_error_response(e: &ErrorResponse) -> Vec<Violation> {
    let class = e.code.split('-').nth(2).unwrap_or("");
    if class != e.error_class {
        return vec![v(
            "error_class_matches_code",
            "error_class differs from the class letter in code",
        )];
    }
    Vec::new()
}
