//! Adapter (denominator enumeration) tests for T-DT-04. All inputs are synthetic
//! `fixture_only` data — no real disclosure site is contacted (O17), and every fixture
//! transport carries the `origin=fixture` marker in spirit (fixture-only code paths).

mod adapters {
    use std::collections::BTreeMap;
    use std::path::PathBuf;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::sync::Mutex;

    use onjeon_collect::adapters::manifest::ScopeDesc;
    use onjeon_collect::adapters::{
        self, company_doc_roles, exploration_state_of, klia, unenumerated_manifest,
        AcquisitionEvidence, AssociationPlan, DenominatorItem, DiscoveryAdapter, Enumerator,
        ExplorationState, Fetch, FetchError, FetchResponse, InsurerAdapter, ListParser, ListPlan,
        Pagination, ProgressTable, RobotsGate, RobotsVerdict, RunMeta, Termination,
    };
    use onjeon_collect::Store;
    use onjeon_contracts::{AcquisitionStatus, DocRole, HostAccess};

    // ---------- fixture transport ----------

    /// A `Fetch` that answers from a URL→response map (or a queue for repeated URLs) and
    /// records every requested URL. Missing URLs answer `FetchError::Network`.
    struct FixtureFetch {
        responses: BTreeMap<String, FixtureResponse>,
        requested: Mutex<Vec<String>>,
    }

    #[derive(Clone)]
    enum FixtureResponse {
        Ok {
            status: u16,
            headers: Vec<(String, String)>,
            body: Vec<u8>,
        },
        Err(FetchError),
    }

    impl FixtureFetch {
        fn new() -> Self {
            Self {
                responses: BTreeMap::new(),
                requested: Mutex::new(Vec::new()),
            }
        }
        fn add(&mut self, url: &str, status: u16, body: &str) {
            self.responses.insert(
                url.into(),
                FixtureResponse::Ok {
                    status,
                    headers: vec![("content-type".into(), "text/html".into())],
                    body: body.as_bytes().to_vec(),
                },
            );
        }
        fn add_json(&mut self, url: &str, status: u16, body: &str) {
            self.responses.insert(
                url.into(),
                FixtureResponse::Ok {
                    status,
                    headers: vec![("content-type".into(), "application/json".into())],
                    body: body.as_bytes().to_vec(),
                },
            );
        }
        fn add_err(&mut self, url: &str, e: FetchError) {
            self.responses.insert(url.into(), FixtureResponse::Err(e));
        }
        fn requested(&self) -> Vec<String> {
            self.requested.lock().unwrap().clone()
        }
    }

    impl Fetch for FixtureFetch {
        fn fetch(&self, url: &str, _max_bytes: usize) -> Result<FetchResponse, FetchError> {
            self.requested.lock().unwrap().push(url.to_string());
            match self.responses.get(url) {
                Some(FixtureResponse::Ok {
                    status,
                    headers,
                    body,
                }) => Ok(FetchResponse {
                    status: *status,
                    headers: headers.clone(),
                    body: body.clone(),
                    truncated: false,
                }),
                Some(FixtureResponse::Err(e)) => Err(*e),
                None => Err(FetchError::Network),
            }
        }
    }

    static NOW: u64 = 1_760_000_000; // fixture epoch seconds

    fn clock() -> u64 {
        NOW
    }

    fn meta() -> RunMeta {
        RunMeta {
            survey_round: "round-fixture".into(),
            source_id: "fixture_src".into(),
            adapter_version: "0.1.0".into(),
        }
    }

    fn scope() -> ScopeDesc {
        ScopeDesc {
            axis: "product_list".into(),
            institution_id: "fixture_co".into(),
            sale_status: None,
            channel: None,
            period_from: None,
            period_to: None,
            doc_roles: vec!["disclosure_list".into()],
        }
    }

    fn allow_all_robots(ff: &mut FixtureFetch, host: &str) {
        ff.add(
            &format!("https://{host}/robots.txt"),
            200,
            "User-agent: *\nAllow: /\n",
        );
    }

