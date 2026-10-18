//! ONJEON API v1 server types (T-CT-03).
//!
//! [`generated::types`] and [`generated::operations`] come from `packages/schemas/openapi/*.v1.yaml`
//! via `bash packages/schemas/codegen/gen.sh` and are never edited by hand. Contract views
//! (`CompareView`, `ScenarioResult`, ...) and vocabulary enums live in `onjeon-contracts`;
//! the generated types use them through `onjeon_contracts::*`; the crate is re-exported as [`contracts`].
//!
//! Skeleton operations (reserved, flags off, 제3부 §58) exist only with the `skeleton` feature,
//! which is off by default: the default build has neither their types nor their routes.

pub mod checks;
#[rustfmt::skip]
pub mod generated;

pub use generated::operations::*;
pub use generated::types::*;
/// The contracts crate (views, vocabulary enums, `checks`), for callers that want it by path.
pub use onjeon_contracts as contracts;

/// Operations of the default surface for one API surface.
pub fn operations_of(surface: Surface) -> impl Iterator<Item = &'static Operation> {
    OPERATIONS.iter().filter(move |o| o.surface == surface)
}

/// Looks an operation up by `operationId` (default surface only).
pub fn operation(id: &str) -> Option<&'static Operation> {
    OPERATIONS.iter().find(|o| o.id == id)
}

#[cfg(test)]
mod tests;
