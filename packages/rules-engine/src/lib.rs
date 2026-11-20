#![forbid(unsafe_code)]

//! ONJEON deterministic rule evaluator (DSL v0.1, plus the rule-0.2 operators).
//!
//! Design rules (see docs/masterplan, part 3 section 49):
//! - Three-valued logic: true / false / unknown. Unknown never defaults to zero.
//! - Money is an integer number of KRW. No floating point anywhere.
//! - Only allow-listed operators; rules are data, never code.
//! - Every result carries a trace, the missing inputs that blocked it, and
//!   an input snapshot hash so it can be reproduced.

mod canonical;
pub mod strict_json;

pub mod date;
pub mod eval;
pub mod rule;
pub mod tri;
pub mod value;

pub use eval::{
    confirmed_empty_class_money_list, AmountOut, CalculationIssue, CalculationIssueCode,
    ContractEffectOut, EvalError, EvaluationResult, Payout, TraceEntry,
};
pub use rule::{ContractEffect, Rule, RuleError};
pub use tri::Tri;

/// Evaluator version recorded in results and release manifests. The suffix identifies
/// the input snapshot encoding. This version is independent of the Cargo package version.
pub const ENGINE_VERSION: &str = "0.2.0+snapshot-json-1";