    fn plan(entrypoint: &str) -> ListPlan {
        ListPlan {
            scope: scope(),
            query_signature: "scope=fixture_list".into(),
            entrypoint: entrypoint.into(),
            pagination: Pagination::PageNumber { start: 1 },
            parser: ListParser::HtmlLinks {
                link_substring: "item.do?id=".into(),
                id_query_key: "id".into(),
                total_marker: None,
            },
            max_pages: 10,
        }
    }

    // ---------- required test id: acquisition-reason-not-counted ----------

    /// 09 P02: 확보 = 원본 보존 + 구획 추출 + 판 연결(accepted) 모두. 사유만 있는 항목은
    /// 분모에 남되 분자에 들어가지 않는다 — 10개를 넣어도 확보율은 오르지 않는다.
    #[test]
    fn acquisition_reason_not_counted() {
        let denom =
            adapters::denominator_from_rows(vec![fixture_row("ins-a")], vec![], vec![]).unwrap();
        let mut table = ProgressTable::for_denominator(denom.in_scope.iter());
        let row = table.row_mut("ins-a").unwrap();
        for i in 0..10 {
            row.items.push(DenominatorItem {
                item_id: format!("prod:x:terms:{i}"),
                doc_role: DocRole::Terms,
                evidence: AcquisitionEvidence::default(),
                unacquired: Some((AcquisitionStatus::Blocked, "fixture_only reason".into())),
            });
        }
        let cov = table.coverage_of("ins-a");
        let terms = &cov[&DocRole::Terms];
        assert_eq!(terms.expected, 10);
        assert_eq!(terms.acquired, 0);
        assert_eq!(terms.rate(), Some(0.0));
        assert_eq!(terms.unacquired.get("blocked"), Some(&10));

        // Partial evidence is still unacquired: raw + segment without accepted realizes.
        let row = table.row_mut("ins-a").unwrap();
        row.items.push(DenominatorItem {
            item_id: "prod:x:terms:partial".into(),
            doc_role: DocRole::Terms,
            evidence: AcquisitionEvidence {
                raw_stored: true,
                segment_extracted: true,
                edition_link_accepted: false,
            },
            unacquired: None,
        });
        // A reasoned item with partial evidence stays under its reason, not acquired.
        row.items.push(DenominatorItem {
            item_id: "prod:x:terms:reasoned".into(),
            doc_role: DocRole::Terms,
            evidence: AcquisitionEvidence {
                raw_stored: true,
                segment_extracted: false,
                edition_link_accepted: false,
            },
            unacquired: Some((AcquisitionStatus::NotFound, "fixture_only".into())),
        });
        let cov = table.coverage_of("ins-a");
        let terms = &cov[&DocRole::Terms];
        assert_eq!(terms.expected, 12);
        assert_eq!(terms.acquired, 0);
        assert_eq!(terms.unacquired.get("partial_evidence"), Some(&1));
        assert_eq!(terms.unacquired.get("not_found"), Some(&1));

        // Only the full three-part evidence counts.
        let row = table.row_mut("ins-a").unwrap();
        row.items.push(DenominatorItem {
            item_id: "prod:x:terms:full".into(),
            doc_role: DocRole::Terms,
            evidence: AcquisitionEvidence {
                raw_stored: true,
                segment_extracted: true,
                edition_link_accepted: true,
            },
            unacquired: None,
        });
        let cov = table.coverage_of("ins-a");
        let terms = &cov[&DocRole::Terms];
        assert_eq!(terms.acquired, 1);
        assert_eq!(terms.expected, 13);

        // The six document roles are reported separately (문서 종류별 확보·미확보).
        assert_eq!(cov.keys().cloned().collect::<Vec<_>>(), company_doc_roles());
        // A role with no denominator items reports None, never NaN.
        assert_eq!(cov[&DocRole::PriceTable].rate(), None);
    }

