use onjeon_knowledge::{
    AcquisitionTask, KnowledgeError, KnowledgeRepository, ObservationAllowlist, ReviewDecision,
};
use onjeon_ontology::{candidate_view, check_constraints, Abox, CheckProfile};
use serde_json::{json, Value};
use std::path::Path;

fn pending(id: &str) -> Value {
    json!({
        "id": id,
        "subject": "coverage:test",
        "predicate": "label",
        "value": "test",
        "criticality": "C1",
        "value_state": "observed",
        "review_status": "pending",
        "evidence": [],
        "origin": "pipeline"
    })
}

fn accepted(id: &str, origin: &str, decision: Option<&str>) -> Value {
    let mut value = pending(id);
    value["review_status"] = json!("accepted");
    value["origin"] = json!(origin);
    if let Some(decision) = decision {
        value["review_decision_id"] = json!(decision);
    }
    value
}

fn valid_decision() -> ReviewDecision {
    ReviewDecision {
        id: "rd:01ARZ3NDEKTSV4RRFFQ69G5FAV".to_owned(),
        environment: "test".to_owned(),
        outcome: "accepted".to_owned(),
        families_count: 2,
        code_checks_passed: true,
        redteam_counterexamples: 0,
        cross_doc_conflict_free: true,
        audit_log_sha256: "a".repeat(64),
    }
}

#[test]
fn store() {
    let mut repository = KnowledgeRepository::new();
    let allowlist = ObservationAllowlist::default();
    let assertion = pending("a:01ARZ3NDEKTSV4RRFFQ69G5FAV");
    repository
        .ingest_assertion(Path::new("incoming/a.json"), assertion.clone(), &allowlist)
        .unwrap();

    let stored = repository
        .get("assertions", "a:01ARZ3NDEKTSV4RRFFQ69G5FAV")
        .expect("stored assertion is retrievable");
    assert_eq!(stored["subject"], "coverage:test");
    assert_eq!(repository.list("assertions").len(), 1);
}

#[test]
fn assertion_is_append_only_and_changes_by_supersedes() {
    let mut repository = KnowledgeRepository::new();
    let allowlist = ObservationAllowlist::default();
    repository
        .ingest_assertion(
            Path::new("incoming/a.json"),
            pending("a:01ARZ3NDEKTSV4RRFFQ69G5FAV"),
            &allowlist,
        )
        .unwrap();
    assert_eq!(
        repository.update_assertion("a:01ARZ3NDEKTSV4RRFFQ69G5FAV", json!({})),
        Err(KnowledgeError::Immutable)
    );

    let mut replacement = pending("a:01ARZ3NDEKTSV4RRFFQ69G5FAW");
    replacement["supersedes"] = json!("a:01ARZ3NDEKTSV4RRFFQ69G5FAV");
    repository
        .ingest_assertion(Path::new("incoming/b.json"), replacement, &allowlist)
        .unwrap();
    assert_eq!(
        repository.superseding("a:01ARZ3NDEKTSV4RRFFQ69G5FAV").len(),
        1
    );
}

#[test]
fn conflict_links_divergent_superseding_assertions() {
    let mut repository = KnowledgeRepository::new();
    let allowlist = ObservationAllowlist::default();
    repository
        .ingest_assertion(
            Path::new("incoming/base.json"),
            pending("a:01ARZ3NDEKTSV4RRFFQ69G5FAV"),
            &allowlist,
        )
        .unwrap();
    for id in [
        "a:01ARZ3NDEKTSV4RRFFQ69G5FAW",
        "a:01ARZ3NDEKTSV4RRFFQ69G5FAX",
    ] {
        let mut replacement = pending(id);
        replacement["supersedes"] = json!("a:01ARZ3NDEKTSV4RRFFQ69G5FAV");
        repository
            .ingest_assertion(
                Path::new("incoming/replacement.json"),
                replacement,
                &allowlist,
            )
            .unwrap();
    }
    repository
        .insert_conflict(json!({
            "id": "conflict:01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "assertion_ids": [
                "a:01ARZ3NDEKTSV4RRFFQ69G5FAW",
                "a:01ARZ3NDEKTSV4RRFFQ69G5FAX"
            ],
            "reason": "divergent corrections"
        }))
        .unwrap();
    assert_eq!(
        repository
            .conflicts_for("a:01ARZ3NDEKTSV4RRFFQ69G5FAW")
            .len(),
        1
    );
}

