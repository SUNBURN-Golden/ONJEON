use super::*;
use std::cell::RefCell;
use std::path::Path;

struct FixtureOnly {
    robots: &'static str,
    content_type: &'static str,
    page: &'static str,
    requests: RefCell<Vec<String>>,
}

impl Fetch for FixtureOnly {
    fn fetch(&self, url: &str, _: usize) -> Result<FetchResponse, FetchError> {
        self.requests.borrow_mut().push(url.into());
        let robots = url.ends_with("/robots.txt");
        Ok(FetchResponse {
            status: 200,
            headers: vec![(
                "content-type".into(),
                if robots {
                    self.content_type
                } else {
                    "text/html"
                }
                .into(),
            )],
            body: if robots { self.robots } else { self.page }
                .as_bytes()
                .to_vec(),
            truncated: false,
        })
    }
}

fn registry() -> Denominator {
    load_denominator(&Path::new(env!("CARGO_MANIFEST_DIR")).join("../../data/registry")).unwrap()
}

fn run(plan: &ListPlan, fixture: &FixtureOnly) -> DiscoveryManifest {
    Enumerator {
        fetch: fixture,
        gate: &mut RobotsGate::new(3600),
        clock: &|| 1,
        page_cap_bytes: LIST_PAGE_MAX_BYTES,
        rate_policy: "fixture_only".into(),
    }
    .run(
        plan,
        &RunMeta {
            survey_round: "fixture_only".into(),
            source_id: "fixture_only".into(),
            adapter_version: "fixture_only".into(),
        },
    )
}

fn entry() -> DenomEntry {
    let mut entry = registry().in_scope.remove(0);
    entry.row.disclosure_status = Some(onjeon_contracts::AcquisitionStatus::Archived);
    entry.row.disclosure_access = onjeon_contracts::HostAccess::Reachable;
    entry.row.disclosure_url = "https://fixture.invalid/disclosure".into();
    entry
}

#[test]
fn adapters_navigation_and_js_shell_never_complete_product_enumeration() {
    let entry = entry();
    let plan = InsurerAdapter::for_entry(&entry).plans(&entry).remove(0);
    assert_eq!(plan.scope.axis, "disclosure_entry");
    for page in [
        "<a href='/home'>Home</a><a href='/privacy'>Privacy</a>",
        "<html><div id='app'></div><script src='app.js'></script></html>",
    ] {
        let fixture = FixtureOnly {
            robots: "User-agent: *\nAllow: /\n",
            content_type: "text/plain",
            page,
            requests: RefCell::default(),
        };
        let result = run(&plan, &fixture);
        assert!(!exploration_state_of(&result.termination).reached_evidence());
        assert!(result.discovered_ids.is_empty());
        assert!(!result.result.empty_success);
    }
}

#[test]
fn adapters_invalid_robots_holds_without_list_request() {
    let entry = entry();
    let plan = InsurerAdapter::for_entry(&entry).plans(&entry).remove(0);
    for (robots, content_type) in [
        ("<html><input type='password'></html>", "text/html"),
        ("<html>WAF challenge</html>", "text/plain"),
        ("Service temporarily unavailable", "text/plain"),
        ("", "text/html"),
    ] {
        let fixture = FixtureOnly {
            robots,
            content_type,
            page: "<html></html>",
            requests: RefCell::default(),
        };
        let result = run(&plan, &fixture);
        assert!(matches!(
            exploration_state_of(&result.termination),
            ExplorationState::Hold { .. }
        ));
        assert_eq!(fixture.requests.borrow().len(), 1);
        assert!(fixture.requests.borrow()[0].ends_with("/robots.txt"));
    }
}

#[test]
fn adapters_html_requires_positive_list_or_empty_evidence() {
    let parser = ListParser::HtmlLinks {
        link_substring: "product".into(),
        id_query_key: "id".into(),
        total_marker: Some("total=".into()),
    };
    for body in [
        "<html>Service temporarily unavailable</html>",
        "<html><div id='app'></div></html>",
        "<a href='/home'>Home</a>",
    ] {
        assert!(parse_page(&parser, body.as_bytes()).is_err());
    }
    assert!(parse_page(&parser, b"<html>total=0</html>")
        .unwrap()
        .item_ids
        .is_empty());
    assert_eq!(
        parse_page(&parser, b"<a href='/product?id=one'>One</a>")
            .unwrap()
            .item_ids,
        ["one"]
    );
}