    fn fixture_row(id: &str) -> BTreeMap<String, String> {
        [
            ("insurer_id", id),
            ("name_ko", "픽스처보험"),
            ("sector", "life"),
            ("foreign_branch", "false"),
            ("listed_in", "fixture_list"),
            ("entity_evidence", "one_source"),
            ("in_current_assoc_list", "true"),
            ("disclosure_url", ""),
            ("disclosure_access", "not_checked"),
            ("home_url", ""),
            ("home_access", "not_checked"),
            ("disclosure_status", "unqueried"),
            ("product_list_status", "unqueried"),
            ("observed_at", "2026-10-09T00:00:00Z"),
        ]
        .into_iter()
        .map(|(k, v)| (k.to_string(), v.to_string()))
        .collect()
    }

    // ---------- registry denominator ----------

    /// ADR-0018: insurers.csv 53곳 + public-epost가 분모이고, 공제·한국무역보험공사·seed·
    /// excluded_or_historical은 사유를 남기고 분모에서 빠진다.
    #[test]
    fn denominator_loads_registry_with_adr0018_scope() {
        let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../data/registry");
        let denom = adapters::load_denominator(&dir).unwrap();
        assert_eq!(denom.in_scope.len(), 54);
        assert!(denom
            .in_scope
            .iter()
            .any(|e| e.kind == adapters::InstitutionKind::PublicInstitution
                && e.row.insurer_id == "public-epost"));
        assert_eq!(
            denom
                .in_scope
                .iter()
                .filter(|e| e.kind == adapters::InstitutionKind::Insurer)
                .count(),
            53
        );
        let reasons: BTreeMap<&str, usize> =
            denom.exclusions.iter().fold(BTreeMap::new(), |mut m, e| {
                *m.entry(e.reason).or_insert(0) += 1;
                m
            });
        // 공제 13곳 + 농협(구 공제) 시드 1곳.
        assert_eq!(reasons.get("cooperative_out_of_scope"), Some(&14));
        assert_eq!(reasons.get("non_personal_lines"), Some(&1));
        assert_eq!(reasons.get("historical_or_non_insurer"), Some(&49));
        // 제외 행에는 출처 증거가 있다.
        assert!(denom
            .exclusions
            .iter()
            .all(|e| e.evidence_ref.starts_with("data/registry/")));
        // 기관마다 진행표가 있다.
        let table = ProgressTable::for_denominator(denom.in_scope.iter());
        assert_eq!(table.rows.len(), 54);
        assert!(table.rows.iter().all(|r| r
            .exploration
            .values()
            .all(|s| *s == ExplorationState::Unqueried)));
    }

    /// seed는 분모에 넣지 않는다 (registry README).
    #[test]
    fn denominator_seed_rows_are_excluded() {
        let mut row = fixture_row("seed-x");
        row.insert("entity_evidence".into(), "seed".into());
        let denom = adapters::denominator_from_rows(vec![row], vec![], vec![]).unwrap();
        assert!(denom.in_scope.is_empty());
        assert_eq!(denom.exclusions[0].reason, "seed_not_listed");
    }

    /// 알 수 없는 어휘값은 기본값으로 처리하지 않고 실패한다 (vocabulary rule 4).
    #[test]
    fn denominator_rejects_unknown_vocabulary() {
        let mut row = fixture_row("ins-x");
        row.insert("disclosure_access".into(), "guessed".into());
        assert!(adapters::denominator_from_rows(vec![row], vec![], vec![]).is_err());
        let mut row = fixture_row("ins-x");
        row.insert("disclosure_status".into(), "acquired".into());
        assert!(adapters::denominator_from_rows(vec![row], vec![], vec![]).is_err());
    }

