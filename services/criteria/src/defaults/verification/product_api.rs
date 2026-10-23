//! Acceptance probe of the exported product API, not the test-only module.
//! Until onjeon-criteria wires defaults, this target must fail to compile.

use onjeon_criteria::defaults::{
    display, effective, load_dir, DefaultsStore, DisplayKind, EffectiveDefault,
    REFERENCE_STAT_LABEL,
};

#[test]
fn defaults_are_available_through_the_product_crate() {
    let store = DefaultsStore::new();
    assert_eq!(store.for_service().count(), 0);
    assert_eq!(REFERENCE_STAT_LABEL, "참고 통계");
}

#[test]
fn shipped_editions_are_loaded_through_the_product_api_without_service_exposure() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .find(|root| {
            root.join("data/criteria/criterion-file.schema.json")
                .is_file()
        })
        .expect("repository root");
    let store = load_dir(&root.join("data/criteria/defaults/candidates")).unwrap();
    assert!(
        store.versions().count() > 0,
        "confirmed editions must be shipped"
    );
    assert_eq!(store.for_service().count(), 0);
    for edition in store.versions() {
        let candidate = store.resolve(&edition.id).unwrap();
        assert!(!candidate.candidate.applied);
        let shown = display(candidate);
        assert_eq!(shown.kind, DisplayKind::ReferenceStatistic);
        assert_eq!(shown.kind.label(), "참고 통계");
        // fixture_only: the user assumption here is not a shipped default.
        assert!(matches!(
            effective(Some(37u64), Some(edition)),
            Some(EffectiveDefault::UserAssumption(37))
        ));
    }
}
