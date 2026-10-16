use super::*;
use crate::checks::{comparison_request, evaluation_request, RequestCheck};
use onjeon_contracts::{AcquisitionStatus, ContractVersionMatch, DisplayStatus, SaleStatus};
use serde::de::DeserializeOwned;
use serde::Serialize;
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

fn schemas_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../schemas")
}

fn spec(surface: &str) -> serde_json::Value {
    let p = schemas_dir().join(format!("openapi/{surface}.v1.yaml"));
    serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap()
}

fn fixture(name: &str) -> serde_json::Value {
    let p = schemas_dir().join(format!("codegen/tests/api_fixtures/{name}.fixture.json"));
    serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap()
}

/// Fixture -> typed value -> JSON must give the fixture back (no field is dropped or invented).
fn round_trip<T: DeserializeOwned + Serialize>(name: &str) -> T {
    let doc = fixture(name);
    let typed: T = serde_json::from_value(doc.clone()).unwrap_or_else(|e| panic!("{name}: {e}"));
    assert_eq!(
        serde_json::to_value(&typed).unwrap(),
        doc,
        "{name} does not round-trip"
    );
    typed
}

fn spec_routes(surface: &str) -> BTreeSet<(String, String, String, bool)> {
    let doc = spec(surface);
    let mut out = BTreeSet::new();
    for (path, item) in doc["paths"].as_object().unwrap() {
        for (method, op) in item.as_object().unwrap() {
            out.insert((
                method.to_uppercase(),
                path.clone(),
                op["operationId"].as_str().unwrap().to_string(),
                op.get("x-onjeon-skeleton") == Some(&serde_json::Value::Bool(true)),
            ));
        }
    }
    out
}

fn table_routes(surface: Surface, skeleton: bool) -> BTreeSet<(String, String, String, bool)> {
    #[allow(unused_mut)]
    let mut ops: Vec<&Operation> = OPERATIONS.iter().collect();
    #[cfg(feature = "skeleton")]
    ops.extend(SKELETON_OPERATIONS.iter());
    ops.into_iter()
        .filter(|o| o.surface == surface && (skeleton || !o.skeleton))
        .map(|o| {
            (
                o.method.to_string(),
                o.path.to_string(),
                o.id.to_string(),
                o.skeleton,
            )
        })
        .collect()
}

#[test]
fn operation_table_matches_the_openapi_documents() {
    for (name, surface) in [
        ("public", Surface::Public),
        ("personal", Surface::Personal),
        ("console", Surface::Console),
    ] {
        let in_spec = spec_routes(name);
        let default_surface: BTreeSet<_> = in_spec.iter().filter(|r| !r.3).cloned().collect();
        assert_eq!(
            table_routes(surface, false),
            default_surface,
            "{name}: default surface differs from the document"
        );
        #[cfg(feature = "skeleton")]
        assert_eq!(
            table_routes(surface, true),
            in_spec,
            "{name}: with the skeleton feature the table is the whole document"
        );
        #[cfg(not(feature = "skeleton"))]
        assert_eq!(
            in_spec.iter().filter(|r| r.3).count(),
            if name == "personal" { 2 } else { 0 }
        );
    }
}

#[test]
fn operation_ids_and_routes_are_unique() {
    let ids: BTreeSet<_> = OPERATIONS.iter().map(|o| o.id).collect();
    assert_eq!(ids.len(), OPERATIONS.len());
    let routes: BTreeSet<_> = OPERATIONS.iter().map(|o| (o.method, o.path)).collect();
    assert_eq!(routes.len(), OPERATIONS.len());
}

#[test]
fn personal_and_console_are_never_publicly_cacheable() {
    for o in OPERATIONS {
        match o.surface {
            Surface::Public => {
                if o.method == "GET" {
                    assert_eq!(o.cache, CacheClass::PublicKeyed, "{}", o.id);
                    assert!(
                        o.cache_key.contains(&"release_id"),
                        "{}: cache key lacks release_id",
                        o.id
                    );
                } else {
                    assert_eq!(o.cache, CacheClass::NoStore, "{}", o.id);
                }
            }
            Surface::Personal | Surface::Console => {
                assert_eq!(o.cache, CacheClass::PrivateNoStore, "{}", o.id);
                assert!(o.cache_key.is_empty(), "{}", o.id);
            }
        }
    }
}

#[test]
fn the_spec_pins_private_no_store_on_every_personal_and_console_response() {
    for surface in ["personal", "console"] {
        let doc = spec(surface);
        assert_eq!(
            doc["components"]["headers"]["CacheControl"]["schema"]["enum"],
            serde_json::json!(["private, no-store"])
        );
        for (_, item) in doc["paths"].as_object().unwrap() {
            for (_, op) in item.as_object().unwrap() {
                for (code, resp) in op["responses"].as_object().unwrap() {
                    let resp = match resp.get("$ref") {
                        Some(r) => doc["components"]["responses"]
                            [r.as_str().unwrap().rsplit('/').next().unwrap()]
                        .clone(),
                        None => resp.clone(),
                    };
                    assert_eq!(
                        resp["headers"]["Cache-Control"]["$ref"],
                        "#/components/headers/CacheControl",
                        "{surface} {} {code}",
                        op["operationId"]
                    );
                }
            }
        }
    }
}

