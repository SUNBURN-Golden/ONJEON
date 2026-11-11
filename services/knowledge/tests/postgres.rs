//! Writes only to the disposable DB created by ../test.sh. Never silently skips.
use onjeon_knowledge::{
    AcquisitionTask, KnowledgeError, KnowledgeRepository, ObservationAllowlist, ReviewDecision,
};
use postgres::{Client, NoTls};
use serde_json::{json, Value};
use std::path::Path;
fn id(prefix: &str, n: u32) -> String {
    format!("{prefix}:{n:026}")
}
fn decision() -> ReviewDecision {
    ReviewDecision {
        id: id("rd", 1),
        environment: "test".into(),
        outcome: "accepted".into(),
        provider_family_labels: vec!["fixture_family_a".into(), "fixture_family_b".into()],
        families_count: 2,
        code_checks_passed: true,
        redteam_counterexamples: 0,
        cross_doc_conflict_free: true,
        audit_log_sha256: "d".repeat(64),
        prompt_version: "fixture-v1".into(),
        decided_at: "2026-10-23T00:00:00Z".into(),
    }
}
fn assertion(n: u32, raw: &str) -> Value {
    json!({"id":id("a",n),"subject":"concept:test","predicate":"label","value":{"raw":"fixture_only","normalized":"fixture_only"},
        "scope":{},"recorded_at":"2026-10-23T00:00:00Z","observed_at":"2026-10-23T00:00:00Z",
        "evidence":[{"ref":raw,"role":"observation"}],"criticality":"c1","value_state":"observed",
        "review_status":"pending","extractor_tool":"fixture_only","extractor_version":"v1","origin":"pipeline",
        "onto_version":"onto-0.2","created_by_run":"fixture_only"})
}
fn raw_price(n: u32, raw: &str) -> Value {
    json!({"id":id("premium",n),"raw_amount":12000,"price_basis":"illustrative",
        "evidence":[{"ref":raw,"role":"observation"}],"observed_at":"2026-10-23T00:00:00Z",
        "comparison_eligible":false,"missing_dimensions":["conditions","package_binding","as_of"],
        "value_state":"observed","review_status":"pending","origin":"pipeline"})
}
fn db_insert(c: &mut Client, table: &str, v: &Value) -> postgres::Error {
    let columns = v
        .as_object()
        .unwrap()
        .keys()
        .map(|s| format!("\"{s}\""))
        .collect::<Vec<_>>()
        .join(",");
    c.execute(&format!("INSERT INTO {table} ({columns}) SELECT {columns} FROM jsonb_populate_record(NULL::{table}, $1)"),&[v]).unwrap_err()
}
fn constraint(e: postgres::Error, name: &str) {
    assert_eq!(e.as_db_error().and_then(|e| e.constraint()), Some(name));
}

// Clone the empty, migrated database, so independent regressions cannot mask one
// another's promotion failures. test.sh removes the whole disposable cluster.
fn isolated_database(name: &str) -> String {
    assert!(name.chars().all(|c| c.is_ascii_lowercase() || c == '_'));
    let base = std::env::var("ONJEON_KNOWLEDGE_TEST_DB")
        .expect("test.sh must provide a disposable database");
    let mut config: postgres::Config = base.parse().unwrap();
    config.dbname("postgres");
    config
        .connect(NoTls)
        .unwrap()
        .execute(
            &format!("CREATE DATABASE {name} TEMPLATE knowledge_fixture_only"),
            &[],
        )
        .unwrap();
    format!("{base} dbname={name}")
}

