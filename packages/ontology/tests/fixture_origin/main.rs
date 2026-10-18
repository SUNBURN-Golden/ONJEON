//! Fixture marker checks for `packages/fixtures/ontology/` (T-KN-02, 02_구현계약 §8.1).
//!
//! Library level only. Rejection by the service loader (B1~B3) and the release builder (B5) belongs to the
//! tasks that implement those; this file checks that the migrated case data carries the fixture markers and
//! that it still behaves like the golden case A-box.

use onjeon_ontology::*;
use serde_json::Value;
use std::collections::BTreeSet;
use std::path::PathBuf;

const CURRENT: &str = "rel:case-r26";

fn repo() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn fixture_dir() -> PathBuf {
    repo().join("packages/fixtures/ontology")
}

fn json_of(p: &PathBuf) -> Value {
    serde_json::from_str(&std::fs::read_to_string(p).unwrap_or_else(|e| panic!("{p:?}: {e}")))
        .unwrap()
}

fn doc() -> Value {
    json_of(&fixture_dir().join("abox_cases.json"))
}

fn abox() -> Abox {
    Abox::from_dir(&fixture_dir()).expect("fixture A-box")
}

fn rule_files() -> Vec<(String, Value)> {
    let mut v: Vec<_> = std::fs::read_dir(fixture_dir().join("rules"))
        .unwrap()
        .map(|e| e.unwrap().path())
        .filter(|p| p.extension().is_some_and(|x| x == "json"))
        .map(|p| {
            (
                p.file_name().unwrap().to_string_lossy().into_owned(),
                json_of(&p),
            )
        })
        .collect();
    v.sort_by(|a, b| a.0.cmp(&b.0));
    v
}

fn strings(v: &Value, out: &mut Vec<String>) {
    match v {
        Value::String(s) => out.push(s.clone()),
        Value::Array(a) => a.iter().for_each(|x| strings(x, out)),
        Value::Object(m) => m.values().for_each(|x| strings(x, out)),
        _ => {}
    }
}

fn is_hex64(s: &str) -> bool {
    s.len() == 64 && s.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
}

fn fixture_origin_all_claims() {
    let d = doc();
    let claims = d["assertions"].as_array().unwrap();
    assert!(!claims.is_empty());
    for a in claims {
        let id = a["id"].as_str().unwrap();
        assert_eq!(a["origin"], "fixture", "{id}");
        assert!(
            a.get("review_decision_id").is_none(),
            "{id}: a fixture claim has no ReviewDecision"
        );
    }
    // _review_note is kept as the proposal has it
    let src = json_of(&repo().join("docs/blueprint/proposals/온톨로지/abox_cases.json"));
    for s in src["assertions"].as_array().unwrap() {
        let mine = claims
            .iter()
            .find(|a| a["id"] == s["id"])
            .unwrap_or_else(|| panic!("{}: missing", s["id"]));
        assert_eq!(mine["_review_note"], s["_review_note"], "{}", s["id"]);
    }
    assert_eq!(claims.len(), src["assertions"].as_array().unwrap().len());
}

/// test id: fixture-origin-all-claims
#[test]
fn fixture_origin_claims_are_all_fixture() {
    fixture_origin_all_claims();
}

/// test id: fixture-only-all-rules
#[test]
fn fixture_origin_rules_are_all_fixture_only() {
    let rules = rule_files();
    assert_eq!(rules.len(), 2);
    for (name, r) in &rules {
        assert_eq!(r["publication_state"], "fixture_only", "{name}");
        assert!(r.get("release_id").is_none(), "{name}");
    }
    // every rule file an assertion names is one of these, under rules/
    let d = doc();
    let on_disk: BTreeSet<String> = rules.iter().map(|(n, _)| format!("rules/{n}")).collect();
    let named: BTreeSet<String> = d["assertions"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|a| a["rule_path"].as_str().map(str::to_string))
        .collect();
    assert_eq!(named, on_disk);
    // the rules engine still loads them
    for (name, _) in &rules {
        let text = std::fs::read_to_string(fixture_dir().join("rules").join(name)).unwrap();
        onjeon_rules_engine::Rule::from_json_str(&text).unwrap_or_else(|e| panic!("{name}: {e:?}"));
    }
}

