//! ONJEON wire contracts (T-CT-01).
//!
//! Types in [`generated`] come from `packages/schemas/vocabulary.json` (every
//! enum) and `packages/schemas/json/*.schema.json` (every wire struct) via
//! `bash packages/schemas/codegen/gen.sh`. They are never edited by hand.
//! The JSON Schemas are the contract; Dart and TypeScript clients are generated
//! from the same files.
//!
//! Unknown enum values fail to deserialize, they are never mapped to a default
//! (vocabulary rule 4). Unknown struct fields are ignored so that additive
//! (minor) schema changes do not break older clients.
//!
//! [`checks`] holds the cross-field invariants that JSON Schema cannot state
//! without repeating vocabulary values (for example `accepted` needs a review
//! decision).
//!
//! T-CT-04 adds [`evidence_ref`] (grammar parser, validator and fixture-id converter,
//! 02 §6.1), [`errors`] (`errors.json`, 02 §4), [`allowlist`] (`analytics-events.json`,
//! 02 §3.2) and [`events`] (`events/*.schema.json`, 02 §3.1). The JSON files are the
//! contract and carry `contracts_version`, which tests tie to this crate's version.

pub mod allowlist;
pub mod checks;
pub mod errors;
pub mod events;
pub mod evidence_ref;
#[rustfmt::skip]
pub mod generated;

pub use generated::types::*;
pub use generated::vocabulary::*;

/// Contracts package version (semver, tag `contracts-x.y.z`). See `packages/schemas/README.md`.
pub const CONTRACTS_VERSION: &str = env!("CARGO_PKG_VERSION");

#[cfg(test)]
mod tests;
