//! ONJEON deterministic rule evaluator (DSL v0.1).
//!
//! Design rules (see docs/masterplan, part 3 section 49):
//! - Three-valued logic: true / false / unknown. Unknown never defaults to zero.
//! - Money is an integer number of KRW. No floating point anywhere.
//! - Only allow-listed operators; rules are data, never code.
//! - Every result carries a trace, the missing inputs that blocked it, and
//!   an input snapshot hash so it can be reproduced.

pub mod date;
pub mod eval;
pub mod rule;
pub mod tri;
pub mod value;

pub use eval::{AmountOut, EvalError, EvaluationResult, Payout, TraceEntry};
pub use rule::{Rule, RuleError};
pub use tri::Tri;

/// Engine version recorded in every result.
pub const ENGINE_VERSION: &str = env!("CARGO_PKG_VERSION");
