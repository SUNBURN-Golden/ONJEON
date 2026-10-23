//! Test-only (`fixture_only`) compilation of the actual defaults source files.
//! No product source is temporarily modified. Passing these tests does not prove
//! that onjeon-criteria exports defaults; the product_api integration target
//! checks the actual exported Rust API separately.

pub use onjeon_criteria::{error, k8, model, release, store};

#[path = "../mod.rs"]
pub mod defaults;
