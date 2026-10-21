//! Check profiles (historical fixture vs service conformance) and price observations (P1), library level only.
//! Rejection by a real service loader or release builder is tested where those are implemented.

mod common;
use common::*;
use onjeon_ontology::*;
use serde_json::json;

/// test id: profile-check-flags-fixture
#[test]
fn profile_check_flags_fixture() {
    let a = abox();
    let v = release_view(&a, CURRENT);

    // (a) historical_fixture: r26 has no violations and the 11 questions answer as in the reference
    assert!(check_constraints(
        &v,
        &CheckProfile::historical_fixture(Some(fixture_universe()))
    )
    .is_empty());
    for q in questions() {
        assert_eq!(answer(&v, &q).outcome, q.expect, "{}", q.id);
    }

    // (b) service_conformance: every accepted fixture / fixture_assumption claim is listed
    let vs = check_constraints(
        &v,
        &CheckProfile::service_conformance(Some(fixture_universe())),
    );
    assert!(!vs.is_empty());
    assert!(
        vs.iter().all(|x| x.code == PROFILE_VIOLATION),
        "only profile findings, no K violations: {vs:?}"
    );
    let listed: std::collections::BTreeSet<&str> = vs.iter().map(|x| x.subject.as_str()).collect();
    let expected: std::collections::BTreeSet<&str> = v
        .assertions
        .iter()
        .filter(|x| {
            x.accepted()
                && (x.origin.as_deref() == Some("fixture")
                    || x.decision_by() == Some("fixture_assumption"))
        })
        .map(|x| x.id.as_str())
        .collect();
    assert_eq!(listed, expected);
    assert!(
        listed.contains("a:realizes_hana_r2_1"),
        "fixture_assumption realizes is listed"
    );
    assert_eq!(listed.len(), vs.len(), "one finding per claim");
    // claims that are neither fixtures nor assumptions are not listed
    assert!(v
        .assertions
        .iter()
        .any(|x| x.accepted() && !listed.contains(x.id.as_str())));
}

#[test]
fn a_review_decision_realizes_passes_the_service_profile() {
    let mut a = abox();
    let mut cand = candidate_view(&a).unwrap();
    let before = check_constraints(
        &cand,
        &CheckProfile::service_conformance(Some(fixture_universe())),
    )
    .len();
    set(
        &mut a,
        "assertions",
        "a:realizes_hana_r2_1",
        "decision",
        json!({"by": "review_decision"}),
    );
    set(
        &mut a,
        "assertions",
        "a:realizes_hana_r2_1",
        "origin",
        json!("pipeline"),
    );
    cand = candidate_view(&a).unwrap();
    let after = check_constraints(
        &cand,
        &CheckProfile::service_conformance(Some(fixture_universe())),
    );
    assert_eq!(after.len(), before - 1);
    assert!(!after.iter().any(|x| x.subject == "a:realizes_hana_r2_1"));
}

#[test]
fn p1_raw_price_observation_is_kept_and_comparison_needs_dimensions() {
    let mut a = abox();
    push(
        &mut a,
        "premium_observations",
        json!({"id": "p:raw_bundle", "krw": 16598, "priced_for": "sc:hana_2601_3d_v20260701", "conditions": null,
        "package_binding": "source_bundle", "as_of": null, "comparison_eligible": false}),
    );
    assert!(
        check_candidate(&a).is_empty(),
        "raw observation with empty dimensions is kept"
    );
    set(
        &mut a,
        "premium_observations",
        "p:raw_bundle",
        "comparison_eligible",
        json!(true),
    );
    let vs = check_candidate(&a);
    assert!(
        !vs.is_empty() && vs.iter().all(|v| v.code == "K13"),
        "{vs:?}"
    );
    assert_eq!(
        vs.len(),
        2,
        "conditions and as_of are missing, package_binding is present"
    );
}