#[cfg(not(feature = "skeleton"))]
#[test]
fn skeleton_operations_are_not_exposed_by_default() {
    assert!(OPERATIONS.iter().all(|o| !o.skeleton && o.flag.is_none()));
    assert!(operation("create_consultation_request").is_none());
    assert!(operation("create_quote_request").is_none());
    assert!(OPERATIONS
        .iter()
        .all(|o| !o.path.contains("consultation") && !o.path.contains("quote")));
}

#[cfg(feature = "skeleton")]
#[test]
fn skeleton_operations_exist_only_behind_the_feature_and_every_flag_is_named() {
    assert_eq!(SKELETON_OPERATIONS.len(), 2);
    for o in SKELETON_OPERATIONS {
        assert!(o.skeleton && o.flag.is_some(), "{}", o.id);
        assert_eq!(o.surface, Surface::Personal);
        assert_eq!(o.cache, CacheClass::PrivateNoStore);
    }
    assert!(OPERATIONS.iter().all(|o| !o.skeleton));
    // the reserved types compile and carry release_id like every response
    let r = ConsultationRequestReceipt {
        release_id: "rel:20261001-1".into(),
        consultation_request_id: "x".into(),
    };
    assert_eq!(
        serde_json::to_value(r).unwrap()["release_id"],
        "rel:20261001-1"
    );
    let _ = QuoteRequestCreate {
        profile_id: "person:00000000000000000000000000".into(),
        idempotency_key: "k".into(),
    };
}

#[test]
fn every_response_body_type_has_a_required_release_id() {
    // Serialising a value built from a fixture shows release_id; removing it must fail to parse.
    for name in [
        "CurrentReleaseResponse",
        "ProductListResponse",
        "PolicyImportDetail",
        "EvaluationResponse",
        "DeletionJobResponse",
        "ReleaseListResponse",
    ] {
        let mut doc = fixture(name);
        assert!(doc.get("release_id").is_some(), "{name}");
        doc.as_object_mut().unwrap().remove("release_id");
        let parsed = match name {
            "CurrentReleaseResponse" => {
                serde_json::from_value::<CurrentReleaseResponse>(doc).is_err()
            }
            "ProductListResponse" => serde_json::from_value::<ProductListResponse>(doc).is_err(),
            "PolicyImportDetail" => serde_json::from_value::<PolicyImportDetail>(doc).is_err(),
            "EvaluationResponse" => serde_json::from_value::<EvaluationResponse>(doc).is_err(),
            "DeletionJobResponse" => serde_json::from_value::<DeletionJobResponse>(doc).is_err(),
            "ReleaseListResponse" => serde_json::from_value::<ReleaseListResponse>(doc).is_err(),
            _ => unreachable!(),
        };
        assert!(parsed, "{name}: a body without release_id must not parse");
    }
}

#[test]
fn fixtures_round_trip() {
    let r: CurrentReleaseResponse = round_trip("CurrentReleaseResponse");
    assert_eq!(r.release_id, "rel:20261001-1");
    let p: ProductListResponse = round_trip("ProductListResponse");
    assert_eq!(p.items.len(), 2);
    assert!(p.items[0].acquisition_status.is_none());
    assert_eq!(
        p.items[1].acquisition_status,
        Some(AcquisitionStatus::NotFound)
    );
    let d: PolicyImportDetail = round_trip("PolicyImportDetail");
    assert_eq!(
        d.contract_version_match,
        Some(ContractVersionMatch::Ambiguous)
    );
    let e: EvaluationResponse = round_trip("EvaluationResponse");
    assert_eq!(e.results[0].result.display_status, DisplayStatus::Hold);
    let _: DeletionJobResponse = round_trip("DeletionJobResponse");
    let _: PolicyUpdateRequest = round_trip("PolicyUpdateRequest");
    let q: ListProductsQuery = round_trip("ListProductsQuery");
    assert_eq!(q.sale_status, Some(SaleStatus::OnSale));
}

#[test]
fn console_release_id_is_null_before_the_first_release_but_the_key_is_required() {
    let l: ReleaseListResponse = round_trip("ReleaseListResponse");
    assert_eq!(l.release_id, None);
    let mut doc = fixture("ReleaseListResponse");
    doc.as_object_mut().unwrap().remove("release_id");
    assert!(serde_json::from_value::<ReleaseListResponse>(doc).is_err());
}