#[test]
#[ignore = "requires disposable PostgreSQL; run bash services/knowledge/test.sh"]
fn canonical_segment_fingerprint_blocks_extension_bypass_after_reconnect() {
    for (name, canonical_rule, canonical_hash, violates) in [
        ("fixture_only_hash", "fp-1", "c".repeat(64), true),
        ("fixture_only_rule", "fp-2", "d".repeat(64), true),
        ("fixture_only_matching", "fp-1", "c".repeat(64), false),
    ] {
        let config = isolated_database(name);
        let mut admin = Client::connect(&config, NoTls).unwrap();
        let allow = ObservationAllowlist::new(["b".repeat(64)]);
        let raw = format!("raw:sha256:{}", "b".repeat(64));
        let segment = "seg:bbbbbbbbbbbb:p1-3:terms:v1";
        let alias = json!({"rule":"fp-1","sha256":"d".repeat(64)});
        let edition_fingerprint = if violates {
            alias.clone()
        } else {
            json!({"rule":canonical_rule,"sha256":canonical_hash})
        };
        let mut repo = KnowledgeRepository::connect(
            &format!("{config} options='-c role=data_writer'"),
            allow.clone(),
        )
        .unwrap();
        repo.insert_record(
            "raw_assets",
            json!({"id":raw,"sha256":"b".repeat(64),
            "byte_length":1,"media_type":"application/pdf","storage_key":"fixture_only"}),
        )
        .unwrap();
        repo.insert_record(
            "segments",
            json!({"id":segment,"raw_asset_id":raw,
            "page_from":1,"page_to":3,"doc_role":"terms","seg_rule_ver":"v1",
            "fingerprint_rule":canonical_rule,"fingerprint_sha256":canonical_hash,
            "fingerprint":alias}),
        )
        .unwrap();
        drop(repo);
        let writer = format!("{config} options='-c role=knowledge_writer'");
        let mut repo = KnowledgeRepository::connect(&writer, allow.clone()).unwrap();
        repo.insert_review_decision(decision()).unwrap();
        repo.insert_record(
            "terms_editions",
            json!({"id":id("ted",1),"label":"fixture_only",
            "parts":[{"role":"body","fingerprint":edition_fingerprint}]}),
        )
        .unwrap();
        let mut realizes = assertion(1, &raw);
        realizes["subject"] = json!(segment);
        realizes["predicate"] = json!("realizes");
        realizes.as_object_mut().unwrap().remove("value");
        realizes["object"] = json!(id("ted", 1));
        realizes["criticality"] = json!("c0");
        realizes["review_status"] = json!("accepted");
        realizes["review_decision_id"] = json!(id("rd", 1));
        realizes["evidence"] = json!([{"ref":segment,"role":"observation"}]);
        repo.ingest_assertion(Path::new("incoming/fixture_only.json"), realizes, &allow)
            .unwrap();
        drop(repo);
        let mut repo = KnowledgeRepository::connect(&writer, allow).unwrap();
        // Both representations really survive in PostgreSQL; the checker must use SQL.
        let stored = admin
            .query_one(
                "SELECT fingerprint_rule, fingerprint_sha256, \
            (SELECT payload->'fingerprint' FROM knowledge.record_extension \
             WHERE section='segments' AND id=$1) FROM public.document_segment WHERE id=$1",
                &[&segment],
            )
            .unwrap();
        assert_eq!(stored.get::<_, String>(0), canonical_rule);
        assert_eq!(stored.get::<_, String>(1), canonical_hash);
        assert_eq!(stored.get::<_, Value>(2), alias);
        let violations = repo.check_candidate(None).unwrap();
        if violates {
            assert!(violations.iter().any(|v| v.code == "K16"), "{violations:?}");
            assert!(matches!(
                repo.promote_candidate("candidate:fixture_only", None),
                Err(KnowledgeError::ConstraintViolation(_))
            ));
            assert!(!repo.is_promoted("candidate:fixture_only"));
            assert_eq!(
                admin
                    .query_one("SELECT count(*) FROM knowledge.candidate", &[])
                    .unwrap()
                    .get::<_, i64>(0),
                0
            );
        } else {
            assert!(violations.is_empty(), "{violations:?}");
            repo.promote_candidate("candidate:fixture_only", None)
                .unwrap();
        }
    }
    println!("fixture_only: canonical fingerprint hash/rule override extension; K16 rejection after reconnect; canonical match promotion: PASS");
}