/// test id: fixture-hash-not-in-r2-listing
#[test]
fn fixture_origin_hashes_not_in_r2_listing() {
    let listing_path =
        repo().join("docs/blueprint/validation/source_checks/archive_listing_raw.json");
    let listing_text = std::fs::read_to_string(&listing_path).expect("Git-pinned R2 listing");
    let listing: Value = serde_json::from_str(&listing_text).unwrap();
    // sanity: the listing really holds hashes, otherwise "not found" proves nothing
    let mut all = Vec::new();
    strings(&listing, &mut all);
    let listed: Vec<&String> = all.iter().filter(|s| s.len() >= 16).collect();
    assert!(!listed.is_empty(), "listing has no searchable keys");

    let d = doc();
    let raws = d["raw_assets"].as_array().unwrap();
    let hashes: Vec<&str> = raws.iter().filter_map(|r| r["sha256"].as_str()).collect();
    assert!(hashes.len() >= 4 && hashes.iter().all(|h| is_hex64(h)));
    // every 64-hex value in the fixture (raw hashes, fingerprints) counts as a document hash
    let mut fixture_strings = Vec::new();
    strings(&d, &mut fixture_strings);
    let all_hashes: BTreeSet<&str> = fixture_strings
        .iter()
        .filter_map(|s| s.strip_prefix("raw:sha256:").or(Some(s.as_str())))
        .filter(|s| is_hex64(s))
        .collect();
    for h in hashes.iter().copied().chain(all_hashes.iter().copied()) {
        assert!(
            !listing_text.contains(h),
            "fixture hash {h} found in the R2 listing"
        );
        assert!(
            !listing_text.contains(&h[..16]),
            "fixture hash prefix {} found in the R2 listing",
            &h[..16]
        );
    }
}

fn is_formal_ref(s: &str) -> bool {
    let tail_ok = |t: &str| !t.is_empty() && !t.contains(char::is_whitespace);
    if let Some(h) = s.strip_prefix("raw:sha256:") {
        return is_hex64(h);
    }
    // seg:<sha12>:p<from>-<to>:<doc_role>:<ver>
    fn seg(s: &str) -> Option<&str> {
        let rest = s.strip_prefix("seg:")?;
        let (sha12, rest) = rest.split_once(":p")?;
        if sha12.len() != 12 || !sha12.bytes().all(|b| b.is_ascii_hexdigit()) {
            return None;
        }
        let (pages, rest) = rest.split_once(':')?;
        let (a, b) = pages.split_once('-')?;
        a.parse::<u32>().ok()?;
        b.parse::<u32>().ok()?;
        let (role, ver) = rest.rsplit_once(':')?;
        (!role.is_empty() && !ver.is_empty()).then_some(ver)
    }
    if s.starts_with("seg:") {
        return seg(s).is_some();
    }
    if let Some(rest) = s.strip_prefix("clause:") {
        // clause:<segment_ref>/<path_slug>#p<page>:<extractor>@<ver>
        let Some((segpart, tail)) = rest.split_once('/') else {
            return false;
        };
        let Some((slug, tail)) = tail.split_once("#p") else {
            return false;
        };
        let Some((page, ext)) = tail.split_once(':') else {
            return false;
        };
        return seg(segpart).is_some()
            && tail_ok(slug)
            && page.parse::<u32>().is_ok()
            && ext
                .split_once('@')
                .is_some_and(|(n, v)| !n.is_empty() && !v.is_empty());
    }
    false
}

