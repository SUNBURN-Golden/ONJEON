use onjeon_knowledge::{
    AcquisitionTask, KnowledgeError, KnowledgeRepository, ObservationAllowlist, ReviewDecision,
};
use serde_json::{json, Value};
use std::collections::BTreeSet;
use std::path::Path;

fn pending(id: &str) -> Value {
    json!({
        "id": id,
        "subject": "coverage:test",
        "predicate": "label",
        "value": "test",
        "criticality": "c1",
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
        provider_family_labels: vec!["fixture_family_a".into(), "fixture_family_b".into()],
        prompt_version: "test-v1".into(),
        decided_at: "2026-10-23T00:00:00Z".into(),
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
    assert!(repository
        .check_candidate(None)
        .unwrap()
        .iter()
        .any(|v| v.code == "K10"));
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
    assert!(!repository
        .check_candidate(None)
        .unwrap()
        .iter()
        .any(|v| v.code == "K10"));
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
    let raw_asset = json!({"id": format!("raw:sha256:{hash}"), "sha256": hash});
    // The loader itself is allowlist-gated: an unlisted hash never becomes a raw asset.
    assert!(matches!(
        repository.insert_record("raw_assets", raw_asset.clone()),
        Err(KnowledgeError::HashNotObserved(_))
    ));
    repository.set_allowlist(ObservationAllowlist::new([hash.clone()]));
    repository.insert_record("raw_assets", raw_asset).unwrap();
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
    repository.set_allowlist(ObservationAllowlist::new(["b".repeat(64)]));
    repository
        .insert_record(
            "raw_assets",
            json!({"id": format!("raw:sha256:{}", "b".repeat(64)), "sha256":"b".repeat(64)}),
        )
        .unwrap();
    let raw = json!({
        "id": "premium:01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "evidence": [{"ref": "raw:sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "role": "observation"}],
        "raw_amount": 12000,
        "observed_at": "2026-10-19T00:00:00Z",
        "missing_dimensions": ["conditions", "package_binding", "as_of"],
        "comparison_eligible": false,
        "review_status": "pending"
    });
    repository.insert_premium(raw).unwrap();
    assert!(repository
        .get("premium_observations", "premium:01ARZ3NDEKTSV4RRFFQ69G5FAV")
        .is_some());

    let invalid_eligible = json!({
        "id": "premium:01ARZ3NDEKTSV4RRFFQ69G5FAW",
        "evidence": [{"ref": "raw:sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "role": "observation"}],
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

fn source(repo: &mut KnowledgeRepository) -> (String, String, String) {
    let raw = format!("raw:sha256:{}", "b".repeat(64));
    let segment = "seg:bbbbbbbbbbbb:p1-3:terms:v1".to_owned();
    let clause = format!("clause:{segment}/art1#p1:text@1.0");
    repo.set_allowlist(ObservationAllowlist::new(["b".repeat(64)]));
    repo.insert_record("raw_assets", json!({"id":raw,"sha256":"b".repeat(64)}))
        .unwrap();
    repo.insert_record(
        "segments",
        json!({"id":segment,"raw_asset_id":raw,"doc_role":"terms"}),
    )
    .unwrap();
    repo.insert_record("clauses", json!({"id":clause,"segment_id":segment}))
        .unwrap();
    repo.insert_record("observations", json!({"id":"obs:test","raw_asset_id":raw}))
        .unwrap();
    (raw, segment, clause)
}

#[test]
fn canonical_c0_is_checked_and_cannot_be_promoted() {
    let mut repo = KnowledgeRepository::new();
    let d = valid_decision();
    repo.insert_review_decision(d.clone()).unwrap();
    let mut a = accepted("a:c0", "pipeline", Some(&d.id));
    a["criticality"] = json!("c0");
    repo.ingest_assertion(
        Path::new("incoming/a.json"),
        a,
        &ObservationAllowlist::default(),
    )
    .unwrap();
    assert!(repo
        .check_candidate(None)
        .unwrap()
        .iter()
        .any(|v| v.code == "K1"));
    assert!(matches!(
        repo.promote_candidate("candidate:c0", None),
        Err(KnowledgeError::ConstraintViolation(_))
    ));
    assert!(!repo.is_promoted("candidate:c0"));
}

#[test]
fn indirect_evidence_and_candidate_recheck_the_current_allowlist() {
    for kind in ["clause", "seg", "obs", "premium"] {
        let mut repo = KnowledgeRepository::new();
        let (raw, segment, clause) = source(&mut repo);
        let allow = ObservationAllowlist::new(["b".repeat(64)]);
        repo.set_allowlist(allow.clone());
        repo.insert_premium(json!({"id":"premium:source", "raw_amount":1,"observed_at":"2026-10-23T00:00:00Z",
            "evidence":[{"ref":raw,"role":"observation"}],"missing_dimensions":["conditions","package_binding","as_of"],
            "comparison_eligible":false,"review_status":"pending","origin":"pipeline"})).unwrap();
        let reference = match kind {
            "clause" => clause,
            "seg" => segment,
            "obs" => "obs:test".into(),
            _ => "premium:source".into(),
        };
        let mut a = pending("a:indirect");
        a["evidence"] = json!([{"ref":reference,"role":"observation"}]);
        assert!(
            matches!(
                repo.ingest_assertion(
                    Path::new("incoming/a.json"),
                    a.clone(),
                    &ObservationAllowlist::default()
                ),
                Err(KnowledgeError::HashNotObserved(_))
            ),
            "{kind}"
        );
        repo.ingest_assertion(Path::new("incoming/a.json"), a, &allow)
            .unwrap();
        assert!(repo.check_candidate(None).unwrap().is_empty());
        repo.set_allowlist(ObservationAllowlist::default());
        assert!(repo
            .check_candidate(None)
            .unwrap()
            .iter()
            .any(|v| v.code == "B4"));
        assert!(repo
            .promote_candidate("candidate:unobserved", None)
            .is_err());
    }
    let mut repo = KnowledgeRepository::new();
    let mut a = pending("a:missing");
    a["evidence"] = json!([{"ref":"clause:missing","role":"basis"}]);
    assert_eq!(
        repo.ingest_assertion(
            Path::new("incoming/a.json"),
            a,
            &ObservationAllowlist::default()
        ),
        Err(KnowledgeError::MissingTarget("clause:missing".into()))
    );
}

fn eligible_premium(id: &str, reference: &str) -> Value {
    json!({"id":id,"raw_amount":12000,"evidence":[{"ref":reference,"role":"observation"}],
        "observed_at":"2026-10-23T00:00:00Z","conditions":{"age":40},"package_binding":"base",
        "source_as_of":"2026-10-23","comparison_basis_id":"basis:test","comparison_eligible":true,
        "missing_dimensions":[],"review_status":"accepted","origin":"pipeline"})
}

#[test]
fn accepted_prices_require_origin_and_real_review_decision() {
    let mut repo = KnowledgeRepository::new();
    let (raw, _, _) = source(&mut repo);
    repo.set_allowlist(ObservationAllowlist::new(["b".repeat(64)]));
    let mut p = eligible_premium("premium:eligible", &raw);
    p["origin"] = json!("fixture");
    assert_eq!(
        repo.insert_premium(p.clone()),
        Err(KnowledgeError::FixtureAccepted)
    );
    p["origin"] = json!("pipeline");
    assert_eq!(
        repo.insert_premium(p.clone()),
        Err(KnowledgeError::AcceptedWithoutDecision)
    );
    p["review_decision_id"] = json!("rd:missing");
    assert_eq!(
        repo.insert_premium(p.clone()),
        Err(KnowledgeError::InvalidDecision)
    );
    let mut d = valid_decision();
    d.code_checks_passed = false;
    repo.insert_review_decision(d.clone()).unwrap();
    p["review_decision_id"] = json!(d.id);
    assert_eq!(
        repo.insert_premium(p.clone()),
        Err(KnowledgeError::InvalidDecision)
    );
    let mut good = valid_decision();
    good.id = "rd:good".into();
    repo.insert_review_decision(good.clone()).unwrap();
    p["review_decision_id"] = json!(good.id);
    repo.insert_premium(p).unwrap();
    assert!(repo.check_candidate(None).unwrap().is_empty());
    repo.promote_candidate("candidate:eligible-price", None)
        .unwrap();
}

#[test]
fn real_r2_listings_extract_all_58_verified_hashes() {
    let root =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../../docs/blueprint/validation/source_checks");
    for name in ["archive_listing_raw.json", "2026-10-09_r2_listing_raw.json"] {
        let listing: Value =
            serde_json::from_slice(&std::fs::read(root.join(name)).unwrap()).unwrap();
        let allow = ObservationAllowlist::from_archive_listing(&listing);
        assert_eq!(allow.len(), 58, "{name}");
        assert!(allow.contains("052dd4693601b0f5d4bf9ffb5b1f3bc47b39be0c9ad6706b36eaeb6929be4032"));
    }
    let failed = json!({"results":[{"status":"mismatch","sha256_source":"b".repeat(64),"sha256_downloaded":"c".repeat(64)}]});
    assert!(ObservationAllowlist::from_archive_listing(&failed).is_empty());
}

#[test]
fn b1_normalizes_parent_paths_and_forbids_blueprint_and_symlinks() {
    for path in [
        "packages/tmp/../fixtures/ontology/a.json",
        "docs/tmp/../blueprint/a.json",
        "packages/fixtures/../fixtures/a.json",
        "docs/blueprint/a.json",
        "./packages/fixtures/a.json",
    ] {
        assert_eq!(
            KnowledgeRepository::new().ingest_assertion(
                Path::new(path),
                pending("a:path"),
                &ObservationAllowlist::default()
            ),
            Err(KnowledgeError::FixturePath),
            "{path}"
        );
    }
    #[cfg(unix)]
    {
        let target = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../packages/fixtures")
            .canonicalize()
            .unwrap();
        let link = std::env::temp_dir().join(format!("kn04-link-{}", std::process::id()));
        std::os::unix::fs::symlink(target, &link).unwrap();
        let result = KnowledgeRepository::new().ingest_assertion(
            &link.join("ontology/a.json"),
            pending("a:path"),
            &ObservationAllowlist::default(),
        );
        std::fs::remove_file(link).unwrap();
        assert_eq!(result, Err(KnowledgeError::FixturePath));
    }
}

#[test]
fn edition_conflict_uses_actual_segments_editions_and_clauses() {
    let mut repo = KnowledgeRepository::new();
    let allow = ObservationAllowlist::new(["a".repeat(64), "b".repeat(64)]);
    repo.set_allowlist(allow.clone());
    let fingerprint = json!({"rule":"fp-1","sha256":"c".repeat(64)});
    let segments = ["seg:combined", "seg:individual"];
    let clauses = ["clause:combined", "clause:individual"];
    // A combined terms file and an individual rider file contain the same body.
    for (i, hash) in ["a".repeat(64), "b".repeat(64)].into_iter().enumerate() {
        let raw = format!("raw:sha256:{hash}");
        repo.insert_record("raw_assets", json!({"id":raw,"sha256":hash}))
            .unwrap();
        repo.insert_record(
            "segments",
            json!({"id":segments[i],"raw_asset_id":raw,
            "doc_role":"rider_terms","fingerprint":fingerprint}),
        )
        .unwrap();
        repo.insert_record("clauses", json!({"id":clauses[i],"segment_id":segments[i]}))
            .unwrap();
    }
    repo.insert_record(
        "terms_editions",
        json!({"id":"ted:same",
        "parts":[{"role":"body","fingerprint":fingerprint}]}),
    )
    .unwrap();
    let d = valid_decision();
    repo.insert_review_decision(d.clone()).unwrap();
    for (i, segment) in segments.iter().enumerate() {
        let mut realizes = accepted(&format!("a:realizes-{i}"), "pipeline", Some(&d.id));
        realizes["predicate"] = json!("realizes");
        realizes["subject"] = json!(segment);
        realizes["object"] = json!("ted:same");
        realizes["criticality"] = json!("c0");
        realizes.as_object_mut().unwrap().remove("value");
        realizes["decision"] = json!({"by":"review_decision"});
        realizes["evidence"] = json!([{"ref":segment,"role":"observation"}]);
        repo.ingest_assertion(Path::new("incoming/realizes.json"), realizes, &allow)
            .unwrap();
    }
    assert!(repo.check_candidate(None).unwrap().is_empty());
    assert!(repo.list("conflicts").is_empty());
    assert_eq!(repo.list("terms_editions").len(), 1);

    let mut base = pending("a:edition-base");
    base["subject"] = json!("ted:same");
    base["scope"] = json!({"document":"ted:same"});
    base["evidence"] = json!([{"ref":clauses[0],"role":"observation"}]);
    repo.ingest_assertion(Path::new("incoming/base.json"), base.clone(), &allow)
        .unwrap();
    let mut first = base;
    first["id"] = json!("a:edition-first");
    first["supersedes"] = json!("a:edition-base");
    let mut second = first.clone();
    second["id"] = json!("a:edition-second");
    second["value"] = json!("incompatible correction");
    second["evidence"] = json!([{"ref":clauses[1],"role":"observation"}]);
    for a in [first, second] {
        repo.ingest_assertion(Path::new("incoming/corrections.json"), a, &allow)
            .unwrap();
    }
    assert!(repo
        .check_candidate(None)
        .unwrap()
        .iter()
        .any(|v| v.code == "K10"));
    repo.insert_conflict(json!({"id":"conflict:edition",
        "assertions":["a:edition-first","a:edition-second"],
        "reason":"incompatible corrections about the same scope"}))
        .unwrap();
    assert!(repo.check_candidate(None).unwrap().is_empty());
    assert_eq!(repo.conflicts_for("a:edition-first").len(), 1);
}

/// `public.node` shape: the class is the `kind` column and ontology attributes are `attrs`.
fn sql_node(id: &str, attrs: Value) -> Value {
    json!({"id": id, "kind": "Condition", "label": "fixture_only", "attrs": attrs,
        "origin": "pipeline", "onto_version": "onto-0.2"})
}

#[test]
fn canonical_fingerprint_columns_gate_edition_confirmation() {
    let alias = json!({"rule":"fp-1","sha256":"d".repeat(64)});
    for (rule, hash, expected_code) in [
        (json!("fp-1"), json!("c".repeat(64)), Some("K16")),
        (json!("fp-2"), json!("d".repeat(64)), Some("K16")),
        (Value::Null, Value::Null, Some("K14")),
        (json!("fp-1"), Value::Null, Some("K14")),
        (Value::Null, json!("d".repeat(64)), Some("K14")),
        (json!("fp-1"), json!("d".repeat(64)), None),
    ] {
        let mut repo = KnowledgeRepository::new();
        let extension = if expected_code.is_none() {
            json!({"rule":"fp-2","sha256":"c".repeat(64)})
        } else {
            alias.clone()
        };
        let allow = ObservationAllowlist::new(["b".repeat(64)]);
        repo.set_allowlist(allow.clone());
        let raw = format!("raw:sha256:{}", "b".repeat(64));
        repo.insert_record("raw_assets", json!({"id":raw,"sha256":"b".repeat(64)}))
            .unwrap();
        repo.insert_record(
            "segments",
            json!({"id":"seg:fixture_only","raw_asset_id":raw,
            "doc_role":"terms","fingerprint_rule":rule,"fingerprint_sha256":hash,
            "fingerprint":extension}),
        )
        .unwrap();
        repo.insert_record(
            "terms_editions",
            json!({"id":"ted:fixture_only",
            "parts":[{"role":"body","fingerprint":alias}]}),
        )
        .unwrap();
        let d = valid_decision();
        repo.insert_review_decision(d.clone()).unwrap();
        let mut realizes = accepted("a:fixture_only", "pipeline", Some(&d.id));
        realizes["subject"] = json!("seg:fixture_only");
        realizes["predicate"] = json!("realizes");
        realizes["object"] = json!("ted:fixture_only");
        realizes.as_object_mut().unwrap().remove("value");
        realizes["evidence"] = json!([{"ref":"seg:fixture_only","role":"observation"}]);
        repo.ingest_assertion(Path::new("incoming/fixture_only.json"), realizes, &allow)
            .unwrap();
        let violations = repo.check_candidate(None).unwrap();
        if let Some(code) = expected_code {
            assert!(
                violations.iter().any(|v| v.code == code),
                "{rule}/{hash}: {violations:?}"
            );
            assert!(matches!(
                repo.promote_candidate("candidate:fixture_only", None),
                Err(KnowledgeError::ConstraintViolation(_))
            ));
            assert!(!repo.is_promoted("candidate:fixture_only"));
        } else {
            assert!(violations.is_empty(), "{violations:?}");
            repo.promote_candidate("candidate:fixture_only", None)
                .unwrap();
        }
    }
}

#[test]
fn canonical_node_kind_overrides_conflicting_classes() {
    for attrs in [json!({}), json!({"class":"Organization"})] {
        let mut repo = KnowledgeRepository::new();
        repo.insert_record(
            "nodes",
            json!({"id":"codes:fixture_only","kind":"CodeSet",
            "class":"Organization","attrs":attrs,"origin":"pipeline"}),
        )
        .unwrap();
        let violations = repo.check_candidate(None).unwrap();
        assert_eq!(
            violations.iter().filter(|v| v.code == "K3").count(),
            4,
            "{violations:?}"
        );
        assert!(matches!(
            repo.promote_candidate("candidate:fixture_only", None),
            Err(KnowledgeError::ConstraintViolation(_))
        ));
        assert!(!repo.is_promoted("candidate:fixture_only"));
    }
}

fn has_condition(id: &str, node: &str) -> Value {
    let mut a = pending(id);
    a["predicate"] = json!("has_condition");
    a["object"] = json!(node);
    a.as_object_mut().unwrap().remove("value");
    a
}

#[test]
fn k7_reads_reductions_in_the_persisted_node_shape() {
    let cases = [
        (json!({"kind": "감액", "anchor": "계약일"}), true),
        (
            json!({"kind": "감액", "anchor": "계약일", "applies_to": ["최초계약"]}),
            false,
        ),
        (json!({"kind": "감액", "value": "없음"}), false),
        (json!({"kind": "보장개시", "anchor": "계약일"}), false),
    ];
    for (attrs, violates) in cases {
        let mut repo = KnowledgeRepository::new();
        repo.insert_record("nodes", sql_node("cond:reduction", attrs.clone()))
            .unwrap();
        repo.ingest_assertion(
            Path::new("incoming/a.json"),
            has_condition("a:reduction", "cond:reduction"),
            &ObservationAllowlist::default(),
        )
        .unwrap();
        let violations = repo.check_candidate(None).unwrap();
        assert_eq!(
            violations.iter().any(|v| v.code == "K7"),
            violates,
            "{attrs}: {violations:?}"
        );
        assert_eq!(
            repo.promote_candidate("candidate:reduction", None).is_ok(),
            !violates,
            "{attrs}"
        );
        assert_eq!(repo.is_promoted("candidate:reduction"), !violates);
    }
}

#[test]
fn ontology_shaped_nodes_keep_their_class() {
    // Here `kind` is the 감액 attribute, not the class; K5 only fires for class Condition.
    let mut repo = KnowledgeRepository::new();
    repo.insert_record(
        "nodes",
        json!({"id":"cond:reduction","class":"Condition","kind":"감액",
            "anchor":"fixture_only_unknown_anchor","origin":"pipeline"}),
    )
    .unwrap();
    repo.ingest_assertion(
        Path::new("incoming/a.json"),
        has_condition("a:reduction", "cond:reduction"),
        &ObservationAllowlist::default(),
    )
    .unwrap();
    let codes: BTreeSet<String> = repo
        .check_candidate(None)
        .unwrap()
        .into_iter()
        .map(|v| v.code)
        .collect();
    assert!(codes.contains("K7") && codes.contains("K5"), "{codes:?}");
}

fn scope_relation(id: &str, subject: &str, object: &str, relation: &str) -> Value {
    let mut a = pending(id);
    a["subject"] = json!(subject);
    a["predicate"] = json!("scope_relation");
    a["object"] = json!(object);
    a["value"] = json!(relation);
    a
}

#[test]
fn scope_relations_keep_object_and_value_for_k4_and_k12() {
    let allow = ObservationAllowlist::default();
    let mut repo = KnowledgeRepository::new();
    for a in [
        scope_relation("a:ab", "cat:a", "cat:b", "narrower"),
        scope_relation("a:ba", "cat:b", "cat:a", "narrower"),
    ] {
        repo.ingest_assertion(Path::new("incoming/scope.json"), a, &allow)
            .unwrap();
    }
    let violations = repo.check_candidate(None).unwrap();
    assert!(violations.iter().any(|v| v.code == "K4"), "{violations:?}");
    assert!(matches!(
        repo.promote_candidate("candidate:cycle", None),
        Err(KnowledgeError::ConstraintViolation(_))
    ));
    // An accepted relation without a code universe cannot be computed: K12.
    let mut repo = KnowledgeRepository::new();
    let d = valid_decision();
    repo.insert_review_decision(d.clone()).unwrap();
    let mut a = scope_relation("a:accepted", "cat:a", "cat:b", "narrower");
    a["review_status"] = json!("accepted");
    a["review_decision_id"] = json!(d.id);
    repo.ingest_assertion(Path::new("incoming/accepted.json"), a, &allow)
        .unwrap();
    let violations = repo.check_candidate(None).unwrap();
    assert!(violations.iter().any(|v| v.code == "K12"), "{violations:?}");
}

#[test]
fn raw_assets_are_allowlisted_at_load_and_at_candidate_check() {
    let hash = "b".repeat(64);
    let mut repo = KnowledgeRepository::new();
    repo.set_allowlist(ObservationAllowlist::new([hash.clone()]));
    assert!(matches!(
        repo.insert_record(
            "raw_assets",
            json!({"id": format!("raw:sha256:{}", "c".repeat(64)), "sha256": "c".repeat(64)})
        ),
        Err(KnowledgeError::HashNotObserved(_))
    ));
    assert!(matches!(
        repo.insert_record(
            "raw_assets",
            json!({"id": "raw:sha256:mismatch", "sha256": hash})
        ),
        Err(KnowledgeError::InvalidShape(_))
    ));
    repo.insert_record(
        "raw_assets",
        json!({"id": format!("raw:sha256:{hash}"), "sha256": hash}),
    )
    .unwrap();
    assert!(repo.check_candidate(None).unwrap().is_empty());
    repo.promote_candidate("candidate:listed", None).unwrap();
    // The listing is re-read at candidate time even when no assertion references the asset.
    repo.set_allowlist(ObservationAllowlist::default());
    let violations = repo.check_candidate(None).unwrap();
    assert!(violations.iter().any(|v| v.code == "B4"), "{violations:?}");
    assert!(matches!(
        repo.promote_candidate("candidate:unlisted", None),
        Err(KnowledgeError::ConstraintViolation(_))
    ));
    assert!(!repo.is_promoted("candidate:unlisted"));
}