#[test]
fn edition_conflict() {
    let mut repository = KnowledgeRepository::new();
    let allowlist = ObservationAllowlist::default();

    // Two clauses may share the same edition without being in conflict.
    repository
        .ingest_assertion(
            Path::new("incoming/combined_terms.json"),
            pending("edition:01ARZ3NDEKTSV4RRFFQ69G5FAV"),
            &allowlist,
        )
        .unwrap();
    let mut rider = pending("edition:01ARZ3NDEKTSV4RRFFQ69G5FAW");
    rider["edition_id"] = json!("edition:01ARZ3NDEKTSV4RRFFQ69G5FAV");
    repository
        .ingest_assertion(Path::new("incoming/rider.json"), rider, &allowlist)
        .unwrap();

    // Only mutually exclusive claims about the same scope are recorded as a conflict.
    let mut first = pending("edition:01ARZ3NDEKTSV4RRFFQ69G5FAX");
    first["supersedes"] = json!("edition:01ARZ3NDEKTSV4RRFFQ69G5FAV");
    let mut second = pending("edition:01ARZ3NDEKTSV4RRFFQ69G5FAY");
    second["supersedes"] = json!("edition:01ARZ3NDEKTSV4RRFFQ69G5FAV");
    repository
        .ingest_assertion(Path::new("incoming/first.json"), first, &allowlist)
        .unwrap();
    repository
        .ingest_assertion(Path::new("incoming/second.json"), second, &allowlist)
        .unwrap();
    repository
        .insert_conflict(json!({
            "id": "conflict:01ARZ3NDEKTSV4RRFFQ69G5FAX",
            "assertion_ids": [
                "edition:01ARZ3NDEKTSV4RRFFQ69G5FAX",
                "edition:01ARZ3NDEKTSV4RRFFQ69G5FAY"
            ],
            "reason": "same edition, incompatible terms"
        }))
        .unwrap();
    assert_eq!(
        repository
            .conflicts_for("edition:01ARZ3NDEKTSV4RRFFQ69G5FAX")
            .len(),
        1
    );
}

#[test]
fn b1_fixture_path_is_rejected() {
    let mut repository = KnowledgeRepository::new();
    let error = repository.ingest_assertion(
        Path::new("packages/fixtures/ontology/abox_cases.json"),
        pending("a:01ARZ3NDEKTSV4RRFFQ69G5FAV"),
        &ObservationAllowlist::default(),
    );
    assert_eq!(error, Err(KnowledgeError::FixturePath));
}

#[test]
fn fixture_rejection() {
    let mut repository = KnowledgeRepository::new();
    let allowlist = ObservationAllowlist::default();

    // B1: packages/fixtures/** paths are refused before any content is inspected.
    assert_eq!(
        repository.ingest_assertion(
            Path::new("packages/fixtures/ontology/abox_cases.json"),
            pending("rej:01ARZ3NDEKTSV4RRFFQ69G5FAV"),
            &allowlist,
        ),
        Err(KnowledgeError::FixturePath)
    );

    // B2: an accepted assertion whose origin is fixture is refused.
    assert_eq!(
        repository.ingest_assertion(
            Path::new("incoming/a.json"),
            accepted(
                "rej:01ARZ3NDEKTSV4RRFFQ69G5FAW",
                "fixture",
                Some("rd:01ARZ3NDEKTSV4RRFFQ69G5FAV"),
            ),
            &allowlist,
        ),
        Err(KnowledgeError::FixtureAccepted)
    );

    // B3: changing the origin to pipeline but removing the review decision is still refused.
    assert_eq!(
        repository.ingest_assertion(
            Path::new("incoming/b.json"),
            accepted("rej:01ARZ3NDEKTSV4RRFFQ69G5FAX", "pipeline", None),
            &allowlist,
        ),
        Err(KnowledgeError::AcceptedWithoutDecision)
    );
}

#[test]
fn profile_historical_vs_service() {
    // (a) The historical-fixture profile reads a fixture A-box as discussion material.
    let mut abox = Abox::default();
    abox.section_mut("assertions").push(json!({
        "id": "hist:01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "subject": "coverage:test",
        "predicate": "label",
        "value": "fixture_value",
        "criticality": "C1",
        "value_state": "observed",
        "review_status": "accepted",
        "evidence": [],
        "origin": "fixture",
        "decision": {"by": "fixture_assumption"}
    }));
    let view = candidate_view(&abox).unwrap();
    let historical = check_constraints(&view, &CheckProfile::historical_fixture(None));
    assert!(
        !historical
            .iter()
            .any(|v| v.code == onjeon_ontology::check::PROFILE_VIOLATION),
        "historical_fixture profile must allow fixture assumptions"
    );

    // (b) The service-conformance profile rejects the same fixture A-box.
    let service = check_constraints(&view, &CheckProfile::service_conformance(None));
    assert!(
        service
            .iter()
            .any(|v| v.code == onjeon_ontology::check::PROFILE_VIOLATION),
        "service_conformance profile must flag accepted fixture-origin claims"
    );

    // The service ingestion gate enforces the same rejection for individual assertions.
    let mut repository = KnowledgeRepository::new();
    let b2 = repository.ingest_assertion(
        Path::new("incoming/assertion.json"),
        accepted(
            "a:01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "fixture",
            Some("rd:missing"),
        ),
        &ObservationAllowlist::default(),
    );
    assert_eq!(b2, Err(KnowledgeError::FixtureAccepted));

    let b3 = repository.ingest_assertion(
        Path::new("incoming/assertion.json"),
        accepted("a:01ARZ3NDEKTSV4RRFFQ69G5FAW", "pipeline", None),
        &ObservationAllowlist::default(),
    );
    assert_eq!(b3, Err(KnowledgeError::AcceptedWithoutDecision));
}

