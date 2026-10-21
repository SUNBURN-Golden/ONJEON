//! The committed `tests/fixtures/declared_abox/` fixture is generated, not hand-edited:
//! it is the golden A-box with `inputs_from_outside_dsl` (C-08) pinned into its two rule
//! files and the `rel:case-r26` members re-frozen as `rel:declared-r26`.
//!
//! Regenerate after changing the declaration or the golden corpus:
//! `cargo test -p onjeon-twin-runtime --test regen_fixture -- --ignored`
//! The freshness test keeps the committed copy honest.

mod common;
use std::path::PathBuf;

fn fixture_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/declared_abox")
}

#[test]
#[ignore]
fn regenerate_declared_abox_fixture() {
    common::write_abox_dir(&common::declared_abox(), &fixture_dir());
}

/// The committed fixture is exactly what `declared_abox()` produces — a stale or
/// hand-edited copy fails here.
#[test]
fn declared_abox_fixture_is_current() {
    let a = common::declared_abox();
    let on_disk = onjeon_ontology::Abox::from_dir(&fixture_dir()).expect("fixture abox");
    assert_eq!(
        common::abox_json(&on_disk),
        common::abox_json(&a),
        "abox_cases.json drifted — regenerate with `cargo test -p onjeon-twin-runtime --test regen_fixture -- --ignored`"
    );
    for (p, bytes) in &a.rule_files {
        assert_eq!(
            std::fs::read(fixture_dir().join(p)).unwrap_or_else(|_| panic!("{p}")),
            *bytes,
            "{p} drifted"
        );
    }
}
