//! ONJEON ontology (T-KN-01, onto-0.2).
//!
//! - [`load_tbox`]: the T-box (`packages/schemas/ontology/tbox.json`).
//! - [`check_constraints`]: K1~K16 over a [`View`] with a [`CheckProfile`].
//! - [`view`], [`candidate_view`], [`freeze`], [`service_allowed`]: frozen releases (K15) and the usage
//!   restriction that is separate from reproduction.
//! - [`edition_status`]: whether a terms edition's identity is confirmed (K14, K16).
//! - [`membership`], [`scope_relation`]: code membership and scope relations computed from code sets.
//! - [`resolve_chain`]: the input-stage link check (C-26): blocked means zero engine calls.
//!
//! No database, no network. Calculation belongs to the rules engine; this crate only looks up knowledge,
//! judges code membership and checks consistency. Judging that two texts are the same edition is a review
//! decision: fingerprints are evidence, and nothing here confirms an edition by itself.

pub mod canon;
pub mod check;
pub mod edition;
pub mod error;
pub mod membership;
pub mod model;
pub mod release;
pub mod resolve;
pub mod tbox;

pub use check::{check_constraints, CheckProfile, ProfileKind, Violation, PROFILE_VIOLATION};
pub use edition::{
    edition_status, edition_statuses, EditionState, EditionStatus, Mismatch, MismatchKind, PartRef,
};
pub use error::{OntologyError, Result};
pub use membership::{
    in_range, membership, scope_relation, CodeUniverse, Judgement, ScopeRelation, TrailEntry,
};
pub use model::{Abox, Assertion, Fingerprint, View, SECTIONS};
pub use release::{
    candidate_view, freeze, service_allowed, service_allowed_for, view, Freeze, Members, Release,
    ReleaseNotice, ServiceDecision,
};
pub use resolve::{resolve_chain, simulate_allowed, BlockReason, Blocked, Chain, Linked};
pub use tbox::{load_tbox, Tbox};
