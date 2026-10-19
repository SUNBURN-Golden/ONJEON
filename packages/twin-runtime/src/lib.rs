//! ONJEON twin runtime (T-TW-01, twin S0): the service-side input stage.
//!
//! The contract it answers is what a request needs before the rules engine may run
//! (02_구현계약 C-08·C-26·§1.7, ADR-0014 §4):
//!
//! - [`config_select`]: which sales configuration applies on the contract date. Ambiguity
//!   is *several* sales configurations; one configuration using several terms editions
//!   (보통약관·특약) is normal.
//! - [`resolve_chain`] / [`resolve_request`]: the link check sales configuration → terms
//!   edition → coverage → rule. A `Blocked` chain means zero engine calls; the coverage a
//!   request names is never trusted on its own.
//! - [`input_stage::fill`]: fills the inputs a rule declares from request facts and from
//!   input-stage judgements (code membership). What a rule needs judged is declared by
//!   the rule artifact itself (`inputs_from_outside_dsl`, C-08) — never by the request —
//!   and a judgement carries its evidence trail.
//! - [`evaluate_request`]: gates before the chain — K15 release-integrity findings and a
//!   malformed contract date stop the run with zero engine calls.
//! - [`harness`]: the `case-runner` job format and the per-job pipeline the CLI runs.
//!
//! No database, no network. The library never reads files: the caller hands it a
//! [`Snapshot`] and rule bytes pinned by the release.

pub mod config_select;
pub mod harness;
pub mod input_stage;
pub mod resolve;
pub mod snapshot;

pub use config_select::{config_select, ConfigBlock, ConfigSelection, HeldLink};
pub use input_stage::{
    fill, judge_time, load_rule_artifact, DurUnit, FillError, FillRequest, Filled, JudgedBy,
    OutsideInput, StageJudgement, TimeDuration, TimeJudgement,
};
pub use onjeon_ontology::Linked;
pub use resolve::{
    evaluate_request, resolve_chain, resolve_request, BlockReason, Blocked, Chain, Request,
    RequestOutcome,
};
pub use snapshot::Snapshot;