#[test]
fn unknown_enum_values_fail_instead_of_defaulting() {
    let mut q = fixture("ListProductsQuery");
    q["sale_status"] = "on_sale_maybe".into();
    assert!(serde_json::from_value::<ListProductsQuery>(q).is_err());
    let mut p = fixture("ProductListResponse");
    p["items"][0]["capabilities"][0]["state"] = "maybe".into();
    assert!(serde_json::from_value::<ProductListResponse>(p).is_err());
}

#[test]
fn a_required_any_value_must_be_present() {
    let ok = serde_json::json!({"name": "assumption_a", "value": null});
    assert!(serde_json::from_value::<AssumptionRequest>(ok).is_ok());
    let missing = serde_json::json!({"name": "assumption_a"});
    assert!(serde_json::from_value::<AssumptionRequest>(missing).is_err());
}

#[test]
fn money_in_requests_is_integer_won() {
    let ok = serde_json::json!({"budget_krw": 100000, "edits": [], "idempotency_key": "k"});
    let r: PlanCreateRequest = serde_json::from_value(ok).unwrap();
    assert_eq!(r.budget_krw, Some(100000));
    let float = serde_json::json!({"budget_krw": 10.5, "edits": [], "idempotency_key": "k"});
    assert!(serde_json::from_value::<PlanCreateRequest>(float).is_err());
}

#[test]
fn comparison_and_evaluation_targets_are_exactly_one() {
    let cov = "cov:ted:01BX5ZZKBKACTAV9WEVGEMMVRY/art7".to_string();
    let none = ComparisonRequest {
        cov_ids: None,
        concept_id: None,
        comparison_basis_id: None,
        scenario: None,
    };
    assert_eq!(comparison_request(&none), Err(RequestCheck::MissingTarget));
    let empty = ComparisonRequest {
        cov_ids: Some(vec![]),
        ..none.clone()
    };
    assert_eq!(comparison_request(&empty), Err(RequestCheck::MissingTarget));
    let one = ComparisonRequest {
        cov_ids: Some(vec![cov.clone()]),
        ..none.clone()
    };
    assert_eq!(comparison_request(&one), Ok(()));
    let both = ComparisonRequest {
        concept_id: Some("concept-1".into()),
        ..one.clone()
    };
    assert_eq!(
        comparison_request(&both),
        Err(RequestCheck::AmbiguousTarget)
    );

    let scenario = EvaluationScenario {
        facts: Default::default(),
        assumptions: None,
    };
    let ev = EvaluationRequest {
        contract_ids: None,
        cov_ids: None,
        scenario,
        confirmed_facts: None,
        idempotency_key: "k".into(),
    };
    assert_eq!(evaluation_request(&ev), Err(RequestCheck::MissingTarget));
    let ev1 = EvaluationRequest {
        cov_ids: Some(vec![cov.clone()]),
        ..ev.clone()
    };
    assert_eq!(evaluation_request(&ev1), Ok(()));
    let ev2 = EvaluationRequest {
        contract_ids: Some(vec!["contract:01H8XGJWBWBAQ4Z4RN3XPQ3BDY".into()]),
        ..ev1.clone()
    };
    assert_eq!(evaluation_request(&ev2), Err(RequestCheck::AmbiguousTarget));
}

#[test]
fn multipart_form_has_no_binary_field_and_keeps_the_password_out_of_other_types() {
    let form = PolicyImportForm {
        profile_id: "person:00000000000000000000000000".into(),
        idempotency_key: "k".into(),
        password: Some("x".into()),
    };
    let v = serde_json::to_value(form).unwrap();
    assert!(v.get("file").is_none());
    let imp = operation("create_policy_import").unwrap();
    assert!(imp.multipart && imp.request == Some("PolicyImportForm"));
}

#[test]
fn lookup_helpers() {
    assert_eq!(
        operations_of(Surface::Console).count(),
        OPERATIONS
            .iter()
            .filter(|o| o.surface == Surface::Console)
            .count()
    );
    assert_eq!(
        operation("get_current_release").unwrap().path,
        "/v1/releases/current"
    );
    assert!(operation("no_such_operation").is_none());
    assert_eq!(
        API_VERSION,
        spec("public")["info"]["version"].as_str().unwrap()
    );
}

#[test]
fn generated_files_are_up_to_date() {
    let status = std::process::Command::new("python3")
        .arg("-I")
        .arg(schemas_dir().join("codegen/gen.py"))
        .arg("--check")
        .status()
        .expect("python3 is required to check generated files");
    assert!(
        status.success(),
        "generated files are stale: run `bash packages/schemas/codegen/gen.sh`"
    );
}

#[test]
fn python_openapi_suite_passes() {
    let status = std::process::Command::new("python3")
        .args([
            "-I",
            "-m",
            "unittest",
            "discover",
            "-p",
            "test_openapi.py",
            "-s",
        ])
        .arg(schemas_dir().join("codegen/tests"))
        .status()
        .expect("python3 is required to run the OpenAPI suite");
    assert!(
        status.success(),
        "packages/schemas/codegen/tests/test_openapi.py failed"
    );
}