#[test]
fn accepted_requires_a_complete_review_decision() {
    let mut repository = KnowledgeRepository::new();
    let decision = valid_decision();
    let decision_id = decision.id.clone();
    repository.insert_review_decision(decision).unwrap();
    repository
        .ingest_assertion(
            Path::new("incoming/assertion.json"),
            accepted(
                "a:01ARZ3NDEKTSV4RRFFQ69G5FAV",
                "pipeline",
                Some(&decision_id),
            ),
            &ObservationAllowlist::default(),
        )
        .unwrap();
}

#[test]
fn allowlist_extracts_sha256_from_archive_listing() {
    let listing = json!({
        "archive": {
            "items": [
                {"sha256": "a".repeat(64)},
                {"content_sha256": "b".repeat(64)},
                {"checksum_sha256": "c".repeat(64)},
                {"sha256": "not-a-hash"},
                {"sha256": "D".repeat(64)}
            ]
        }
    });
    let allowlist = ObservationAllowlist::from_archive_listing(&listing);
    assert!(allowlist.contains(&"a".repeat(64)));
    assert!(allowlist.contains(&"b".repeat(64)));
    assert!(allowlist.contains(&"c".repeat(64)));
    assert!(!allowlist.contains("not-a-hash"));
    assert!(!allowlist.contains(&"D".repeat(64)));
}

#[test]
fn r2_allowlist_applies_to_raw_evidence() {
    let hash = "b".repeat(64);
    let mut repository = KnowledgeRepository::new();
    repository
        .insert_record(
            "raw_assets",
            json!({"id": format!("raw:sha256:{hash}"), "sha256": hash}),
        )
        .unwrap();
    let mut assertion = pending("a:01ARZ3NDEKTSV4RRFFQ69G5FAV");
    assertion["evidence"] = json!([{"ref": format!("raw:sha256:{hash}"), "role": "observation"}]);
    assert!(matches!(
        repository.ingest_assertion(
            Path::new("incoming/a.json"),
            assertion.clone(),
            &ObservationAllowlist::default()
        ),
        Err(KnowledgeError::HashNotObserved(_))
    ));
    repository
        .ingest_assertion(
            Path::new("incoming/a.json"),
            assertion,
            &ObservationAllowlist::new([hash]),
        )
        .unwrap();
}

#[test]
fn price_raw_kept_comparison_gated() {
    let mut repository = KnowledgeRepository::new();
    let raw = json!({
        "id": "premium:01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "evidence": [{"ref": "obs:source", "role": "observation"}],
        "raw_amount": 12000,
        "observed_at": "2026-10-19T00:00:00Z",
        "missing_dimensions": ["conditions", "package_binding", "source_as_of"],
        "comparison_eligible": false,
        "review_status": "pending"
    });
    repository.insert_premium(raw).unwrap();
    assert!(repository
        .get("premium_observations", "premium:01ARZ3NDEKTSV4RRFFQ69G5FAV")
        .is_some());

    let invalid_eligible = json!({
        "id": "premium:01ARZ3NDEKTSV4RRFFQ69G5FAW",
        "evidence": [{"ref": "obs:source", "role": "observation"}],
        "raw_amount": 12000,
        "observed_at": "2026-10-19T00:00:00Z",
        "missing_dimensions": ["conditions"],
        "comparison_eligible": true,
        "review_status": "accepted"
    });
    assert!(matches!(
        repository.insert_premium(invalid_eligible),
        Err(KnowledgeError::InvalidPremium(_))
    ));
}

#[test]
fn gap_and_acquisition_task_states_are_independent() {
    let mut repository = KnowledgeRepository::new();
    repository
        .insert_gap(json!({
            "id": "gap:01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "subject": "coverage:test",
            "status": "not_found"
        }))
        .unwrap();
    repository
        .insert_task(AcquisitionTask {
            id: "task:01ARZ3NDEKTSV4RRFFQ69G5FAV".to_owned(),
            gap_id: "gap:01ARZ3NDEKTSV4RRFFQ69G5FAV".to_owned(),
            state: "queued".to_owned(),
            attempts: 0,
        })
        .unwrap();
    repository
        .update_task_state("task:01ARZ3NDEKTSV4RRFFQ69G5FAV", "running")
        .unwrap();
    assert_eq!(
        repository
            .task("task:01ARZ3NDEKTSV4RRFFQ69G5FAV")
            .unwrap()
            .state,
        "running"
    );
    assert_eq!(
        repository
            .get("gaps", "gap:01ARZ3NDEKTSV4RRFFQ69G5FAV")
            .unwrap()["status"],
        "not_found"
    );
}

#[test]
fn violating_candidate_is_not_promoted() {
    let mut repository = KnowledgeRepository::new();
    repository
        .insert_record(
            "nodes",
            json!({
                "id": "contract:private",
                "kind": "Coverage",
                "origin": "pipeline"
            }),
        )
        .unwrap();
    let result = repository.promote_candidate("candidate:bad", None);
    assert!(matches!(
        result,
        Err(KnowledgeError::ConstraintViolation(_))
    ));
    assert!(!repository.is_promoted("candidate:bad"));
}