    #[test]
    fn csv_parser_handles_quotes_commas_newlines() {
        let csv = b"a,b,c\n\"x,y\",\"line\nbreak\",\"q\"\"q\"\n1,2,3\n";
        let rows = adapters::parse_csv(csv).unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0]["a"], "x,y");
        assert_eq!(rows[0]["b"], "line\nbreak");
        assert_eq!(rows[0]["c"], "q\"q");
        assert_eq!(rows[1]["c"], "3");
    }

    // ---------- robots gate ----------

    /// robots를 확인할 수 없는 호스트는 보류다: 목록 URL을 요청하지 않고, 범위는 hold로 남는다.
    #[test]
    fn robots_unverifiable_holds_host_and_never_fetches() {
        let mut ff = FixtureFetch::new();
        ff.add_err("https://h.fixture/robots.txt", FetchError::Network);
        ff.add(
            "https://h.fixture/list?page=1",
            200,
            "<a href='item.do?id=1'>x</a>",
        );
        let mut gate = RobotsGate::new(86_400);
        let mut en = Enumerator {
            fetch: &ff,
            gate: &mut gate,
            clock: &clock,
            page_cap_bytes: adapters::LIST_PAGE_MAX_BYTES,
            rate_policy: "default".into(),
        };
        let m = en.run(&plan("https://h.fixture/list?page={cursor}"), &meta());
        assert!(matches!(
            m.termination,
            Termination::RobotsHold { ref reason } if reason == "robots_unreachable"
        ));
        assert_eq!(m.gaps[0].kind, "hold");
        assert_eq!(
            ff.requested(),
            vec!["https://h.fixture/robots.txt".to_string()]
        );
        assert_eq!(
            exploration_state_of(&m.termination),
            ExplorationState::Hold {
                reason: "robots_unreachable".into()
            }
        );
        // 같은 UTC 일 안에서는 다시 시도하지 않는다.
        assert!(matches!(
            gate.check(&ff, "https://h.fixture/other", NOW + 60),
            RobotsVerdict::Unverifiable { .. }
        ));
        assert_eq!(ff.requested().len(), 1);
    }

    /// robots.txt가 Disallow면 차단이고 우회하지 않는다.
    #[test]
    fn robots_disallow_blocks_without_fetching() {
        let mut ff = FixtureFetch::new();
        ff.add(
            "https://h.fixture/robots.txt",
            200,
            "User-agent: *\nDisallow: /list\nAllow: /public\n",
        );
        ff.add("https://h.fixture/list?page=1", 200, "x");
        let mut gate = RobotsGate::new(86_400);
        let mut en = Enumerator {
            fetch: &ff,
            gate: &mut gate,
            clock: &clock,
            page_cap_bytes: adapters::LIST_PAGE_MAX_BYTES,
            rate_policy: "default".into(),
        };
        let m = en.run(&plan("https://h.fixture/list?page={cursor}"), &meta());
        assert!(matches!(m.termination, Termination::RobotsBlocked { .. }));
        assert_eq!(m.gaps[0].kind, "blocked");
        assert_eq!(
            ff.requested(),
            vec!["https://h.fixture/robots.txt".to_string()]
        );
    }

    /// RFC 9309: 가장 긴 규칙이 이기고 Allow가 동률에서 이긴다. `*`와 `$`를 지원한다.
    #[test]
    fn robots_longest_match_and_wildcards() {
        let mut ff = FixtureFetch::new();
        ff.add(
        "https://h.fixture/robots.txt",
        200,
        "User-agent: *\nDisallow: /\nAllow: /list/\nDisallow: /list/secret$\nDisallow: /list/*.tmp$\n",
    );
        let mut gate = RobotsGate::new(86_400);
        assert!(matches!(
            gate.check(&ff, "https://h.fixture/list/a", NOW),
            RobotsVerdict::Allow { .. }
        ));
        assert!(matches!(
            gate.check(&ff, "https://h.fixture/list/secret", NOW),
            RobotsVerdict::Disallow
        ));
        assert!(matches!(
            gate.check(&ff, "https://h.fixture/list/x.tmp", NOW),
            RobotsVerdict::Disallow
        ));
        assert!(matches!(
            gate.check(&ff, "https://h.fixture/list/x.tmpy", NOW),
            RobotsVerdict::Allow { .. }
        ));
    }

    /// robots.txt의 401/403은 forbidden 차단이다.
    #[test]
    fn robots_forbidden_blocks_host() {
        let mut ff = FixtureFetch::new();
        ff.add("https://h.fixture/robots.txt", 403, "");
        let mut gate = RobotsGate::new(86_400);
        assert!(matches!(
            gate.check(&ff, "https://h.fixture/a", NOW),
            RobotsVerdict::Forbidden
        ));
    }

    /// robots.txt의 다른 4xx는 '규칙 없음'으로 전부 허용이다.
    #[test]
    fn robots_404_means_no_rules() {
        let mut ff = FixtureFetch::new();
        ff.add("https://h.fixture/robots.txt", 404, "");
        ff.add(
            "https://h.fixture/list?page=1",
            200,
            "<a href='item.do?id=1'>x</a>",
        );
        let mut gate = RobotsGate::new(86_400);
        let mut en = Enumerator {
            fetch: &ff,
            gate: &mut gate,
            clock: &clock,
            page_cap_bytes: adapters::LIST_PAGE_MAX_BYTES,
            rate_policy: "default".into(),
        };
        let m = en.run(&plan("https://h.fixture/list?page={cursor}"), &meta());
        assert_eq!(m.result.unique_item_count, 1);
    }

    // ---------- login page is not a success ----------

    /// §8 체크 사례: 목록 200 응답이 로그인 HTML이면 확보 성공으로 세지 않는다.
    #[test]
    fn login_html_200_is_blocked_not_enumerated() {
        let mut ff = FixtureFetch::new();
        allow_all_robots(&mut ff, "h.fixture");
        ff.add(
        "https://h.fixture/list?page=1",
        200,
        "<html><form action='/member/login'><input name='id'><input type='password'></form></html>",
    );
        let mut gate = RobotsGate::new(86_400);
        let mut en = Enumerator {
            fetch: &ff,
            gate: &mut gate,
            clock: &clock,
            page_cap_bytes: adapters::LIST_PAGE_MAX_BYTES,
            rate_policy: "default".into(),
        };
        let m = en.run(&plan("https://h.fixture/list?page={cursor}"), &meta());
        assert!(matches!(m.termination, Termination::LoginPage { .. }));
        assert_eq!(m.result.unique_item_count, 0);
        assert!(!m.result.empty_success);
        assert_eq!(m.gaps[0].kind, "blocked");
        assert_eq!(m.pages[0].page_kind, "login_page");
        assert_eq!(
            exploration_state_of(&m.termination),
            ExplorationState::Blocked {
                reason: "login_page".into()
            }
        );
    }

    #[test]
    fn login_detection_markers() {
        assert!(adapters::looks_like_login(
            b"<form><input type='password' name='pw'></form>"
        ));
        assert!(adapters::looks_like_login(
            b"<form action='/signin'><input name='a'></form>"
        ));
        assert!(!adapters::looks_like_login(
            b"<html><a href='item.do?id=1'>list</a>login</html>"
        ));
    }

    // ---------- termination evidence ----------

    /// 페이지 번호 열거: 항목이 있는 페이지 → 빈 페이지 도달이 종료 증거다.
    #[test]
    fn enumeration_terminates_on_empty_page() {
        let mut ff = FixtureFetch::new();
        allow_all_robots(&mut ff, "h.fixture");
        ff.add(
            "https://h.fixture/list?page=1",
            200,
            "<a href='item.do?id=1'>a</a><a href='item.do?id=2'>b</a>",
        );
        ff.add(
            "https://h.fixture/list?page=2",
            200,
            "<a href='item.do?id=3'>c</a>",
        );
        ff.add("https://h.fixture/list?page=3", 200, "<div>nothing</div>");
        let mut gate = RobotsGate::new(86_400);
        let mut en = Enumerator {
            fetch: &ff,
            gate: &mut gate,
            clock: &clock,
            page_cap_bytes: adapters::LIST_PAGE_MAX_BYTES,
            rate_policy: "default".into(),
        };
        let m = en.run(&plan("https://h.fixture/list?page={cursor}"), &meta());
        assert!(matches!(m.termination, Termination::EmptyPage { .. }));
        assert_eq!(m.result.unique_item_count, 3);
        assert_eq!(m.pages.len(), 3);
        assert_eq!(m.pages[0].first_item_id.as_deref(), Some("1"));
        assert_eq!(m.pages[0].last_item_id.as_deref(), Some("2"));
        assert!(!m.pages[0].page_hash.is_empty());
    }

    /// 공시된 전체 건수에 도달하면 종료 증거다.
    #[test]
    fn enumeration_terminates_on_advertised_total() {
        let mut ff = FixtureFetch::new();
        allow_all_robots(&mut ff, "h.fixture");
        ff.add_json(
            "https://h.fixture/api?p=1",
            200,
            r#"{"items":[{"id":"a"},{"id":"b"}],"total":2}"#,
        );
        let mut gate = RobotsGate::new(86_400);
        let mut en = Enumerator {
            fetch: &ff,
            gate: &mut gate,
            clock: &clock,
            page_cap_bytes: adapters::LIST_PAGE_MAX_BYTES,
            rate_policy: "default".into(),
        };
        let mut p = plan("https://h.fixture/api?p={cursor}");
        p.parser = ListParser::Json {
            items_path: "items".into(),
            id_field: "id".into(),
            total_field: Some("total".into()),
            next_field: None,
        };
        let m = en.run(&p, &meta());
        assert!(matches!(
            m.termination,
            Termination::AdvertisedTotalReached {
                unique_items: 2,
                advertised_total: 2
            }
        ));
        assert_eq!(ff.requested().len(), 2); // robots + one page
    }

    /// 같은 마지막 페이지가 반복돼도 성공으로 종료하지 않는다 — 꼬리는 미탐색이다.
    #[test]
    fn repeated_last_page_is_not_a_success() {
        let mut ff = FixtureFetch::new();
        allow_all_robots(&mut ff, "h.fixture");
        let page = "<a href='item.do?id=1'>a</a>";
        ff.add("https://h.fixture/list?page=1", 200, page);
        ff.add("https://h.fixture/list?page=2", 200, page); // 같은 내용 반복
        let mut gate = RobotsGate::new(86_400);
        let mut en = Enumerator {
            fetch: &ff,
            gate: &mut gate,
            clock: &clock,
            page_cap_bytes: adapters::LIST_PAGE_MAX_BYTES,
            rate_policy: "default".into(),
        };
        let m = en.run(&plan("https://h.fixture/list?page={cursor}"), &meta());
        assert!(matches!(m.termination, Termination::PageRepeat { .. }));
        assert!(m.gaps.iter().any(|g| g.kind == "unexplored"));
        assert!(matches!(
            exploration_state_of(&m.termination),
            ExplorationState::PartiallyEnumerated { .. }
        ));
    }

    /// 다음 포인터가 없는데 공시 건수에 못 미치면 실제 정지 — 남은 것은 미탐색이다.
    #[test]
    fn stall_before_advertised_total_is_unexplored() {
        let mut ff = FixtureFetch::new();
        allow_all_robots(&mut ff, "h.fixture");
        ff.add_json(
            "https://h.fixture/api?c=first",
            200,
            r#"{"items":[{"id":"a"}],"total":5,"next":null}"#,
        );
        let mut gate = RobotsGate::new(86_400);
        let mut en = Enumerator {
            fetch: &ff,
            gate: &mut gate,
            clock: &clock,
            page_cap_bytes: adapters::LIST_PAGE_MAX_BYTES,
            rate_policy: "default".into(),
        };
        let mut p = plan("https://h.fixture/api?c={cursor}");
        p.pagination = Pagination::Cursor {
            first_cursor: "first".into(),
        };
        p.parser = ListParser::Json {
            items_path: "items".into(),
            id_field: "id".into(),
            total_field: Some("total".into()),
            next_field: Some("next".into()),
        };
        let m = en.run(&p, &meta());
        assert!(matches!(
            m.termination,
            Termination::Stall {
                unique_items: 1,
                advertised_total: 5,
                ..
            }
        ));
        assert!(m.gaps.iter().any(|g| g.kind == "unexplored"));
    }

    /// 첫 페이지가 빈 목록이면 '성공한 빈 목록'이지 오류가 아니다.
    #[test]
    fn empty_first_page_is_a_successful_empty_list() {
        let mut ff = FixtureFetch::new();
        allow_all_robots(&mut ff, "h.fixture");
        ff.add(
            "https://h.fixture/list?page=1",
            200,
            "<div>등록된 상품이 없습니다</div>",
        );
        let mut gate = RobotsGate::new(86_400);
        let mut en = Enumerator {
            fetch: &ff,
            gate: &mut gate,
            clock: &clock,
            page_cap_bytes: adapters::LIST_PAGE_MAX_BYTES,
            rate_policy: "default".into(),
        };
        let m = en.run(&plan("https://h.fixture/list?page={cursor}"), &meta());
        assert!(m.result.empty_success);
        assert_eq!(
            exploration_state_of(&m.termination),
            ExplorationState::EnumeratedEmpty
        );
        // fetch 실패한 것과 구분된다: 페이지 기록은 200, 항목 0.
        assert_eq!(m.pages[0].http_status, 200);
    }

    /// 페이지 상한에 닿으면 나머지는 미탐색으로 기록된다.
    #[test]
    fn max_pages_records_unexplored_tail() {
        let mut ff = FixtureFetch::new();
        allow_all_robots(&mut ff, "h.fixture");
        for i in 1..=3 {
            ff.add(
                &format!("https://h.fixture/list?page={i}"),
                200,
                &format!("<a href='item.do?id={i}'>a</a>"),
            );
        }
        let mut gate = RobotsGate::new(86_400);
        let mut en = Enumerator {
            fetch: &ff,
            gate: &mut gate,
            clock: &clock,
            page_cap_bytes: adapters::LIST_PAGE_MAX_BYTES,
            rate_policy: "default".into(),
        };
        let mut p = plan("https://h.fixture/list?page={cursor}");
        p.max_pages = 3;
        let m = en.run(&p, &meta());
        assert!(matches!(m.termination, Termination::MaxPagesReached { .. }));
        assert!(m.gaps.iter().any(|g| g.kind == "unexplored"));
    }

    // ---------- manifest persistence ----------

    static NEXT: AtomicU64 = AtomicU64::new(0);

    fn temp_store() -> (PathBuf, onjeon_collect::LocalStore) {
        let path = std::env::temp_dir().join(format!(
            "adapters-fixture-only-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        std::fs::create_dir_all(&path).unwrap();
        (path.clone(), onjeon_collect::LocalStore::new(path))
    }

    /// DiscoveryManifest는 write-once로 저장되고 다시 열람할 수 있다.
    #[test]
    fn manifest_is_stored_write_once() {
        let (dir, st) = temp_store();
        let m = unenumerated_manifest(
            scope(),
            "scope=fixture_list",
            "https://h.fixture/list",
            &meta(),
            "entrypoint_unverified",
            "2026-10-20T00:00:00Z",
        );
        let (key, outcome) = adapters::record_manifest(&st, &m).unwrap();
        assert!(key.starts_with("manifests/discovery/fixture_src/"));
        let (key2, outcome2) = adapters::record_manifest(&st, &m).unwrap();
        assert_eq!(key, key2);
        assert_eq!(outcome, onjeon_collect::PutOutcome::Stored);
        assert_eq!(outcome2, onjeon_collect::PutOutcome::AlreadyPresent);
        let stored: serde_json::Value = serde_json::from_slice(&st.get(&key).unwrap()).unwrap();
        assert_eq!(stored["kind"], "discovery_manifest");
        assert_eq!(stored["termination"]["kind"], "entrypoint_unverified");
        assert_eq!(stored["gaps"][0]["kind"], "unexplored");
        std::fs::remove_dir_all(dir).unwrap();
    }

    // ---------- institution adapters ----------

    /// 협회 어댑터는 관측된 진입점만 계획하고 알려진 한계를 선언한다. KLIA 공시실의
    /// robots(관측상 Disallow:/)는 차단으로 기록되지 우회되지 않는다.
    #[test]
    fn association_adapter_records_robots_block() {
        let mut ff = FixtureFetch::new();
        ff.add(
            "https://pub.insure.or.kr/robots.txt",
            200,
            "User-agent: *\nDisallow: /\n",
        );
        let mut gate = RobotsGate::new(86_400);
        let denom =
            adapters::denominator_from_rows(vec![fixture_row("ins-a")], vec![], vec![]).unwrap();
        let adapter = klia();
        let plans = adapter.plans(&denom.in_scope[0]);
        assert!(!plans.is_empty());
        let mut en = Enumerator {
            fetch: &ff,
            gate: &mut gate,
            clock: &clock,
            page_cap_bytes: adapters::LIST_PAGE_MAX_BYTES,
            rate_policy: "default".into(),
        };
        let m = en.run(&plans[0], &meta());
        assert!(matches!(m.termination, Termination::RobotsBlocked { .. }));
        assert!(adapter
            .manifest()
            .known_limitations
            .iter()
            .any(|l| l.contains("Disallow")));
    }

    /// 보험사 어댑터는 registry가 검증한 진입점만 열거한다. disclosure_status가 archived가
    /// 아니면 계획을 만들지 않고 기록된 사유를 진행표로 넘긴다.
    #[test]
    fn insurer_adapter_only_plans_verified_entrypoints() {
        let mut row = fixture_row("ins-a");
        row.insert(
            "disclosure_url".into(),
            "https://co.fixture/disc/list.do".into(),
        );
        row.insert("disclosure_access".into(), "reachable".into());
        row.insert("disclosure_status".into(), "archived".into());
        let denom = adapters::denominator_from_rows(vec![row], vec![], vec![]).unwrap();
        let adapter = InsurerAdapter::for_entry(&denom.in_scope[0]);
        assert_eq!(adapter.plans(&denom.in_scope[0]).len(), 1);

        let mut row = fixture_row("ins-b");
        row.insert("disclosure_access".into(), "js_shell".into());
        row.insert("disclosure_status".into(), "failed".into());
        row.insert(
            "disclosure_gap_reason".into(),
            "정적 HTML에서 공시실 진입점을 찾지 못함".into(),
        );
        row.insert("product_list_status".into(), "unqueried".into());
        let denom = adapters::denominator_from_rows(vec![row], vec![], vec![]).unwrap();
        let adapter = InsurerAdapter::for_entry(&denom.in_scope[0]);
        assert!(adapter.plans(&denom.in_scope[0]).is_empty());
        let states = adapter.preflight_states();
        let disclosure = states
            .iter()
            .find(|(a, _)| a == "disclosure_entry")
            .map(|(_, s)| s)
            .unwrap();
        assert!(matches!(disclosure, ExplorationState::Failed { .. }));
    }

    /// AssociationPlan으로 설정된 어댑터는 manifest의 허용 호스트·진입점을 그대로 드러낸다.
    #[test]
    fn association_adapter_manifest_is_honest_config() {
        let adapter = klia();
        let m = adapter.manifest();
        assert_eq!(m.source_id, "klia_pub");
        assert!(m
            .inventory_entrypoints
            .iter()
            .all(|e| e.starts_with("https://")));
        assert!(m.allowed_hosts.iter().all(|h| !h.is_empty()));
        let _ = AssociationPlan {
            axis: "documents",
            query_signature: "q".into(),
            entrypoint: "https://x".into(),
            pagination: Pagination::SinglePage,
            parser: ListParser::HtmlLinks {
                link_substring: String::new(),
                id_query_key: String::new(),
                total_marker: None,
            },
            doc_roles: vec![],
            max_pages: 1,
        };
        let _ = HostAccess::NotChecked;
    }
}
