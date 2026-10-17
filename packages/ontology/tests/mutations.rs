//! The 15 constraint mutations of the reference (K1~K14, K16): each deliberately broken A-box is checked as a
//! release candidate and must raise exactly its own constraint. K15 is covered in `releases.rs`.

mod common;
use common::*;
use onjeon_ontology::*;
use serde_json::json;

fn caught(cid: &str, a: &Abox) -> Vec<Violation> {
    let vs = check_candidate(a);
    let hit: Vec<_> = vs.iter().filter(|v| v.code == cid).collect();
    let others: Vec<_> = vs.iter().filter(|v| v.code != cid).collect();
    assert!(!hit.is_empty(), "{cid}: not caught, got {vs:?}");
    assert!(others.is_empty(), "{cid}: other violations {others:?}");
    vs
}

fn broken(f: impl FnOnce(&mut Abox)) -> Abox {
    let mut a = abox();
    f(&mut a);
    a
}

#[test]
fn unbroken_candidate_is_clean() {
    assert!(check_candidate(&abox()).is_empty());
}

#[test]
fn k1_accepted_c0_without_terms_basis() {
    let a = broken(|a| {
        set(
            a,
            "assertions",
            "a:lotte_cov_def",
            "review_status",
            json!("accepted"),
        )
    });
    caught("K1", &a);
}

#[test]
fn k2_same_benefit_without_both_sides() {
    let a = broken(|a| {
        push(
            a,
            "assertions",
            json!({"id": "a:bad_same", "subject": "cov:hana_2_1", "predicate": "same_benefit_as", "object": "cov:hi_2_5",
            "criticality": "C0", "evidence": [{"ref": "hana_2601_3d#c_2_1_art1_1", "role": "basis"}], "value_state": "observed", "review_status": "accepted"}),
        )
    });
    caught("K2", &a);
}

#[test]
fn k3_code_set_without_edition() {
    caught("K3", &broken(|a| unset(a, "nodes", "codes:c44", "edition")));
}

#[test]
fn k4_narrower_cycle() {
    let a = broken(|a| {
        for (id, s, o) in [
            (
                "a:n1",
                "cat:lotte_general_cancer",
                "cat:hana_cancer_x_breast_genital",
            ),
            (
                "a:n2",
                "cat:hana_cancer_x_breast_genital",
                "cat:lotte_general_cancer",
            ),
        ] {
            push(
                a,
                "assertions",
                json!({"id": id, "subject": s, "predicate": "scope_relation", "object": o, "value": "narrower", "criticality": "C1",
                "evidence": [{"ref": "lotte_2604_smry#term_general_cancer", "role": "cross_check"}], "value_state": "observed", "review_status": "hold"}),
            );
        }
    });
    caught("K4", &a);
}

#[test]
fn k5_valid_from_after_valid_to() {
    caught(
        "K5",
        &broken(|a| {
            set(
                a,
                "assertions",
                "a:hana_old_doc_link",
                "time",
                json!({"valid_from": "2026-04-01", "valid_to": "2026-03-31"}),
            )
        }),
    );
}

#[test]
fn k6_different_units_called_equal() {
    let a = broken(|a| {
        set(
            a,
            "nodes",
            "cond:hi_waiting",
            "duration",
            json!({"value": 3, "unit": "calendar_month"}),
        );
        push(
            a,
            "assertions",
            json!({"id": "a:same_dur", "subject": "cond:hana_waiting", "predicate": "same_duration_as", "object": "cond:hi_waiting",
            "criticality": "C1", "evidence": [], "value_state": "derived", "review_status": "accepted"}),
        );
    });
    caught("K6", &a);
}

#[test]
fn k7_reduction_without_target() {
    caught(
        "K7",
        &broken(|a| unset(a, "nodes", "cond:hana_reduction", "applies_to")),
    );
}

#[test]
fn k8_private_id_in_public_zone() {
    caught(
        "K8",
        &broken(|a| {
            set(
                a,
                "assertions",
                "a:hana_cov_def",
                "note",
                json!("contract:abc123 에서 확인"),
            )
        }),
    );
}

#[test]
fn k9_rule_evidence_outside_basis() {
    caught("K9", &broken(with_bad_rule));
}

#[test]
fn k10_two_claims_supersede_the_same_one() {
    let a = broken(|a| {
        let v2 = get(a, "assertions", "a:lotte_cond_waiting_v2");
        push(
            a,
            "assertions",
            with(&v2, &[("id", json!("a:lotte_cond_waiting_v3"))]),
        );
    });
    caught("K10", &a);
}

#[test]
fn k11_enabled_with_hold_claims() {
    let a = broken(|a| {
        a.declared_capabilities
            .insert("cov:lotte_general_dx".into(), "enabled".into());
    });
    caught("K11", &a);
}

#[test]
fn k12_scope_relation_differs_from_computation() {
    let a = broken(|a| {
        push(
            a,
            "assertions",
            json!({"id": "a:wrong_scope", "subject": "cat:hana_cancer_x_breast_genital", "predicate": "scope_relation",
            "object": "cat:hi_cancer_x_similar", "value": "same_scope", "criticality": "C1", "evidence": [], "value_state": "derived", "review_status": "accepted"}),
        )
    });
    let vs = caught("K12", &a);
    assert_eq!(vs[0].message, "주장 same_scope ≠ 계산 narrower");
}

#[test]
fn k12_accepted_relation_without_a_code_universe_is_not_computable() {
    let a = broken(|a| {
        push(
            a,
            "assertions",
            json!({"id": "a:good_scope", "subject": "cat:hana_cancer_x_breast_genital", "predicate": "scope_relation",
            "object": "cat:hi_cancer_x_similar", "value": "narrower", "criticality": "C1", "evidence": [], "value_state": "derived", "review_status": "accepted"}),
        )
    });
    let v = candidate_view(&a).unwrap();
    assert!(check_constraints(&v, &historical()).is_empty());
    let vs = check_constraints(&v, &CheckProfile::historical_fixture(None));
    assert_eq!(codes(&vs), ["K12"]);
}

#[test]
fn k13_comparison_eligible_price_without_conditions() {
    let a = broken(|a| {
        push(
            a,
            "premium_observations",
            json!({"id": "p:hana_bundle", "krw": 16598, "priced_for": "sc:hana_2601_3d_v20260701", "conditions": null,
            "package_binding": "source_bundle", "as_of": null, "comparison_eligible": true}),
        )
    });
    caught("K13", &a);
}

#[test]
fn k14_fingerprint_match_is_not_an_approval() {
    // test id: edition-not-auto-by-fingerprint (golden D3) also in editions.rs
    let a = broken(|a| {
        set(
            a,
            "assertions",
            "a:realizes_hana_r2_1",
            "decision",
            json!({"by": "fingerprint_match"}),
        )
    });
    caught("K14", &a);
}

#[test]
fn k16_annex_fingerprint_changed_in_place() {
    let a = broken(|a| {
        set(
            a,
            "segments",
            "seg:hana_annex12",
            "fingerprint",
            json!({"rule": "fp-0.1", "sha256": "e".repeat(64)}),
        )
    });
    caught("K16", &a);
}
