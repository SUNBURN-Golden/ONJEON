//! All payloads and transports in this module are synthetic `fixture_only` inputs.
use super::*;
use onjeon_contracts::{AcquisitionStatus, DocRole};
use std::cell::RefCell;
use std::path::Path;

struct FixtureOnly {
    robots: &'static str,
    content_type: &'static str,
    page: String,
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
            body: if robots {
                self.robots
            } else {
                self.page.as_str()
            }
            .as_bytes()
            .to_vec(),
            truncated: false,
        })
    }
}

fn fixture_only(page: &str) -> FixtureOnly {
    FixtureOnly {
        robots: "User-agent: *\nAllow: /\n",
        content_type: "text/plain",
        page: page.into(),
        requests: RefCell::default(),
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

fn lifeplanet_entry() -> DenomEntry {
    registry()
        .in_scope
        .into_iter()
        .find(|e| e.row.insurer_id == "life-kyobo-lifeplanet")
        .unwrap()
}

fn complete() -> Termination {
    Termination::NextPointerAbsent {
        at_cursor: "fixture_only_last".into(),
    }
}

fn fixture_only_manifest(
    id: &str,
    axis: &str,
    roles: &[DocRole],
    ids: &[&str],
) -> DiscoveryManifest {
    let mut manifest = unenumerated_manifest(
        ScopeDesc {
            axis: axis.into(),
            institution_id: id.into(),
            sale_status: None,
            channel: None,
            period_from: None,
            period_to: None,
            doc_roles: roles.iter().map(|r| r.as_str().into()).collect(),
        },
        "fixture_only",
        "",
        &RunMeta {
            survey_round: "fixture_only".into(),
            source_id: "fixture_only".into(),
            adapter_version: "fixture_only".into(),
        },
        "fixture_only",
        "1970-01-01T00:00:01Z",
    );
    manifest.termination = complete();
    manifest.gaps.clear();
    manifest.discovered_ids = ids.iter().map(|s| (*s).into()).collect();
    manifest
}

fn complete_inventory(id: &str) -> Vec<DiscoveryManifest> {
    let mut manifests = vec![fixture_only_manifest(
        id,
        "product_list",
        &[],
        &["fixture_only_product"],
    )];
    for role in DENOMINATOR_DOC_ROLES {
        manifests.push(fixture_only_manifest(
            id,
            "documents",
            &[role],
            &["fixture_only_document"],
        ));
    }
    manifests
}

#[test]
fn adapters_navigation_maintenance_and_js_shell_never_complete_any_html_plan() {
    let entry = lifeplanet_entry();
    let mut plans = klia().plans(&entry);
    plans.extend(knia().plans(&entry));
    plans.extend(InsurerAdapter::for_entry(&entry).plans(&entry));
    for plan in plans {
        for page in [
            "<a href='/home'>Home</a><a href='/privacy'>Privacy</a>",
            "<html>Service temporarily unavailable</html>",
            "<html><div id='app'></div><script src='app.js'></script></html>",
        ] {
            let result = run(&plan, &fixture_only(page));
            assert!(matches!(
                result.termination,
                Termination::ParseFailed { .. }
            ));
            assert!(!exploration_state_of(&result.termination).reached_evidence());
            assert!(result.discovered_ids.is_empty());
            assert!(!result.result.empty_success);
            assert!(!result.gaps.is_empty());
        }
    }
}

#[test]
fn adapters_invalid_robots_holds_without_list_request() {
    let entry = lifeplanet_entry();
    let plan = InsurerAdapter::for_entry(&entry).plans(&entry).remove(0);
    for (robots, content_type) in [
        ("<html><input type='password'></html>", "text/html"),
        ("<html>WAF challenge</html>", "text/plain"),
        ("Service temporarily unavailable", "text/plain"),
        ("", "text/html"),
    ] {
        let mut fixture = fixture_only("<html></html>");
        fixture.robots = robots;
        fixture.content_type = content_type;
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
fn adapters_html_requires_positive_list_or_empty_evidence_with_or_without_total() {
    for total_marker in [None, Some("total=".into())] {
        let parser = ListParser::HtmlLinks {
            link_substring: "product".into(),
            id_query_key: "id".into(),
            total_marker,
            empty_marker: None,
        };
        for body in [
            "<html>Service temporarily unavailable</html>",
            "<html><div id='app'></div></html>",
            "<a href='/home'>Home</a>",
        ] {
            assert!(parse_page(&parser, body.as_bytes()).is_err());
        }
        assert_eq!(
            parse_page(&parser, b"<a href='/product?id=one'>One</a>")
                .unwrap()
                .item_ids,
            ["one"]
        );
    }
    let parser = ListParser::HtmlLinks {
        link_substring: "product".into(),
        id_query_key: "id".into(),
        total_marker: Some("total=".into()),
        empty_marker: None,
    };
    assert!(parse_page(&parser, b"<html>total=0</html>")
        .unwrap()
        .item_ids
        .is_empty());
    assert!(parse_page(&parser, b"<html>total=unknown; status=0</html>").is_err());
}

#[test]
fn adapters_unqueried_institutions_remain_unknown_in_aggregate() {
    let denom = registry();
    let mut table = ProgressTable::for_denominator(denom.in_scope.iter());
    assert_eq!(table.rows.len(), denom.in_scope.len());
    assert!(table.rows.iter().all(
        |r| r.unknown_denominators.len() == DENOMINATOR_DOC_ROLES.len()
            && r.exploration
                .values()
                .all(|s| *s == ExplorationState::Unqueried)
    ));
    assert!(table
        .coverage_all()
        .values()
        .all(|c| c.unknown_scopes == denom.in_scope.len() && c.rate().is_none()));
    let id = &denom.in_scope[0].row.insurer_id;
    for m in complete_inventory(id) {
        table.apply_discovery(&m).unwrap();
    }
    assert!(table
        .coverage_of(id)
        .values()
        .all(|c| c.expected == 1 && c.acquired == 0 && c.rate() == Some(0.0)));
    assert!(table.coverage_all().values().all(|c| c.expected == 1
        && c.unknown_scopes == denom.in_scope.len() - 1
        && c.rate().is_none()));
    // Only completion of every institution's required axes permits numeric rates.
    for entry in &denom.in_scope[1..] {
        for m in complete_inventory(&entry.row.insurer_id) {
            table.apply_discovery(&m).unwrap();
        }
    }
    assert!(table
        .coverage_all()
        .values()
        .all(|c| c.unknown_scopes == 0 && c.rate() == Some(0.0)));
}

#[test]
fn adapters_scoped_success_does_not_clear_unqueried_whole_inventory() {
    let denom = registry();
    let id = &denom.in_scope[0].row.insurer_id;
    let mut table = ProgressTable::for_denominator(denom.in_scope.iter());
    for mut m in complete_inventory(id) {
        m.scope.sale_status = Some("fixture_only_selling".into());
        m.scope.channel = Some("fixture_only_online".into());
        table.apply_discovery(&m).unwrap();
    }
    assert!(table
        .coverage_of(id)
        .values()
        .all(|c| c.unknown_scopes == 1 && c.rate().is_none()));
}

#[test]
fn adapters_multiple_document_identities_and_reasons_survive_either_discovery_order() {
    let denom = registry();
    let id = &denom.in_scope[0].row.insurer_id;
    let products = fixture_only_manifest(id, "product_list", &[], &["fixture_only_product"]);
    let documents = fixture_only_manifest(
        id,
        "documents",
        &[DocRole::RiderTerms],
        &[
            "fixture_only_rider_a",
            "fixture_only_rider_b",
            "fixture_only_rider_a",
        ],
    );
    for manifests in [
        [products.clone(), documents.clone()],
        [documents.clone(), products.clone()],
    ] {
        let mut table = ProgressTable::from_discoveries(&denom, &manifests).unwrap();
        let row = table.row_mut(id).unwrap();
        assert_eq!(row.discovered_products.len(), 1);
        assert_eq!(row.items.len(), 2);
        assert!(row
            .items
            .iter()
            .all(|i| i.doc_role == DocRole::RiderTerms && !i.is_acquired()));
        row.items[0].unacquired = Some((
            AcquisitionStatus::Blocked,
            "fixture_only_download_denied".into(),
        ));
        row.items[1].evidence = AcquisitionEvidence {
            raw_stored: true,
            segment_extracted: true,
            edition_link_accepted: true,
        };
        table.apply_discovery(&documents).unwrap();
        let row = table.row_mut(id).unwrap();
        assert_eq!(row.items.len(), 2);
        assert_eq!(
            row.items[0].unacquired.as_ref().unwrap().1,
            "fixture_only_download_denied"
        );
        let cov = &table.coverage_of(id)[&DocRole::RiderTerms];
        assert_eq!((cov.expected, cov.acquired), (2, 1));
        assert_eq!(cov.unacquired.get("blocked"), Some(&1));
        assert_eq!(cov.rate(), Some(0.5));
        // Scope failure must not overwrite acquisition reasons for prior documents.
        let mut other = documents.clone();
        other.scope.channel = Some("fixture_only_other".into());
        other.discovered_ids.clear();
        other.termination = Termination::RobotsBlocked {
            reason: "fixture_only_robots".into(),
        };
        table.apply_discovery(&other).unwrap();
        let row = table.row_mut(id).unwrap();
        assert_eq!(
            row.items[0].unacquired.as_ref().unwrap().1,
            "fixture_only_download_denied"
        );
        assert!(row.items[1].is_acquired());
        assert_eq!(table.coverage_of(id)[&DocRole::RiderTerms].rate(), None);
    }
}

#[test]
fn adapters_document_ids_require_one_known_role_before_mutation() {
    let denom = registry();
    let id = &denom.in_scope[0].row.insurer_id;
    let mut table = ProgressTable::for_denominator(denom.in_scope.iter());
    for roles in [
        vec![],
        vec![DocRole::Terms, DocRole::RiderTerms],
        vec![DocRole::DisclosureList],
    ] {
        let m = fixture_only_manifest(id, "documents", &roles, &["fixture_only_document"]);
        assert!(table.apply_discovery(&m).is_err());
        assert!(table.row_mut(id).unwrap().items.is_empty());
        assert!(table
            .row_mut(id)
            .unwrap()
            .exploration
            .values()
            .all(|s| *s == ExplorationState::Unqueried));
    }
    // Even an empty failure must not silently discard its scope because its role
    // is unknown. Reject it before changing the progress table.
    for roles in [vec![], vec![DocRole::DisclosureList]] {
        let mut m = fixture_only_manifest(id, "documents", &roles, &[]);
        m.termination = Termination::RobotsHold {
            reason: "fixture_only_role_unknown".into(),
        };
        assert!(table.apply_discovery(&m).is_err());
        assert!(table
            .row_mut(id)
            .unwrap()
            .exploration
            .values()
            .all(|s| *s == ExplorationState::Unqueried));
    }
}

#[test]
fn adapters_document_discovery_retains_actual_ids_without_products_or_acquisition() {
    let denom = registry();
    let id = &denom.in_scope[0].row.insurer_id;
    for (termination, status, reason) in [
        (
            Termination::RobotsBlocked {
                reason: "fixture_only_blocked".into(),
            },
            "blocked",
            "fixture_only_blocked",
        ),
        (
            Termination::ParseFailed {
                at_cursor: "fixture_only".into(),
                detail: "fixture_only_parse".into(),
            },
            "failed",
            "fixture_only_parse",
        ),
    ] {
        let mut m = fixture_only_manifest(
            id,
            "documents",
            &[DocRole::Terms],
            &["fixture_only_document"],
        );
        m.termination = termination;
        m.gaps = vec![GapRecord {
            kind: status.into(),
            range: "fixture_only_tail".into(),
            reason: reason.into(),
        }];
        let mut table = ProgressTable::from_discoveries(&denom, &[m]).unwrap();
        let row = table.row_mut(id).unwrap();
        assert!(row.discovered_products.is_empty());
        assert_eq!(row.items.len(), 1);
        assert_eq!(row.items[0].item_id, "fixture_only_document");
        assert_eq!(row.items[0].unacquired.as_ref().unwrap().1, reason);
        let cov = &table.coverage_of(id)[&DocRole::Terms];
        assert_eq!((cov.expected, cov.acquired), (1, 0));
        assert_eq!(cov.unacquired.get(status), Some(&1));
        assert!(cov.rate().is_none());
    }
}

#[test]
fn adapters_partial_walks_preserve_unknown_axis_scope_and_roles() {
    let denom = registry();
    let id = &denom.in_scope[0].row.insurer_id;
    for axis in ["product_list", "documents"] {
        for termination in [
            Termination::PageRepeat {
                at_cursor: "fixture_only_repeat".into(),
            },
            Termination::Stall {
                at_cursor: "fixture_only_stall".into(),
                unique_items: 1,
                advertised_total: 2,
            },
            Termination::MaxPagesReached {
                at_cursor: "fixture_only_cap".into(),
            },
        ] {
            let roles = if axis == "documents" {
                vec![DocRole::Terms, DocRole::RiderTerms]
            } else {
                vec![]
            };
            let mut partial = fixture_only_manifest(id, axis, &roles, &[]);
            partial.termination = termination;
            for partial_first in [true, false] {
                let mut manifests = complete_inventory(id);
                if partial_first {
                    manifests.insert(0, partial.clone());
                } else {
                    manifests.push(partial.clone());
                }
                // Use a separate channel so an unscoped success cannot erase its gap.
                let at = if partial_first {
                    0
                } else {
                    manifests.len() - 1
                };
                manifests[at].scope.channel = Some("fixture_only_channel".into());
                let partial = manifests[at].clone();
                let mut table = ProgressTable::from_discoveries(&denom, &manifests).unwrap();
                assert!(table.coverage_of(id)[&DocRole::Terms].rate().is_none());
                for scope in [
                    ScopeDesc {
                        channel: Some("fixture_only_other".into()),
                        ..partial.scope.clone()
                    },
                    ScopeDesc {
                        sale_status: Some("fixture_only_sale".into()),
                        ..partial.scope.clone()
                    },
                    ScopeDesc {
                        period_from: Some("2000-01-01".into()),
                        ..partial.scope.clone()
                    },
                    ScopeDesc {
                        period_to: Some("2001-01-01".into()),
                        ..partial.scope.clone()
                    },
                    ScopeDesc {
                        axis: if axis == "documents" {
                            "product_list"
                        } else {
                            "documents"
                        }
                        .into(),
                        doc_roles: if axis == "product_list" {
                            vec!["terms".into(), "rider_terms".into()]
                        } else {
                            partial.scope.doc_roles.clone()
                        },
                        ..partial.scope.clone()
                    },
                ] {
                    let mut other = partial.clone();
                    other.scope = scope;
                    other.termination = complete();
                    table.apply_discovery(&other).unwrap();
                    assert!(table.coverage_of(id)[&DocRole::Terms].rate().is_none());
                }
                let mut completed = partial.clone();
                completed.termination = complete();
                if axis == "documents" {
                    completed.scope.doc_roles = vec!["terms".into()];
                    table.apply_discovery(&completed).unwrap();
                    assert_eq!(table.coverage_of(id)[&DocRole::Terms].rate(), Some(0.0));
                    assert!(table.coverage_of(id)[&DocRole::RiderTerms].rate().is_none());
                    completed.scope.doc_roles = vec!["rider_terms".into()];
                    completed.termination = Termination::EmptyPage {
                        at_cursor: "fixture_only_empty".into(),
                    };
                }
                table.apply_discovery(&completed).unwrap();
                assert!(table
                    .coverage_of(id)
                    .values()
                    .all(|r| r.rate() == Some(0.0)));
                assert!(table.coverage_all().values().all(|r| r.rate().is_none()));
            }
        }
    }
}

const FIXTURE_ONLY_INVENTORY: &str = r#"<html><script>var result = {"outData":{"prdList":[
    {"prdCd":"fixture_only_A","prdNm":"fixture_only_old_name","rrsnPrdCd":"fixture_only_group","saleStYmd":"20000101","saleEdYmd":"20010101","insTxtPat":"fixture_only_terms_a.pdf","prdSryPat":"fixture_only_summary.pdf","prdMdPat":"fixture_only_business.pdf"},
    {"prdCd":"fixture_only_A","prdNm":"fixture_only_new_name","rrsnPrdCd":"fixture_only_group","saleStYmd":"20010101","saleEdYmd":"99991231","insTxtPat":"fixture_only_terms_b.pdf","prdSryPat":"fixture_only_summary.pdf","prdMdPat":"fixture_only_business.pdf"}
]}}; </script></html>"#;

#[test]
fn adapters_shipped_insurer_enumerates_products_and_documents_into_progress() {
    let denom = registry();
    let entry = lifeplanet_entry();
    let adapter = InsurerAdapter::for_entry(&entry);
    let plans = adapter.plans(&entry);
    assert_eq!(plans.len(), 8);
    assert_eq!(adapter.manifest().inventory_entrypoints.len(), 2);
    let fixture = fixture_only(FIXTURE_ONLY_INVENTORY);
    let mut table = ProgressTable::for_denominator(denom.in_scope.iter());
    let mut manifests = Vec::new();
    // Documents first exercises the previously discarded discovery path.
    for plan in plans.iter().rev() {
        assert!(adapter
            .manifest()
            .inventory_entrypoints
            .contains(&plan.entrypoint));
        assert!(adapter
            .manifest()
            .allowed_hosts
            .contains(&split_url(&plan.entrypoint).unwrap().1.to_string()));
        let manifest = run(plan, &fixture);
        assert!(exploration_state_of(&manifest.termination).reached_evidence());
        assert!(!manifest.result.empty_success);
        assert!(manifest.gaps.is_empty());
        assert!(!manifest.discovered_ids.is_empty());
        table.apply_discovery(&manifest).unwrap();
        manifests.push(manifest);
    }
    let row = table.row_mut(&entry.row.insurer_id).unwrap();
    assert_eq!(row.discovered_products.len(), 2);
    assert_eq!(row.items.len(), 4); // 2 terms + shared summary + shared business reference
    assert_eq!(
        row.items
            .iter()
            .filter(|i| i.doc_role == DocRole::Terms)
            .count(),
        2
    );
    assert!(row.items.iter().all(|i| !i.is_acquired()));
    assert_eq!(
        table.coverage_of(&entry.row.insurer_id)[&DocRole::Terms].expected,
        2
    );
    assert!(table.coverage_all().values().all(|r| r.rate().is_none()));
    let reconstructed = ProgressTable::from_discoveries(&denom, &manifests).unwrap();
    assert_eq!(
        reconstructed.coverage_of(&entry.row.insurer_id),
        table.coverage_of(&entry.row.insurer_id)
    );
}

#[test]
fn adapters_insurer_parser_verifies_empty_inventory_and_rejects_missing_fields() {
    let entry = lifeplanet_entry();
    for plan in InsurerAdapter::for_entry(&entry).plans(&entry) {
        let manifest = run(
            &plan,
            &fixture_only("<script>var result = {\"outData\":{\"prdList\":[]}};</script>"),
        );
        assert!(manifest.result.empty_success);
        assert!(matches!(
            manifest.termination,
            Termination::EmptyPage { .. }
        ));
        for page in [
            "<script>var result = {\"outData\":{}};</script>",
            "<script>var result = {\"outData\":{\"prdList\":[{}]}};</script>",
            "<script>var result = {\"outData\":{\"prdList\":[</script>",
            "<form><input type='password'></form>",
        ] {
            let failed = run(&plan, &fixture_only(page));
            assert!(!exploration_state_of(&failed.termination).reached_evidence());
            assert!(!failed.result.empty_success);
        }
        if plan.scope.axis == "documents" {
            let missing = run(&plan, &fixture_only("<script>var result = {\"outData\":{\"prdList\":[{\"prdCd\":\"fixture_only\",\"saleStYmd\":\"20000101\",\"saleEdYmd\":\"99991231\"}]}};</script>"));
            assert!(matches!(
                missing.termination,
                Termination::ParseFailed { .. }
            ));
        }
    }
}

/// 인벤토리 변수는 실제로 실행되는 script 본문에서만 온다. HTML 주석·템플릿·데이터
/// 블록·JS 주석·문자열 안의 `var result`는 목록이 아니라 파싱 실패이며(빈 목록 성공이
/// 아니다), 실행문이 두 번 나오면 모호하다. 실행문 하나를 둘러싼 미끼는 결과를 바꾸지 않는다.
#[test]
fn adapters_lifeplanet_inventory_requires_executable_script_context() {
    let entry = lifeplanet_entry();
    let empty = r#"var result = {"outData":{"prdList":[]}};"#;
    let one_row = r#"var result = {"outData":{"prdList":[{"prdCd":"fixture_only_decoy","saleStYmd":"20000101","saleEdYmd":"99991231","insTxtPat":"fixture_only_decoy_terms.pdf","prdSryPat":"fixture_only_decoy_summary.pdf","prdMdPat":"fixture_only_decoy_business.pdf"}]}};"#;
    for plan in InsurerAdapter::for_entry(&entry).plans(&entry) {
        for page in [
            format!("<!-- {empty} -->"),
            format!("<html><!-- {one_row} --></html>"),
            format!("<template><script>{empty}</script></template>"),
            format!("<script type=\"text/template\">{empty}</script>"),
            format!("<script type='application/json'>{empty}</script>"),
            format!("<script>// {empty}</script>"),
            format!("<script>/* {empty} */</script>"),
            format!(
                "<script>const t = \"{}\";</script>",
                empty.replace('"', "\\\"")
            ),
            format!("<script>const t = `{empty}`;</script>"),
            format!("<script>window.var result = 1; obj.var result = 2; my{empty}</script>"),
            "<script>var result == {};</script>".to_string(),
            format!("<div>{empty}</div>"),
            format!("<textarea>{empty}</textarea>"),
            format!("<script>{empty} {empty}</script>"),
            format!("<script>{empty}</script><script>{one_row}</script>"),
        ] {
            let manifest = run(&plan, &fixture_only(&page));
            assert!(
                matches!(manifest.termination, Termination::ParseFailed { .. }),
                "{page}"
            );
            assert!(!manifest.result.empty_success, "{page}");
            assert!(
                !exploration_state_of(&manifest.termination).reached_evidence(),
                "{page}"
            );
            assert!(manifest.discovered_ids.is_empty(), "{page}");
            assert!(manifest.product_candidates.is_empty(), "{page}");
            assert_eq!(manifest.gaps[0].kind, "failed", "{page}");
        }
        // Decoys around the one executable statement neither hide it nor leak into it:
        // a decoy row cannot become a candidate, and a decoy empty list cannot erase one.
        let decoyed_empty = format!(
            "<html><!-- {one_row} --><script type='text/template'>{one_row}</script>\
             <script type=\"text/javascript\">/* {one_row} */ var note = 'var result = 1';\n{empty} // {one_row}\n</script></html>"
        );
        let manifest = run(&plan, &fixture_only(&decoyed_empty));
        assert!(matches!(
            manifest.termination,
            Termination::EmptyPage { .. }
        ));
        assert!(manifest.result.empty_success);
        assert!(manifest.discovered_ids.is_empty());
        assert!(manifest.product_candidates.is_empty());
        let decoyed_row = format!(
            "<html><!-- {empty} --><script type='application/json'>{empty}</script>\
             <script>// {empty}\n{one_row}\n/* {empty} */</script></html>"
        );
        let manifest = run(&plan, &fixture_only(&decoyed_row));
        assert!(exploration_state_of(&manifest.termination).reached_evidence());
        assert!(!manifest.result.empty_success);
        assert_eq!(manifest.discovered_ids.len(), 1);
        assert_eq!(manifest.product_candidates.len(), 1);
        assert_eq!(
            manifest.product_candidates[0].product_code,
            "fixture_only_decoy"
        );
    }
}

/// 렉서가 분류하지 못하는 스크립트 문맥은 파싱 실패다(빈 목록 성공이 아니다): 정규식
/// 리터럴 안의 `var result`, `}`·`++` 뒤의 `/`, 끝나지 않은 문자열·주석·정규식, 템플릿
/// 치환, 함수 본문 안의 선언, Annex B `-->` 줄 주석, JSON 뒤에 이어지는 식(두 번째 선언자·
/// 멤버 접근·호출·`in`). 나눗셈·정규식·ASI가 있는 정상 스크립트의 실행문은 그대로 읽는다.
#[test]
fn adapters_lifeplanet_inventory_rejects_unclassifiable_script_contexts() {
    let entry = lifeplanet_entry();
    let empty_json = r#"{"outData":{"prdList":[]}}"#;
    let empty = format!("var result = {empty_json};");
    let one_row_json = r#"{"outData":{"prdList":[{"prdCd":"fixture_only_decoy","saleStYmd":"20000101","saleEdYmd":"99991231","insTxtPat":"fixture_only_decoy_terms.pdf","prdSryPat":"fixture_only_decoy_summary.pdf","prdMdPat":"fixture_only_decoy_business.pdf"}]}}"#;
    let one_row = format!("var result = {one_row_json};");
    for plan in InsurerAdapter::for_entry(&entry).plans(&entry) {
        for page in [
            // The reviewer's case: a regex literal whose body is the statement.
            format!("<script>const decoy = /;{empty}/;</script>"),
            format!("<script>f(/;{empty}/);</script>"),
            format!("<script>function f() {{ return /;{empty}/; }}</script>"),
            format!("<script>if (x) /;{empty}/.test(y);</script>"),
            format!("<script>var r = /[/];{empty}/;</script>"),
            format!("<script>var r = x / 2 / /;{empty}/;</script>"),
            // Both readings of `/` are possible: rejected, not guessed.
            format!("<script>function f() {{}} /;{empty}/;</script>"),
            format!("<script>i++ /;{empty}/;</script>"),
            format!("<script>var result = {empty_json} / x / 1;</script>"),
            // A browser would not run these at all.
            format!("<script>var x = \"unterminated\n{empty}</script>"),
            format!("<script>var x = 'unterminated\n{empty}</script>"),
            format!("<script>/* {empty}</script>"),
            format!("<script>var r = /unterminated\n{empty}</script>"),
            format!("<script>var r = `${{'`'}}'; {empty} `;</script>"),
            format!("<script>f(({empty}</script>"),
            format!("<script>{empty} }}</script>"),
            // Not the page-level inventory.
            format!("<script>(function () {{ {empty} }})();</script>"),
            format!("<script>if (x) {{ {empty} }}</script>"),
            format!("<script>\n--> {empty}\n</script>"),
            format!("<script>/*\n*/ --> {empty}\n</script>"),
            format!("<script>--> {empty}\n</script>"),
            // The JSON is not where the statement ends.
            format!("<script>var result = {empty_json}, result = {one_row_json};</script>"),
            format!("<script>var result = {one_row_json}.outData.prdList.slice(0, 0);</script>"),
            format!("<script>var result = {empty_json}\n.outData;</script>"),
            format!("<script>var result = {empty_json}\n(x);</script>"),
            format!("<script>var result = {empty_json}\nin window;</script>"),
            format!("<script>var result = {empty_json} // note\n.outData;</script>"),
            format!("<script>var result = {empty_json} x = 1;</script>"),
        ] {
            let manifest = run(&plan, &fixture_only(&page));
            assert!(
                matches!(manifest.termination, Termination::ParseFailed { .. }),
                "{page}: {:?}",
                manifest.termination
            );
            assert!(!manifest.result.empty_success, "{page}");
            assert!(
                !exploration_state_of(&manifest.termination).reached_evidence(),
                "{page}"
            );
            assert!(manifest.discovered_ids.is_empty(), "{page}");
            assert!(manifest.product_candidates.is_empty(), "{page}");
            assert_eq!(manifest.gaps[0].kind, "failed", "{page}");
        }
        // Ordinary script text around the one executable statement still yields it:
        // divisions, regex literals (with flags and classes), `if` heads, comments, `-->`
        // comments and ASI line breaks are classified, not guessed.
        for page in [
            format!("<script>var half = total / 2; {empty}</script>"),
            format!("<script>var avg = (a + b) / 2; var q = arr[0] / 2; {empty}</script>"),
            format!("<script>var re = /\\/;var result = /gi; {empty}</script>"),
            format!("<script>var re = /[/;]var result = 1/; {empty}</script>"),
            format!("<script>if (x) /;var result = 1/.test(y); {empty}</script>"),
            format!("<script>function f() {{ return /;var result = 1/; }} {empty}</script>"),
            format!("<script>var n = /a/g.test(x) ? 1 : 2 / 1; {empty}</script>"),
            format!("<script>var s = 'a/b'; var t = \"c/d\"; var u = `e/f`; {empty}</script>"),
            format!("<script>/*\n*/ --> var result = 1;\n{empty}</script>"),
            format!(
                "<script>{}\nvar x = 1;</script>",
                empty.trim_end_matches(';')
            ),
            format!(
                "<script>{}\n// note\nfunction f() {{}}</script>",
                empty.trim_end_matches(';')
            ),
            format!("<script>{} /* c */ ;</script>", empty.trim_end_matches(';')),
            format!("<script>{}</script>", empty.trim_end_matches(';')),
        ] {
            let manifest = run(&plan, &fixture_only(&page));
            assert!(
                matches!(manifest.termination, Termination::EmptyPage { .. }),
                "{page}: {:?}",
                manifest.termination
            );
            assert!(manifest.result.empty_success, "{page}");
            assert!(manifest.product_candidates.is_empty(), "{page}");
        }
        let manifest = run(
            &plan,
            &fixture_only(&format!(
                "<script>var ratio = (a + b) / 2; var re = /;var result = 1/; {one_row}</script>"
            )),
        );
        assert!(exploration_state_of(&manifest.termination).reached_evidence());
        assert!(!manifest.result.empty_success);
        assert_eq!(manifest.product_candidates.len(), 1);
        assert_eq!(
            manifest.product_candidates[0].product_code,
            "fixture_only_decoy"
        );
    }
}

#[test]
fn adapters_unsupported_insurers_have_no_fake_entry_enumeration() {
    let denom = registry();
    for entry in &denom.in_scope {
        let adapter = InsurerAdapter::for_entry(entry);
        if entry.row.insurer_id != "life-kyobo-lifeplanet" {
            assert!(adapter.plans(entry).is_empty());
            assert!(!adapter.manifest().known_limitations.is_empty());
        }
    }
    let mut entry = lifeplanet_entry();
    for access in [
        onjeon_contracts::HostAccess::JsShell,
        onjeon_contracts::HostAccess::NotChecked,
    ] {
        entry.row.disclosure_access = access;
        assert!(InsurerAdapter::for_entry(&entry).plans(&entry).is_empty());
    }
}

#[test]
fn adapters_html_context_rejects_template_links_instead_of_completing_single_page() {
    let entry = lifeplanet_entry();
    for plan in klia().plans(&entry).into_iter().chain(knia().plans(&entry)) {
        let (link_substring, id_query_key) = match &plan.parser {
            ListParser::HtmlLinks {
                link_substring,
                id_query_key,
                ..
            } => (link_substring, id_query_key),
            _ => unreachable!(),
        };
        let link = format!("<a href='/{link_substring}?{id_query_key}=fixture_only_fake'>x</a>");
        for page in [
            format!("<script>const template=\"{link}\";</script>"),
            format!("<!-- {link} -->"),
            format!("<style>/* {link} */</style>"),
            format!("<textarea>{link}</textarea>"),
            format!("<title>{link}</title>"),
            format!("<template><template>{link}</template>{link}</template>"),
            format!("<div data-template=\"{link}\"></div>"),
            format!("<svg>{link}</svg>"),
            format!("<select><option>{link}</option></select>"),
            format!("<script>const template=\"{link}\";"),
            format!("<!-- {link}"),
            format!("<template>{link}"),
        ] {
            let manifest = run(&plan, &fixture_only(&page));
            assert!(
                matches!(manifest.termination, Termination::ParseFailed { .. }),
                "{page}"
            );
            assert!(manifest.discovered_ids.is_empty());
            assert!(!manifest.result.empty_success);
            assert_eq!(manifest.gaps[0].kind, "failed");
        }
        // A real link after the inert content still works, and preserves identifier case.
        let body = format!("<!-- {link} --><script>const t=\"{link}\";</script><A title='x > y' HREF=/{link_substring}?x=1&amp;{id_query_key}=fixture_only_Ab12>real</A>");
        let manifest = run(&plan, &fixture_only(&body));
        assert_eq!(manifest.discovered_ids, ["fixture_only_Ab12"]);
        assert!(exploration_state_of(&manifest.termination).reached_evidence());
    }
}

#[test]
fn adapters_html_attributes_and_script_boundaries_cannot_invent_items() {
    let parser = ListParser::HtmlLinks {
        link_substring: "fixture_only_list".into(),
        id_query_key: "id".into(),
        total_marker: None,
        empty_marker: None,
    };
    let link = "<a href='/fixture_only_list?id=fixture_only_fake'>fake</a>";
    for body in [
        format!("<a title=\"{link}\">title</a>"),
        format!("<!DOCTYPE html PUBLIC \"fixture_only > {link}\">"),
        "<div href='/fixture_only_list?id=fixture_only_fake'></div>".to_string(),
        "<a:fixture_only href='/fixture_only_list?id=fixture_only_fake'>x</a:fixture_only>"
            .to_string(),
        format!("<script><!--<script></script>{link}--></script>"),
        format!("<script>const s='</scriptExtra>{link}';</script>"),
        format!("<script/>const s=\"{link}\";</script>"),
        "<a href='/home' href='/fixture_only_list?id=fixture_only_fake'>duplicate attribute</a>"
            .to_string(),
        "<a href='/fixture_only_list?id=fixture_only_real' title='unterminated".to_string(),
    ] {
        assert!(parse_page(&parser, body.as_bytes()).is_err(), "{body}");
    }
    let body = format!("<script>const s=\"{link}\";</SCRIPT ><a title=\"{link}\" href='/fixture_only_list?id=fixture_only_real'>real</a>");
    assert_eq!(
        parse_page(&parser, body.as_bytes()).unwrap().item_ids,
        ["fixture_only_real"]
    );
}

#[test]
fn adapters_inert_html_cannot_supply_empty_or_total_evidence() {
    let parser = ListParser::HtmlLinks {
        link_substring: "fixture_only_list".into(),
        id_query_key: "id".into(),
        total_marker: Some("fixture_only_total=".into()),
        empty_marker: Some("<div class='fixture_only_empty'>No results</div>".into()),
    };
    let evidence = "fixture_only_total=0 <div class='fixture_only_empty'>No results</div>";
    for body in [
        format!("<!-- {evidence} -->"),
        format!("<script>const t=\"{evidence}\";</script>"),
        format!("<template>{evidence}</template>"),
        format!("<textarea>{evidence}</textarea>"),
        format!("<style>{evidence}</style>"),
        format!("<div data-template=\"{evidence}\"></div>"),
    ] {
        assert!(parse_page(&parser, body.as_bytes()).is_err(), "{body}");
    }
    assert!(parse_page(&parser, evidence.as_bytes())
        .unwrap()
        .item_ids
        .is_empty());
}

#[test]
fn adapters_stored_candidate_metadata_reconstructs_historical_product_document_edges() {
    use crate::store::Store;
    let entry = lifeplanet_entry();
    let plans = InsurerAdapter::for_entry(&entry).plans(&entry);
    let fixture = fixture_only(FIXTURE_ONLY_INVENTORY);
    let mut manifests = Vec::new();
    let dir = std::env::temp_dir().join(format!(
        "fixture_only_candidate_edges_{}",
        std::process::id()
    ));
    let store = crate::store::LocalStore::new(&dir);
    for plan in plans.iter().rev() {
        let manifest = run(plan, &fixture);
        let (key, _) = record_manifest(&store, &manifest).unwrap();
        let saved: serde_json::Value = serde_json::from_slice(&store.get(&key).unwrap()).unwrap();
        let candidates = saved["product_candidates"].as_array().unwrap();
        assert_eq!(candidates.len(), 2);
        assert_ne!(candidates[0]["candidate_id"], candidates[1]["candidate_id"]);
        for (candidate, (from, to, name, terms)) in candidates.iter().zip([
            (
                "20000101",
                "20010101",
                "fixture_only_old_name",
                "fixture_only_terms_a.pdf",
            ),
            (
                "20010101",
                "99991231",
                "fixture_only_new_name",
                "fixture_only_terms_b.pdf",
            ),
        ]) {
            assert_eq!(candidate["product_code"], "fixture_only_A");
            assert_eq!(candidate["sale_from"], from);
            assert_eq!(candidate["sale_to"], to);
            assert_eq!(candidate["source_metadata"]["prdNm"], name);
            assert_eq!(
                candidate["source_metadata"]["rrsnPrdCd"],
                "fixture_only_group"
            );
            assert_eq!(
                candidate["source_page_hash"],
                saved["pages"][0]["page_hash"]
            );
            let documents = candidate["documents"].as_array().unwrap();
            assert_eq!(documents.len(), 3);
            for (role, reference) in [
                ("terms", terms),
                ("summary", "fixture_only_summary.pdf"),
                ("business_method", "fixture_only_business.pdf"),
            ] {
                assert!(documents
                    .iter()
                    .any(|doc| doc["doc_role"] == role && doc["reference"] == reference));
            }
        }
        manifests.push(manifest);
    }
    let denom = registry();
    let mut table = ProgressTable::from_discoveries(&denom, &manifests).unwrap();
    let row = table.row_mut(&entry.row.insurer_id).unwrap();
    assert_eq!(row.product_candidates.len(), 2);
    assert_eq!(row.items.len(), 4);
    assert!(row.items.iter().all(|i| !i.is_acquired()));
    for candidate in row.product_candidates.values() {
        for document in &candidate.documents {
            assert!(row
                .items
                .iter()
                .any(|i| i.doc_role == document.doc_role && i.item_id == document.reference));
        }
    }
    // A document-only reconstruction retains both product edges to the shared file.
    manifests.retain(|m| m.scope.axis == "documents");
    let mut table = ProgressTable::from_discoveries(&denom, &manifests).unwrap();
    assert_eq!(
        table
            .row_mut(&entry.row.insurer_id)
            .unwrap()
            .product_candidates
            .len(),
        2
    );
    std::fs::remove_dir_all(dir).unwrap();
}

#[test]
fn adapters_scope_role_progress_preserves_every_hold_block_and_reason_in_either_order() {
    let denom = registry();
    let id = &denom.in_scope[0].row.insurer_id;
    let mut hold = fixture_only_manifest(id, "documents", &[DocRole::Terms], &[]);
    hold.termination = Termination::RobotsHold {
        reason: "fixture_only_robots_unavailable".into(),
    };
    hold.gaps = vec![GapRecord {
        kind: "hold".into(),
        range: "whole_scope".into(),
        reason: "fixture_only_robots_unavailable".into(),
    }];
    let mut block = hold.clone();
    block.scope.channel = Some("fixture_only_other_channel".into());
    block.scope.sale_status = Some("fixture_only_stopped".into());
    block.scope.period_from = Some("2000-01-01".into());
    block.scope.period_to = Some("2001-01-01".into());
    block.termination = Termination::RobotsBlocked {
        reason: "fixture_only_robots_denied".into(),
    };
    block.gaps = vec![GapRecord {
        kind: "blocked".into(),
        range: "whole_scope".into(),
        reason: "fixture_only_robots_denied".into(),
    }];
    let summary = fixture_only_manifest(id, "documents", &[DocRole::Summary], &[]);
    for manifests in [
        vec![hold.clone(), block.clone(), summary.clone()],
        vec![summary.clone(), block.clone(), hold.clone()],
    ] {
        let mut table = ProgressTable::from_discoveries(&denom, &manifests).unwrap();
        let row = table.row_mut(id).unwrap();
        assert!(!row.exploration["documents"].reached_evidence());
        let scopes = &row.scope_progress;
        assert!(scopes
            .iter()
            .any(|(key, progress)| key.doc_role == Some(DocRole::Summary)
                && progress.state.reached_evidence()));
        let issues = &row.unknown_denominators[&DocRole::Terms];
        for expected in [&hold, &block] {
            let issue = issues
                .iter()
                .find(|issue| {
                    issue.scope.axis == "documents"
                        && issue.scope.channel == expected.scope.channel
                        && issue.scope.sale_status == expected.scope.sale_status
                        && issue.scope.period_from == expected.scope.period_from
                        && issue.scope.period_to == expected.scope.period_to
                })
                .unwrap();
            assert_eq!(issue.scope.doc_role, Some(DocRole::Terms));
            assert_eq!(
                issue.progress.state,
                exploration_state_of(&expected.termination)
            );
            assert_eq!(issue.progress.gaps, expected.gaps);
        }
        assert!(!row.unknown_denominators[&DocRole::Summary]
            .iter()
            .any(|i| i.scope.axis == "documents" && i.scope.channel.is_none()));
        // A retry resolves only the exact scope/role; the other channel stays blocked.
        let mut resolved = hold.clone();
        resolved.termination = complete();
        resolved.gaps.clear();
        table.apply_discovery(&resolved).unwrap();
        let row = table.row_mut(id).unwrap();
        assert!(!row.exploration["documents"].reached_evidence());
        let issues = &row.unknown_denominators[&DocRole::Terms];
        assert!(!issues
            .iter()
            .any(|i| i.scope.axis == "documents" && i.scope.channel.is_none()));
        assert!(issues.iter().any(|i| i.progress.gaps == block.gaps));
        assert!(table.coverage_of(id)[&DocRole::Terms].rate().is_none());
    }
}