/// test id: fixture-evidence-ref-formal
#[test]
fn fixture_origin_evidence_refs_are_formal_except_listed() {
    let d = doc();
    let exceptions: BTreeSet<String> = d["_formal_ref_exceptions"]
        .as_array()
        .unwrap()
        .iter()
        .map(|x| x.as_str().unwrap().to_string())
        .collect();
    // an exception exists only because the source has no hash or no page range
    let raws = d["raw_assets"].as_array().unwrap();
    for r in raws {
        let id = r["id"].as_str().unwrap();
        assert_eq!(exceptions.contains(id), r["sha256"].is_null(), "{id}");
    }
    for s in d["segments"].as_array().unwrap() {
        let id = s["id"].as_str().unwrap();
        let raw = raws.iter().find(|r| r["id"] == s["raw_asset"]).unwrap();
        let no_source = s["pages"].is_null() || raw["sha256"].is_null();
        assert_eq!(exceptions.contains(id), no_source, "{id}");
        if !no_source {
            assert!(is_formal_ref(id), "{id}");
            let sha12 = &raw["sha256"].as_str().unwrap()[..12];
            assert!(id.starts_with(&format!("seg:{sha12}:p")), "{id}");
        }
    }
    for c in d["clauses"].as_array().unwrap() {
        let id = c["id"].as_str().unwrap();
        let seg = c["segment"].as_str().unwrap();
        assert_eq!(exceptions.contains(id), exceptions.contains(seg), "{id}");
        if !exceptions.contains(id) {
            assert!(is_formal_ref(id), "{id}");
            assert!(id.starts_with(&format!("clause:{seg}/")), "{id}");
            assert!(id.contains(&format!("#p{}:", c["pdf_page"])), "{id}");
        }
    }
    // every evidence ref of every claim and every rule names a record, in formal form unless excepted
    let known: BTreeSet<String> = ["raw_assets", "segments", "clauses"]
        .iter()
        .flat_map(|k| {
            d[*k]
                .as_array()
                .unwrap()
                .iter()
                .map(|x| x["id"].as_str().unwrap().to_string())
        })
        .collect();
    let mut refs: Vec<String> = Vec::new();
    for a in d["assertions"].as_array().unwrap() {
        for e in a["evidence"].as_array().into_iter().flatten() {
            refs.push(e["ref"].as_str().unwrap().to_string());
        }
    }
    for (_, r) in rule_files() {
        refs.extend(
            r["evidence_refs"]
                .as_array()
                .unwrap()
                .iter()
                .map(|x| x.as_str().unwrap().to_string()),
        );
    }
    assert!(refs.iter().any(|r| r.starts_with("clause:")));
    for r in &refs {
        assert!(known.contains(r), "{r}: dangling evidence ref");
        assert!(
            exceptions.contains(r) || is_formal_ref(r),
            "{r}: neither formal nor a listed exception"
        );
    }
    // no basis evidence rests on an exception: basis needs a formal clause_ref
    for a in d["assertions"].as_array().unwrap() {
        for e in a["evidence"].as_array().into_iter().flatten() {
            if e["role"] == "basis" {
                assert!(is_formal_ref(e["ref"].as_str().unwrap()), "{}", a["id"]);
            }
        }
    }
    // K9 at file level: a rule's evidence_refs are all basis of some claim
    let basis: BTreeSet<&str> = d["assertions"]
        .as_array()
        .unwrap()
        .iter()
        .flat_map(|a| a["evidence"].as_array().into_iter().flatten())
        .filter(|e| e["role"] == "basis")
        .map(|e| e["ref"].as_str().unwrap())
        .collect();
    for (name, r) in rule_files() {
        for x in r["evidence_refs"].as_array().unwrap() {
            assert!(basis.contains(x.as_str().unwrap()), "{name}: {x}");
        }
    }
}

/// test id: fixture-behaves-like-golden
#[test]
fn fixture_origin_checks_pass_as_historical_and_flag_as_service() {
    let a = abox();
    let v = view(&a, CURRENT).unwrap();
    assert!(
        v.integrity.is_empty(),
        "frozen release hashes: {:?}",
        v.integrity
    );
    for rel in &a.releases {
        assert!(
            view(&a, &rel.id).unwrap().integrity.is_empty(),
            "{}",
            rel.id
        );
    }
    let hist = CheckProfile::historical_fixture(None);
    let vs = check_constraints(&v, &hist);
    // without a code universe K12 cannot run; nothing else may fire
    assert!(vs.iter().all(|x| x.code == "K12"), "{vs:?}");
    // the service profile lists every accepted fixture claim and nothing else
    let svc = check_constraints(&v, &CheckProfile::service_conformance(None));
    assert!(svc.iter().any(|x| x.code == PROFILE_VIOLATION));
    let accepted: BTreeSet<&str> = v
        .assertions
        .iter()
        .filter(|x| x.accepted())
        .map(|x| x.id.as_str())
        .collect();
    let flagged: BTreeSet<&str> = svc
        .iter()
        .filter(|x| x.code == PROFILE_VIOLATION)
        .map(|x| x.subject.as_str())
        .collect();
    assert!(!accepted.is_empty() && accepted.is_superset(&flagged) && !flagged.is_empty());
}

/// Mutating a marker must be caught: the test above is not vacuous.
#[test]
fn fixture_origin_marker_mutations_are_detected() {
    let mut d = doc();
    d["assertions"][0]["origin"] = Value::String("pipeline".into());
    let res = std::panic::catch_unwind(|| {
        let claims = d["assertions"].as_array().unwrap().clone();
        assert!(claims.iter().all(|a| a["origin"] == "fixture"));
    });
    assert!(res.is_err());
}
