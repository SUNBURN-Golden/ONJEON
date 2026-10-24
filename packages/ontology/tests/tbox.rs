//! T-box (onto-0.2) loading and the boundary of the crate (no database, no network).

mod common;
use onjeon_ontology::*;
use std::path::PathBuf;

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn tbox_text() -> String {
    std::fs::read_to_string(root().join("../schemas/ontology/tbox.json")).unwrap()
}

#[test]
fn loads_the_schemas_copy() {
    let t = load_tbox(&tbox_text()).unwrap();
    assert!(t.version.starts_with("onto-0.2"));
    assert_eq!(t.constraints.len(), 16);
    assert_eq!(t.class("TermsEdition").unwrap().zone, "knowledge");
    assert_eq!(t.relation("realizes").unwrap().domain, "DocumentSegment");
    assert!(t.constraint("K16").unwrap().rule.contains("근거 묶음"));
}

#[test]
fn schemas_copy_is_identical_to_the_design_proposal_when_it_is_present() {
    // the copy is verbatim; the proposal may be moved later, then there is nothing to compare against
    let proposal = root().join("../../docs/blueprint/proposals/온톨로지/tbox.json");
    if proposal.exists() {
        assert_eq!(std::fs::read(proposal).unwrap(), tbox_text().into_bytes());
    }
}

#[test]
fn rejects_other_versions_and_incomplete_constraint_lists() {
    let mut v: serde_json::Value = serde_json::from_str(&tbox_text()).unwrap();
    v["version"] = serde_json::json!("onto-0.1");
    assert!(load_tbox(&v.to_string()).is_err());
    let mut v: serde_json::Value = serde_json::from_str(&tbox_text()).unwrap();
    v["constraints"].as_array_mut().unwrap().pop();
    assert!(load_tbox(&v.to_string()).is_err());
    let mut v: serde_json::Value = serde_json::from_str(&tbox_text()).unwrap();
    let dup = v["classes"][0].clone();
    v["classes"].as_array_mut().unwrap().push(dup);
    assert!(load_tbox(&v.to_string()).is_err());
    assert!(load_tbox("{").is_err());
}

#[test]
fn every_constraint_the_checker_reports_is_defined_in_the_tbox() {
    let t = load_tbox(&tbox_text()).unwrap();
    let a = common::abox();
    let mut seen = std::collections::BTreeSet::new();
    for rel in ["rel:case-r24", "rel:case-r25", common::CURRENT] {
        for v in common::check(&common::release_view(&a, rel)) {
            seen.insert(v.code);
        }
    }
    for code in seen {
        assert!(t.constraint(&code).is_some(), "{code}");
    }
}

#[test]
fn no_database_or_network_dependency() {
    let manifest = std::fs::read_to_string(root().join("Cargo.toml")).unwrap();
    for banned in [
        "sqlx", "postgres", "rusqlite", "diesel", "reqwest", "hyper", "tokio", "ureq", "curl",
        "surf", "isahc",
    ] {
        assert!(!manifest.contains(banned), "{banned}");
    }
    for entry in std::fs::read_dir(root().join("src")).unwrap() {
        let text = std::fs::read_to_string(entry.unwrap().path()).unwrap();
        for banned in ["std::net", "TcpStream", "http://", "https://"] {
            assert!(!text.contains(banned), "{banned}");
        }
    }
}