#[test]
#[ignore = "requires disposable PostgreSQL; run bash services/knowledge/test.sh"]
fn canonical_node_class_blocks_extension_bypass_after_reconnect() {
    let config = isolated_database("fixture_only_class");
    let mut admin = Client::connect(&config, NoTls).unwrap();
    let writer = format!("{config} options='-c role=knowledge_writer'");
    let mut repo = KnowledgeRepository::connect(&writer, ObservationAllowlist::default()).unwrap();
    // Omit attrs deliberately: the canonical DB default still distinguishes SQL shape.
    repo.insert_record(
        "nodes",
        json!({"id":"codes:fixture_only","kind":"CodeSet",
        "class":"Organization","label":"fixture_only","origin":"pipeline",
        "onto_version":"onto-0.2"}),
    )
    .unwrap();
    drop(repo);
    let mut repo = KnowledgeRepository::connect(&writer, ObservationAllowlist::default()).unwrap();
    let stored = repo.get("nodes", "codes:fixture_only").unwrap();
    assert_eq!(stored["kind"], "CodeSet");
    assert_eq!(stored["class"], "Organization");
    assert_eq!(stored["attrs"], json!({}));
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
    assert_eq!(
        admin
            .query_one("SELECT count(*) FROM knowledge.candidate", &[])
            .unwrap()
            .get::<_, i64>(0),
        0
    );
    println!("fixture_only: persisted kind overrides extension class after reconnect; K3 and promotion rejection: PASS");
}