#[test]
fn adapters_registry_progress_applies_gaps_and_discoveries_without_acquisition() {
    let denom = registry();
    let mut table = ProgressTable::for_denominator(denom.in_scope.iter());
    assert_eq!(table.rows.len(), denom.in_scope.len());
    for entry in &denom.in_scope {
        let row = table
            .rows
            .iter()
            .find(|r| r.institution_id == entry.row.insurer_id)
            .unwrap();
        // A fresh progress table records only what this round attempted: every
        // axis starts Unqueried and no denominator is marked unknown yet —
        // registry-carried statuses arrive through manifests, not pre-seeding.
        assert!(row.unknown_denominators.is_empty());
        assert!(row
            .exploration
            .values()
            .all(|s| *s == ExplorationState::Unqueried));
        assert!(table
            .coverage_of(&entry.row.insurer_id)
            .values()
            .all(|c| c.unknown_scopes == 0 && c.rate().is_none()));
    }
    let id = denom.in_scope[0].row.insurer_id.clone();
    let mut manifest = unenumerated_manifest(
        ScopeDesc {
            axis: "product_list".into(),
            institution_id: id.clone(),
            sale_status: None,
            channel: None,
            period_from: None,
            period_to: None,
            doc_roles: vec![],
        },
        "fixture_only",
        "",
        &RunMeta {
            survey_round: "fixture_only".into(),
            source_id: "fixture_only".into(),
            adapter_version: "fixture_only".into(),
        },
        "fixture_only missing parser",
        "1970-01-01T00:00:01Z",
    );
    table.apply_discovery(&manifest).unwrap();
    assert!(table.rows[0]
        .unknown_denominators
        .values()
        .all(|s| matches!(s, ExplorationState::Unexplored { .. })));
    manifest.termination = Termination::NextPointerAbsent {
        at_cursor: "".into(),
    };
    manifest.gaps.clear();
    manifest.discovered_ids = vec!["fixture_only_product".into()];
    table = ProgressTable::from_discoveries(&denom, &[manifest.clone()]).unwrap();
    table.apply_discovery(&manifest).unwrap();
    assert_eq!(table.row_mut(&id).unwrap().items.len(), 6);
    assert!(table.coverage_of(&id).values().all(|c| c.expected == 1
        && c.acquired == 0
        && c.rate() == Some(0.0)
        && c.unacquired.get("unqueried") == Some(&1)));
    manifest.scope.axis = "documents".into();
    manifest.scope.doc_roles = vec!["terms".into()];
    manifest.termination = Termination::RobotsBlocked {
        reason: "fixture_only_blocked".into(),
    };
    manifest.gaps = vec![GapRecord {
        kind: "blocked".into(),
        range: "whole_scope".into(),
        reason: "fixture_only_blocked".into(),
    }];
    table.apply_discovery(&manifest).unwrap();
    let row = table.row_mut(&id).unwrap();
    let terms = row
        .items
        .iter()
        .find(|i| i.doc_role == onjeon_contracts::DocRole::Terms)
        .unwrap();
    assert_eq!(terms.unacquired.as_ref().unwrap().1, "fixture_only_blocked");
    assert!(!terms.is_acquired());
    let all = table.coverage_all();
    assert!(all.values().all(|c| c.acquired == 0));
    // The blocked documents manifest covered only `terms` — its denominator is
    // marked unverifiable again, while roles outside the manifest scope keep the
    // verified denominator the product_list enumeration established.
    assert!(all[&onjeon_contracts::DocRole::Terms].rate().is_none());
    assert_eq!(
        all[&onjeon_contracts::DocRole::RiderTerms].rate(),
        Some(0.0)
    );
    manifest.scope.institution_id = "fixture_only_outside_denominator".into();
    assert!(table.apply_discovery(&manifest).is_err());
}
