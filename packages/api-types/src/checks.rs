//! Request invariants that JSON Schema (without `oneOf`) cannot state.
//!
//! Wire parsing only checks shape. These checks reject a request that is well-formed but names
//! its target twice or not at all. They never default a missing choice.

use crate::generated::types::{ComparisonRequest, EvaluationRequest};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RequestCheck {
    /// Neither alternative was given.
    MissingTarget,
    /// Both alternatives were given.
    AmbiguousTarget,
}

fn exactly_one(a: bool, b: bool) -> Result<(), RequestCheck> {
    match (a, b) {
        (true, false) | (false, true) => Ok(()),
        (false, false) => Err(RequestCheck::MissingTarget),
        (true, true) => Err(RequestCheck::AmbiguousTarget),
    }
}

/// `cov_ids` xor `concept_id` (02_구현계약 §2.1). An empty `cov_ids` counts as absent.
pub fn comparison_request(r: &ComparisonRequest) -> Result<(), RequestCheck> {
    exactly_one(
        r.cov_ids.as_ref().is_some_and(|v| !v.is_empty()),
        r.concept_id.is_some(),
    )
}

/// `contract_ids` xor `cov_ids` (02_구현계약 §2.2). An empty list counts as absent.
pub fn evaluation_request(r: &EvaluationRequest) -> Result<(), RequestCheck> {
    exactly_one(
        r.contract_ids.as_ref().is_some_and(|v| !v.is_empty()),
        r.cov_ids.as_ref().is_some_and(|v| !v.is_empty()),
    )
}