#[test]
#[ignore = "requires disposable PostgreSQL; run bash services/knowledge/test.sh"]
fn persistence_restart_db_constraints_and_candidate_integration() {
    let config = isolated_database("fixture_only_restart");
    let allow = ObservationAllowlist::new(["b".repeat(64)]);
    let raw = format!("raw:sha256:{}", "b".repeat(64));
    let mut admin = Client::connect(&config, NoTls).unwrap();
    let mut repo = KnowledgeRepository::connect(
        &format!("{config} options='-c role=data_writer'"),
        allow.clone(),
    )
    .unwrap();
    repo.insert_record(
        "raw_assets",
        json!({"id":raw,"sha256":"b".repeat(64),"byte_length":1,
        "media_type":"application/pdf","storage_key":"fixture_only"}),
    )
    .unwrap();
    // Seed source rows through the data credential; subsequent service writes use
    // the actual knowledge_writer role and its T-CT-05 grants.
    let segment = "seg:bbbbbbbbbbbb:p1-3:terms:v1";
    let clause = format!("clause:{segment}/art1#p1:text@1.0");
    repo.insert_record("segments",json!({"id":segment,"raw_asset_id":raw,"page_from":1,"page_to":3,
        "doc_role":"terms","seg_rule_ver":"v1","fingerprint_rule":"fp-1","fingerprint_sha256":"c".repeat(64)})).unwrap();
    repo.insert_record(
        "clauses",
        json!({"id":clause,"segment_id":segment,"page":1,"quote_sha256":"e".repeat(64)}),
    )
    .unwrap();
    drop(repo);
    let config = format!("{config} options='-c role=knowledge_writer'");
    let mut repo = KnowledgeRepository::connect(&config, allow.clone()).unwrap();
    repo.insert_review_decision(decision()).unwrap();
    repo.ingest_assertion(Path::new("incoming/a.json"), assertion(1, &raw), &allow)
        .unwrap();
    let mut accepted = assertion(2, &raw);
    accepted["review_status"] = json!("accepted");
    accepted["review_decision_id"] = json!(id("rd", 1));
    repo.ingest_assertion(
        Path::new("incoming/accepted.json"),
        accepted.clone(),
        &allow,
    )
    .unwrap();
    repo.insert_gap(json!({"id":id("gap",1),"subject":"concept:test","status":"not_found"}))
        .unwrap();
    repo.insert_task(AcquisitionTask {
        id: id("task", 1),
        gap_id: id("gap", 1),
        state: "queued".into(),
        attempts: 0,
    })
    .unwrap();
    repo.update_task_state(&id("task", 1), "running").unwrap();
    repo.insert_premium(raw_price(1, &raw)).unwrap();
    let mut eligible = raw_price(2, &raw);
    eligible["conditions"] = json!({"age":40});
    eligible["package_binding"] = json!("base");
    eligible["source_as_of"] = json!("2026-10-23");
    eligible["comparison_basis_id"] = json!("basis:test");
    eligible["comparison_eligible"] = json!(true);
    eligible["missing_dimensions"] = json!([]);
    eligible["review_status"] = json!("accepted");
    eligible["review_decision_id"] = json!(id("rd", 1));
    repo.insert_premium(eligible.clone()).unwrap();
    assert!(repo.check_candidate(None).unwrap().is_empty());
    repo.promote_candidate("candidate:durable", None).unwrap();
    drop(repo);
    // New connection, reconstructed entirely from PostgreSQL, including raw prices.
    let mut repo = KnowledgeRepository::connect(&config, allow.clone()).unwrap();
    assert_eq!(repo.list("assertions").len(), 2);
    assert_eq!(repo.task(&id("task", 1)).unwrap().state, "running");
    assert_eq!(
        repo.get("gaps", &id("gap", 1)).unwrap()["status"],
        "not_found"
    );
    assert_eq!(repo.list("premium_observations").len(), 2);
    assert!(repo.is_promoted("candidate:durable"));
    assert!(repo.check_candidate(None).unwrap().is_empty());

    // B2: bypass the service and exercise the real public DB CHECK constraint.
    accepted["id"] = json!(id("a", 3));
    accepted["origin"] = json!("fixture");
    constraint(
        db_insert(&mut admin, "public.assertion", &accepted),
        "chk_fixture_never_accepted",
    );
    assert_eq!(
        repo.ingest_assertion(Path::new("incoming/fixture.json"), accepted.clone(), &allow),
        Err(KnowledgeError::FixtureAccepted)
    );
    // B3: a relabeled copy still has no decision. DB trigger and service both reject.
    accepted["origin"] = json!("pipeline");
    accepted
        .as_object_mut()
        .unwrap()
        .remove("review_decision_id");
    constraint(
        db_insert(&mut admin, "public.assertion", &accepted),
        "chk_accepted_needs_decision",
    );
    assert_eq!(
        repo.ingest_assertion(
            Path::new("incoming/relabeled.json"),
            accepted.clone(),
            &allow
        ),
        Err(KnowledgeError::AcceptedWithoutDecision)
    );
    // Canonical c0 is also independently enforced by the DB.
    accepted["criticality"] = json!("c0");
    accepted["review_decision_id"] = json!(id("rd", 1));
    constraint(
        db_insert(&mut admin, "public.assertion", &accepted),
        "chk_c0_basis",
    );
    assert!(
        matches!(repo.ingest_assertion(Path::new("incoming/c0.json"),accepted,&allow),Err(KnowledgeError::Database{constraint:Some(c),..}) if c=="chk_c0_basis")
    );
    assert_eq!(repo.list("assertions").len(), 2);

    // Price gates exist both on the public table and the raw-preservation table.
    for table in [
        "public.premium_observation",
        "knowledge.raw_premium_observation",
    ] {
        let mut p = if table.starts_with("public") {
            eligible.clone()
        } else {
            raw_price(3, &raw)
        };
        p["id"] = json!(id("premium", 3));
        p["review_status"] = json!("accepted");
        p["origin"] = json!("fixture");
        p["review_decision_id"] = json!(id("rd", 1));
        constraint(
            db_insert(&mut admin, table, &p),
            "chk_fixture_never_accepted",
        );
        p["origin"] = json!("pipeline");
        p.as_object_mut().unwrap().remove("review_decision_id");
        constraint(
            db_insert(&mut admin, table, &p),
            "chk_accepted_needs_decision",
        );
    }
    // DB and API assertion immutability: there is no public update API.
    let e = admin
        .execute(
            "UPDATE public.assertion SET predicate='changed' WHERE id=$1",
            &[&id("a", 1)],
        )
        .unwrap_err();
    constraint(e, "append_only");
    let mut first = assertion(4, &raw);
    first["supersedes"] = json!(id("a", 1));
    first["correction_reason"] = json!("source_changed");
    let mut second = first.clone();
    second["id"] = json!(id("a", 5));
    // A lone branch commits; its sibling without a conflict must roll back completely.
    repo.ingest_assertion(Path::new("incoming/first.json"), first.clone(), &allow)
        .unwrap();
    assert!(
        matches!(repo.ingest_assertion(Path::new("incoming/second.json"),second.clone(),&allow),Err(KnowledgeError::Database{constraint:Some(c),..}) if c=="chk_supersedes_linear")
    );
    assert!(repo.get("assertions", &id("a", 5)).is_none());
    repo.ingest_corrections(
        Path::new("incoming/corrections.json"),
        vec![second],
        json!({"id":id("conflict",1),
        "assertions":[id("a",4),id("a",5)],"state":"open", "reason":"fixture_only divergent corrections"}),
        &allow,
    )
    .unwrap();
    drop(repo);
    let mut repo = KnowledgeRepository::connect(&config, allow).unwrap();
    assert_eq!(repo.superseding(&id("a", 1)).len(), 2);
    assert_eq!(repo.conflicts_for(&id("a", 4)).len(), 1);
    assert_eq!(repo.conflicts_for(&id("a", 4))[0]["state"], "open");
    assert!(!repo
        .check_candidate(None)
        .unwrap()
        .iter()
        .any(|v| v.code == "K10"));
    repo.insert_record(
        "terms_lineages",
        json!({"id":id("tl",1),"org_id":"org:fixture-only","label":"fixture_only"}),
    )
    .unwrap();
    repo.insert_record(
        "terms_editions",
        json!({"id":id("ted",1),"label":"fixture_only",
        "parts":[{"role":"body","fingerprint":{"rule":"fp-1","sha256":"c".repeat(64)}}]}),
    )
    .unwrap();
    let mut realizes = assertion(7, &raw);
    realizes["subject"] = json!(segment);
    realizes["predicate"] = json!("realizes");
    realizes.as_object_mut().unwrap().remove("value");
    realizes["object"] = json!(id("ted", 1));
    realizes["criticality"] = json!("c0");
    realizes["review_status"] = json!("accepted");
    realizes["review_decision_id"] = json!(id("rd", 1));
    realizes["evidence"] = json!([{"ref":segment,"role":"observation"}]);
    repo.ingest_assertion(
        Path::new("incoming/realizes.json"),
        realizes,
        &ObservationAllowlist::new(["b".repeat(64)]),
    )
    .unwrap();
    let mut c0 = assertion(8, &raw);
    c0["criticality"] = json!("c0");
    c0["review_status"] = json!("accepted");
    c0["review_decision_id"] = json!(id("rd", 1));
    c0["evidence"] = json!([{"ref":clause,"role":"basis"}]);
    repo.ingest_assertion(
        Path::new("incoming/basis.json"),
        c0,
        &ObservationAllowlist::new(["b".repeat(64)]),
    )
    .unwrap();
    drop(repo);
    let mut repo =
        KnowledgeRepository::connect(&config, ObservationAllowlist::new(["b".repeat(64)])).unwrap();
    assert_eq!(repo.list("segments").len(), 1);
    assert_eq!(repo.list("clauses").len(), 1);
    assert_eq!(repo.list("terms_lineages").len(), 1);
    assert_eq!(repo.list("terms_editions").len(), 1);
    let violations = repo.check_candidate(None).unwrap();
    assert!(violations.is_empty(), "{violations:?}");
    // Candidate validation re-reads DB rows written externally after connection.
    let mut external = raw_price(6, &raw);
    external["evidence"] = json!([{"ref":"clause:missing","role":"observation"}]);
    let columns = external
        .as_object()
        .unwrap()
        .keys()
        .map(|s| format!("\"{s}\""))
        .collect::<Vec<_>>()
        .join(",");
    admin.execute(&format!("INSERT INTO knowledge.raw_premium_observation({columns}) SELECT {columns} FROM jsonb_populate_record(NULL::knowledge.raw_premium_observation,$1)"),&[&external]).unwrap();
    assert!(repo
        .check_candidate(None)
        .unwrap()
        .iter()
        .any(|v| v.code == "B4"));
    assert!(repo.promote_candidate("candidate:bad", None).is_err());
    assert!(!repo.is_promoted("candidate:bad"));
    let count: i64 = admin
        .query_one(
            "SELECT count(*) FROM knowledge.candidate WHERE id='candidate:bad'",
            &[],
        )
        .unwrap()
        .get(0);
    assert_eq!(count, 0);

    // Dual-reference relation: the target goes to the typed column, the literal only to
    // the extension, and the reconnect restores both so K4 sees the cycle.
    let allow = ObservationAllowlist::new(["b".repeat(64)]);
    let mut relation = assertion(9, &raw);
    relation["subject"] = json!("cat:fixture_a");
    relation["predicate"] = json!("scope_relation");
    relation["object"] = json!("cat:fixture_b");
    relation["value"] = json!("narrower");
    let mut reverse = relation.clone();
    reverse["id"] = json!(id("a", 10));
    reverse["subject"] = json!("cat:fixture_b");
    reverse["object"] = json!("cat:fixture_a");
    for a in [relation, reverse] {
        repo.ingest_assertion(Path::new("incoming/scope.json"), a, &allow)
            .unwrap();
    }
    let row = admin
        .query_one(
            "SELECT object, value, (SELECT payload->>'value' FROM knowledge.record_extension \
             WHERE section='assertions' AND id=$1) FROM public.assertion WHERE id=$1",
            &[&id("a", 9)],
        )
        .unwrap();
    assert_eq!(
        row.get::<_, Option<String>>(0).as_deref(),
        Some("cat:fixture_b")
    );
    assert!(row.get::<_, Option<Value>>(1).is_none());
    assert_eq!(row.get::<_, Option<String>>(2).as_deref(), Some("narrower"));
    drop(repo);
    let mut repo = KnowledgeRepository::connect(&config, allow.clone()).unwrap();
    let stored = repo.get("assertions", &id("a", 9)).unwrap();
    assert_eq!(stored["object"], "cat:fixture_b");
    assert_eq!(stored["value"], "narrower");
    assert!(repo
        .check_candidate(None)
        .unwrap()
        .iter()
        .any(|v| v.code == "K4"));

    // K7 reads the persisted node shape: class in `kind`, 감액 and its target in `attrs`.
    repo.insert_record(
        "nodes",
        json!({"id":"cond:fixture_reduction","kind":"Condition","label":"fixture_only",
        "attrs":{"kind":"감액","anchor":"계약일"},"origin":"pipeline","onto_version":"onto-0.2"}),
    )
    .unwrap();
    let mut reduction = assertion(11, &raw);
    reduction["predicate"] = json!("has_condition");
    reduction["object"] = json!("cond:fixture_reduction");
    reduction.as_object_mut().unwrap().remove("value");
    repo.ingest_assertion(Path::new("incoming/reduction.json"), reduction, &allow)
        .unwrap();
    drop(repo);
    let mut repo = KnowledgeRepository::connect(&config, allow).unwrap();
    assert_eq!(
        repo.get("nodes", "cond:fixture_reduction").unwrap()["kind"],
        "Condition"
    );
    assert!(repo
        .check_candidate(None)
        .unwrap()
        .iter()
        .any(|v| v.code == "K7"));

    // A raw asset outside the R2 listing: refused by the loader, and a row written past the
    // service is a B4 member that blocks promotion even with no assertion referencing it.
    let unlisted = json!({"id":format!("raw:sha256:{}","f".repeat(64)),"sha256":"f".repeat(64),
        "byte_length":1,"media_type":"application/pdf","storage_key":"fixture_only"});
    assert!(matches!(
        repo.insert_record("raw_assets", unlisted.clone()),
        Err(KnowledgeError::HashNotObserved(_))
    ));
    let columns = unlisted
        .as_object()
        .unwrap()
        .keys()
        .map(|s| format!("\"{s}\""))
        .collect::<Vec<_>>()
        .join(",");
    admin.execute(&format!("INSERT INTO public.raw_asset({columns}) SELECT {columns} FROM jsonb_populate_record(NULL::public.raw_asset,$1)"),&[&unlisted]).unwrap();
    assert!(repo
        .check_candidate(None)
        .unwrap()
        .iter()
        .any(|v| v.code == "B4" && v.message.contains(&"f".repeat(64))));
    assert!(repo
        .promote_candidate("candidate:unlisted-raw", None)
        .is_err());
    let count: i64 = admin
        .query_one(
            "SELECT count(*) FROM knowledge.candidate WHERE id='candidate:unlisted-raw'",
            &[],
        )
        .unwrap()
        .get(0);
    assert_eq!(count, 0);
    println!("PostgreSQL restart persistence; B2/B3/price DB rechecks; c0; append_only; deferred K10; external-row candidate rejection; scope_relation round trip; K7 node shape; unlisted raw asset: PASS");
}
