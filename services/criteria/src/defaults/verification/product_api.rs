//! Acceptance probe of the exported product API, not the test-only module.
//! Until onjeon-criteria wires defaults, this target must fail to compile.

use onjeon_criteria::defaults::{DefaultsStore, REFERENCE_STAT_LABEL};

#[test]
fn defaults_are_available_through_the_product_crate() {
    let store = DefaultsStore::new();
    assert_eq!(store.for_service().count(), 0);
    assert_eq!(REFERENCE_STAT_LABEL, "참고 통계");
}
