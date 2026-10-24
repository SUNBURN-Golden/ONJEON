//! Adapter (denominator enumeration) tests for T-DT-04. All inputs are synthetic
//! `fixture_only` data — no real disclosure site is contacted (O17), and every fixture
//! transport carries the `origin=fixture` marker in spirit (fixture-only code paths).

mod adapters {
    use std::collections::{BTreeMap, VecDeque};
    use std::path::PathBuf;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::sync::Mutex;

    use onjeon_collect::adapters::manifest::ScopeDesc;
    use onjeon_collect::adapters::{
        self, company_doc_roles, exploration_state_of, klia, knia, parse_page,
        unenumerated_manifest, AcquisitionEvidence, AssociationPlan, DenominatorItem,
        DiscoveryAdapter, Enumerator, ExplorationState, Fetch, FetchError, FetchResponse,
        InsurerAdapter, ListParser, ListPlan, Pagination, ProgressTable, RobotsGate, RobotsVerdict,
        RunMeta, Termination,
    };
    use onjeon_collect::Store;
    use onjeon_contracts::{AcquisitionStatus, DocRole, HostAccess};

    // ---------- fixture transport ----------

    /// A `Fetch` that answers from a URL→response map (or a queue for repeated URLs) and
    /// records every requested URL. Missing URLs answer `FetchError::Network`.
    struct FixtureFetch {
        responses: BTreeMap<String, FixtureResponse>,
        sequences: Mutex<BTreeMap<String, VecDeque<FixtureResponse>>>,
        requested: Mutex<Vec<String>>,
    }

    #[derive(Clone)]
    enum FixtureResponse {
        Ok {
            status: u16,
            headers: Vec<(String, String)>,
            body: Vec<u8>,
            truncated: bool,
        },
        Err(FetchError),
    }

    impl FixtureFetch {
        fn new() -> Self {
            Self {
                responses: BTreeMap::new(),
                sequences: Mutex::new(BTreeMap::new()),
                requested: Mutex::new(Vec::new()),
            }
        }
        fn add(&mut self, url: &str, status: u16, body: &str) {
            self.add_full(
                url,
                status,
                vec![("content-type".into(), "text/html".into())],
                body.as_bytes(),
                false,
            );
        }
        fn add_json(&mut self, url: &str, status: u16, body: &str) {
            self.add_full(
                url,
                status,
                vec![("content-type".into(), "application/json".into())],
                body.as_bytes(),
                false,
            );
        }
        /// A response that hit the transport's byte cap (`truncated`), or one with
        /// caller-chosen headers (e.g. none — a transport that returns no Content-Type).
        fn add_full(
            &mut self,
            url: &str,
            status: u16,
            headers: Vec<(String, String)>,
            body: &[u8],
            truncated: bool,
        ) {
            self.responses.insert(
                url.into(),
                FixtureResponse::Ok {
                    status,
                    headers,
                    body: body.to_vec(),
                    truncated,
                },
            );
        }
        fn add_err(&mut self, url: &str, e: FetchError) {
            self.responses.insert(url.into(), FixtureResponse::Err(e));
        }
        /// Queue different responses for repeated requests to the same URL (e.g. a
        /// robots.txt that turns unreachable mid-walk).
        fn add_seq(&mut self, url: &str, seq: Vec<FixtureResponse>) {
            self.sequences
                .lock()
                .unwrap()
                .insert(url.into(), VecDeque::from(seq));
        }
        fn requested(&self) -> Vec<String> {
            self.requested.lock().unwrap().clone()
        }
    }

    impl Fetch for FixtureFetch {
        fn fetch(&self, url: &str, _max_bytes: usize) -> Result<FetchResponse, FetchError> {
            self.requested.lock().unwrap().push(url.to_string());
            if let Some(r) = self
                .sequences
                .lock()
                .unwrap()
                .get_mut(url)
                .and_then(|q| q.pop_front())
            {
                return match r {
                    FixtureResponse::Ok {
                        status,
                        headers,
                        body,
                        truncated,
                    } => Ok(FetchResponse {
                        status,
                        headers,
                        body,
                        truncated,
                    }),
                    FixtureResponse::Err(e) => Err(e),
                };
            }
            match self.responses.get(url) {
                Some(FixtureResponse::Ok {
                    status,
                    headers,
                    body,
                    truncated,
                }) => Ok(FetchResponse {
                    status: *status,
                    headers: headers.clone(),
                    body: body.clone(),
                    truncated: *truncated,
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
                empty_marker: Some("<div class='fixture_only_empty'>No results</div>".into()),
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
        assert_eq!(terms.rate(), None); // institution inventories have not been enumerated
        assert_eq!(
            adapters::coverage(&table.rows[0].items)[&DocRole::Terms].rate(),
            Some(0.0)
        );
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
        // 첫 페이지도 가져오기 전의 차단은 남은 페이지가 아니라 범위 전체다.
        assert_eq!(m.gaps[0].range, "whole_scope");
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

    /// BOM이 붙은 robots.txt도 규칙을 그대로 적용한다(tools/crawler/robots.py의
    /// utf-8-sig 이식). BOM 때문에 첫 `User-agent:` 줄이 필드로 인식되지 않으면
    /// 그룹 전체가 비어 모든 경로가 허용되는 방향은 안 된다 — Disallow:/도 우회다.
    #[test]
    fn robots_utf8_bom_does_not_disarm_disallow() {
        let mut ff = FixtureFetch::new();
        ff.add_full(
            "https://h.fixture/robots.txt",
            200,
            vec![("content-type".into(), "text/plain".into())],
            b"\xEF\xBB\xBFUser-agent: *\nDisallow: /\n",
            false,
        );
        let mut gate = RobotsGate::new(86_400);
        assert!(matches!(
            gate.check(&ff, "https://h.fixture/list", NOW),
            RobotsVerdict::Disallow
        ));
        // BOM 뒤의 Allow 규칙도 살아 있다.
        let mut ff = FixtureFetch::new();
        ff.add_full(
            "https://h.fixture/robots.txt",
            200,
            vec![("content-type".into(), "text/plain".into())],
            b"\xEF\xBB\xBFUser-agent: *\nDisallow: /secret\nAllow: /\n",
            false,
        );
        let mut gate = RobotsGate::new(86_400);
        assert!(matches!(
            gate.check(&ff, "https://h.fixture/open", NOW),
            RobotsVerdict::Allow { .. }
        ));
        assert!(matches!(
            gate.check(&ff, "https://h.fixture/secret/x", NOW),
            RobotsVerdict::Disallow
        ));
    }

    /// CPython `RobotFileParser` 의미론(tools/crawler/robots.py `_group`의 참조): agents에
    /// `*`를 포함한 엔트리는 default 엔트리로, 모든 특정 엔트리 뒤에만 참조된다. 표준
    /// 레이아웃(맨 앞 `User-agent: *` + Allow, 뒤의 특정 Disallow)에서 파일 순서대로 첫
    /// 매치를 취하면 `*`의 Allow가 특정 Disallow를 무력화한다 — 참조 파서가 금지하는
    /// 경로를 가져오는, 안전하지 않은 방향의 우회다.
    #[test]
    fn robots_star_entry_is_default_consulted_after_specific_entries() {
        // `archiver`는 우리 토큰(onjeon-sourcearchiver)의 부분 문자열 — 뒤의 특정
        // 엔트리가 맞고 앞의 `* Allow: /`를 이긴다.
        let mut ff = FixtureFetch::new();
        ff.add(
            "https://h.fixture/robots.txt",
            200,
            "User-agent: *\nAllow: /\n\nUser-agent: archiver\nDisallow: /\n",
        );
        let mut gate = RobotsGate::new(86_400);
        assert!(matches!(
            gate.check(&ff, "https://h.fixture/list", NOW),
            RobotsVerdict::Disallow
        ));

        // 특정 엔트리가 우리 토큰과 맞지 않으면 `*` 엔트리는 여전히 적용된다.
        let mut ff = FixtureFetch::new();
        ff.add(
            "https://h.fixture/robots.txt",
            200,
            "User-agent: *\nDisallow: /private\n\nUser-agent: otherbot\nDisallow: /\n",
        );
        let mut gate = RobotsGate::new(86_400);
        assert!(matches!(
            gate.check(&ff, "https://h.fixture/private/x", NOW),
            RobotsVerdict::Disallow
        ));
        assert!(matches!(
            gate.check(&ff, "https://h.fixture/public/x", NOW),
            RobotsVerdict::Allow { .. }
        ));

        // 첫 `*` 엔트리가 default다 — 파이썬처럼 뒤의 `*` 엔트리는 통째로 버려진다.
        let mut ff = FixtureFetch::new();
        ff.add(
            "https://h.fixture/robots.txt",
            200,
            "User-agent: *\nDisallow: /a\n\nUser-agent: *\nDisallow: /\n",
        );
        let mut gate = RobotsGate::new(86_400);
        assert!(matches!(
            gate.check(&ff, "https://h.fixture/a", NOW),
            RobotsVerdict::Disallow
        ));
        assert!(matches!(
            gate.check(&ff, "https://h.fixture/b", NOW),
            RobotsVerdict::Allow { .. }
        ));
    }

    /// IPv6 호스트의 robots URL은 [::1]:8080 꼴이다 — 포트가 괄호 안에 들어간
    /// [::1:8080]은 다른 호스트로 다시 파싱돼 틀린 요청이 된다.
    #[test]
    fn robots_url_brackets_ipv6_host_before_port() {
        let mut ff = FixtureFetch::new();
        ff.add("http://[::1]:8080/robots.txt", 404, "");
        let mut gate = RobotsGate::new(86_400);
        assert!(matches!(
            gate.check(&ff, "http://[::1]:8080/a", NOW),
            RobotsVerdict::Allow {
                reason: "robots_not_found",
                ..
            }
        ));
        assert_eq!(
            ff.requested(),
            vec!["http://[::1]:8080/robots.txt".to_string()]
        );
    }

    /// 주입 transport가 소켓을 열기 전 거절(Refused)하면 원격 unreachable이 아니라
    /// 우리 쪽 거절(transport_refused)로 기록한다 — 보류·미요청 규칙은 같다.
    #[test]
    fn transport_refused_is_recorded_not_blamed_on_remote() {
        let mut ff = FixtureFetch::new();
        ff.add_err("https://h.fixture/robots.txt", FetchError::Refused);
        let mut gate = RobotsGate::new(86_400);
        assert!(matches!(
            gate.check(&ff, "https://h.fixture/a", NOW),
            RobotsVerdict::Unverifiable {
                reason: "transport_refused"
            }
        ));
        // 같은 UTC 일 안에서는 보류가 유지되고 재요청하지 않는다.
        assert!(matches!(
            gate.check(&ff, "https://h.fixture/b", NOW + 60),
            RobotsVerdict::Unverifiable {
                reason: "transport_refused"
            }
        ));
        assert_eq!(ff.requested().len(), 1);
    }

    /// 열거 도중 robots 재확인이 불가해지면 이미 가져온 페이지는 기록된 채고 보류는
    /// 남은 페이지뿐이다 — 범위를 whole_scope로 과소 신고하지 않는다.
    #[test]
    fn mid_walk_robots_hold_records_remaining_pages() {
        let mut ff = FixtureFetch::new();
        ff.add_seq(
            "https://h.fixture/robots.txt",
            vec![
                FixtureResponse::Ok {
                    status: 200,
                    headers: vec![("content-type".into(), "text/plain".into())],
                    body: b"User-agent: *\nAllow: /\n".to_vec(),
                    truncated: false,
                },
                FixtureResponse::Err(FetchError::Network),
            ],
        );
        ff.add(
            "https://h.fixture/list?page=1",
            200,
            "<a href='item.do?id=1'>a</a>",
        );
        let mut gate = RobotsGate::new(0); // TTL 0 — 매 페이지마다 robots를 다시 확인한다.
        let mut en = Enumerator {
            fetch: &ff,
            gate: &mut gate,
            clock: &clock,
            page_cap_bytes: adapters::LIST_PAGE_MAX_BYTES,
            rate_policy: "default".into(),
        };
        let m = en.run(&plan("https://h.fixture/list?page={cursor}"), &meta());
        assert!(matches!(m.termination, Termination::RobotsHold { .. }));
        assert_eq!(m.pages.len(), 1);
        assert!(m
            .gaps
            .iter()
            .any(|g| g.kind == "hold" && g.range == "remaining_pages"));
        assert!(!m.gaps.iter().any(|g| g.range == "whole_scope"));
    }

    /// 열거 도중 robots가 403으로 돌아서도 차단 범위는 남은 페이지다.
    #[test]
    fn mid_walk_robots_forbidden_records_remaining_pages() {
        let mut ff = FixtureFetch::new();
        ff.add_seq(
            "https://h.fixture/robots.txt",
            vec![
                FixtureResponse::Ok {
                    status: 200,
                    headers: vec![("content-type".into(), "text/plain".into())],
                    body: b"User-agent: *\nAllow: /\n".to_vec(),
                    truncated: false,
                },
                FixtureResponse::Ok {
                    status: 403,
                    headers: vec![],
                    body: Vec::new(),
                    truncated: false,
                },
            ],
        );
        ff.add(
            "https://h.fixture/list?page=1",
            200,
            "<a href='item.do?id=1'>a</a>",
        );
        let mut gate = RobotsGate::new(0);
        let mut en = Enumerator {
            fetch: &ff,
            gate: &mut gate,
            clock: &clock,
            page_cap_bytes: adapters::LIST_PAGE_MAX_BYTES,
            rate_policy: "default".into(),
        };
        let m = en.run(&plan("https://h.fixture/list?page={cursor}"), &meta());
        assert!(matches!(m.termination, Termination::RobotsBlocked { .. }));
        assert_eq!(m.pages.len(), 1);
        assert!(m
            .gaps
            .iter()
            .any(|g| g.kind == "blocked" && g.range == "remaining_pages"));
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

    /// 페이지 번호 열거: 항목이 있는 페이지 뒤의 빈 페이지는 목록의 끝(다음 포인터
    /// 없음)이다 — 빈 목록(EnumeratedEmpty)이 아니라 Enumerated로 끝난다.
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
        ff.add(
            "https://h.fixture/list?page=3",
            200,
            "<div class='fixture_only_empty'>No results</div>",
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
            Termination::NextPointerAbsent { .. }
        ));
        assert!(!m.result.empty_success);
        assert_eq!(
            exploration_state_of(&m.termination),
            ExplorationState::Enumerated
        );
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
            "<div class='fixture_only_empty'>No results</div>",
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
        assert!(adapter.plans(&denom.in_scope[0]).is_empty()); // landing URL alone is not a verified list parser

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
                empty_marker: None,
            },
            doc_roles: vec![],
            max_pages: 1,
        };
        let _ = HostAccess::NotChecked;
    }

    // ---------- an empty page is not blindly a success ----------

    /// {"items":[],"total":5}인 첫 페이지는 '성공한 빈 목록'이 아니다 — 끝점이 5건을
    /// 공시했으니 범위는 미탐색 정지로 남는다 (Masterplan §23.2 건수 일치 확인).
    #[test]
    fn empty_first_page_with_advertised_total_is_unexplored() {
        let mut ff = FixtureFetch::new();
        allow_all_robots(&mut ff, "h.fixture");
        ff.add_json(
            "https://h.fixture/api?p=1",
            200,
            r#"{"items":[],"total":5}"#,
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
        assert!(!m.result.empty_success);
        assert!(matches!(
            m.termination,
            Termination::Stall {
                unique_items: 0,
                advertised_total: 5,
                ..
            }
        ));
        assert!(m.gaps.iter().any(|g| g.kind == "unexplored"));
        assert!(matches!(
            exploration_state_of(&m.termination),
            ExplorationState::PartiallyEnumerated { .. }
        ));
    }

    /// 열거 도중의 빈 페이지도 공시 건수에 못 미치면 정지 — 남은 꼬리는 미탐색이다.
    #[test]
    fn mid_walk_empty_page_before_total_is_unexplored() {
        let mut ff = FixtureFetch::new();
        allow_all_robots(&mut ff, "h.fixture");
        ff.add_json(
            "https://h.fixture/api?p=1",
            200,
            r#"{"items":[{"id":"a"},{"id":"b"}],"total":5}"#,
        );
        ff.add_json(
            "https://h.fixture/api?p=2",
            200,
            r#"{"items":[],"total":5}"#,
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
        assert!(!m.result.empty_success);
        assert!(matches!(
            m.termination,
            Termination::Stall {
                unique_items: 2,
                advertised_total: 5,
                ..
            }
        ));
        assert!(m
            .gaps
            .iter()
            .any(|g| g.kind == "unexplored" && g.reason == "empty_page_before_advertised_total"));
        assert!(matches!(
            exploration_state_of(&m.termination),
            ExplorationState::PartiallyEnumerated { .. }
        ));
    }

    /// 끝점이 다음 포인터를 계속 주면 빈 페이지는 종료 증거가 아니다 — 걸음을 계속한다.
    #[test]
    fn empty_page_with_next_cursor_keeps_walking() {
        let mut ff = FixtureFetch::new();
        allow_all_robots(&mut ff, "h.fixture");
        ff.add_json(
            "https://h.fixture/api?c=c1",
            200,
            r#"{"items":[],"total":1,"next":"c2"}"#,
        );
        ff.add_json(
            "https://h.fixture/api?c=c2",
            200,
            r#"{"items":[{"id":"a"}],"total":1,"next":null}"#,
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
            first_cursor: "c1".into(),
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
            Termination::AdvertisedTotalReached {
                unique_items: 1,
                advertised_total: 1
            }
        ));
        assert_eq!(m.result.unique_item_count, 1);
        assert_eq!(m.pages.len(), 2);
    }

    /// 빈 문자열 next는 '다음 없음'이다 — "" 커서를 따라가지 않는다.
    #[test]
    fn empty_string_next_cursor_is_absent() {
        let mut ff = FixtureFetch::new();
        allow_all_robots(&mut ff, "h.fixture");
        ff.add_json(
            "https://h.fixture/api?c=c1",
            200,
            r#"{"items":[{"id":"a"}],"next":""}"#,
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
            first_cursor: "c1".into(),
        };
        p.parser = ListParser::Json {
            items_path: "items".into(),
            id_field: "id".into(),
            total_field: None,
            next_field: Some("next".into()),
        };
        let m = en.run(&p, &meta());
        assert!(matches!(
            m.termination,
            Termination::NextPointerAbsent { .. }
        ));
        assert_eq!(ff.requested().len(), 2); // robots + page one only
    }

    /// Content-Type이 없고 본문이 마크업도 아니면 목록이 아니다 — '성공한 빈 목록'이
    /// 아니라 not_list_content 실패다.
    #[test]
    fn missing_content_type_binary_body_is_not_a_list() {
        let mut ff = FixtureFetch::new();
        allow_all_robots(&mut ff, "h.fixture");
        ff.add_full(
            "https://h.fixture/list?page=1",
            200,
            vec![],
            b"\x00\x01\x02not a page",
            false,
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
        assert!(matches!(m.termination, Termination::ParseFailed { .. }));
        assert!(!m.result.empty_success);
        assert_eq!(m.result.unique_item_count, 0);
        assert_eq!(m.pages[0].page_kind, "not_list_content");
        assert_eq!(m.gaps[0].reason, "not_list_content");
    }

    /// 목록 URL의 401/403은 접근 거부다 — gap 종류는 failed가 아니라 blocked.
    #[test]
    fn http_403_list_page_records_blocked_gap() {
        let mut ff = FixtureFetch::new();
        allow_all_robots(&mut ff, "h.fixture");
        ff.add("https://h.fixture/list?page=1", 403, "forbidden");
        let mut gate = RobotsGate::new(86_400);
        let mut en = Enumerator {
            fetch: &ff,
            gate: &mut gate,
            clock: &clock,
            page_cap_bytes: adapters::LIST_PAGE_MAX_BYTES,
            rate_policy: "default".into(),
        };
        let m = en.run(&plan("https://h.fixture/list?page={cursor}"), &meta());
        assert!(matches!(m.termination, Termination::FetchFailed { .. }));
        assert_eq!(m.gaps[0].kind, "blocked");
        assert_eq!(m.gaps[0].reason, "access_denied");
    }

    /// href 값은 원문 대소문자를 보존한다: 설정 문자열은 페이지의 실제 대소문자와
    /// 매칭되고 id도 원형으로 남는다 — `coId=Ab12`는 "ab12"로 바뀌지 않고, 대소문자만
    /// 다른 두 항목은 하나로 합쳐지지 않는다.
    #[test]
    fn href_extraction_preserves_value_case() {
        let parsed = parse_page(
            &ListParser::HtmlLinks {
                link_substring: "mngtDis".into(),
                id_query_key: "coId".into(),
                total_marker: None,
                empty_marker: None,
            },
            b"<a href=\"/mngtDis/list.do?coId=Ab12\">x</a><a HREF=\"/mngtDis/list.do?coId=ab12\">y</a>",
        )
        .unwrap();
        assert_eq!(
            parsed.item_ids,
            vec!["Ab12".to_string(), "ab12".to_string()]
        );
    }

    /// data-href·xhref 같은 이름은 href 속성이 아니다 — 항목으로 세지 않는다.
    #[test]
    fn href_extraction_ignores_non_href_attribute_names() {
        let parsed = parse_page(
            &ListParser::HtmlLinks {
                link_substring: String::new(),
                id_query_key: "id".into(),
                total_marker: None,
                empty_marker: None,
            },
            b"<div data-href=\"item.do?id=9\" xhref='item.do?id=8'></div><a href='item.do?id=1'>a</a>",
        )
        .unwrap();
        assert_eq!(parsed.item_ids, vec!["1".to_string()]);
    }

    /// 스크립트 안의 `location.href='…'`는 속성이 아니다 — 항목으로 세지 않는다.
    /// 속성 이름 앞에는 공백(또는 관용적 `/`)만 온다.
    #[test]
    fn href_in_script_text_is_not_counted() {
        let parsed = parse_page(
            &ListParser::HtmlLinks {
                link_substring: String::new(),
                id_query_key: "id".into(),
                total_marker: None,
                empty_marker: None,
            },
            b"<script>location.href='item.do?id=9';window.href='item.do?id=8';</script><a href='item.do?id=1'>a</a>",
        )
        .unwrap();
        assert_eq!(parsed.item_ids, vec!["1".to_string()]);
    }

    /// `&amp;`·`&#38;`로 인코딩된 쿼리 구분자는 실제 HTML 파서가 `&`로 돌려준다.
    /// 디코딩 없이 `&`로만 자르면 두 번째 매개변수의 id 키가 `amp;tptyCode`가 돼 항목이
    /// 조용히 빠진다 — 협회 어댑터 둘 다 id 키를 두 번째 매개변수에 둔다.
    #[test]
    fn entity_encoded_query_separators_do_not_drop_items() {
        let parsed = parse_page(
            &ListParser::HtmlLinks {
                link_substring: "disclosurePopup.do".into(),
                id_query_key: "tptyCode".into(),
                total_marker: None,
                empty_marker: None,
            },
            b"<a href=\"disclosurePopup.do?tabType=1&amp;tptyCode=PB15\">a</a>\
              <a href='disclosurePopup.do?tabType=2&#38;tptyCode=PB16'>b</a>\
              <a href='disclosurePopup.do?tabType=3&amp;tptyCode=PB15'>dup</a>",
        )
        .unwrap();
        // 중복 제거는 디코딩된 id 위에서 일어난다.
        assert_eq!(
            parsed.item_ids,
            vec!["PB15".to_string(), "PB16".to_string()]
        );
    }

    /// 링크가 모두 `&amp;`로 인코딩된 단일 페이지는 0건 '검증된 빈 목록'(EnumeratedEmpty)이
    /// 아니다 — 항목이 실제로 열거된다.
    #[test]
    fn fully_entity_encoded_list_page_is_not_a_fabricated_empty() {
        let mut ff = FixtureFetch::new();
        allow_all_robots(&mut ff, "h.fixture");
        ff.add(
            "https://h.fixture/list",
            200,
            "<a href=\"item.do?x=1&amp;id=1\">a</a><a href=\"item.do?x=2&amp;id=2\">b</a>",
        );
        let mut gate = RobotsGate::new(86_400);
        let mut en = Enumerator {
            fetch: &ff,
            gate: &mut gate,
            clock: &clock,
            page_cap_bytes: adapters::LIST_PAGE_MAX_BYTES,
            rate_policy: "default".into(),
        };
        let mut p = plan("https://h.fixture/list");
        p.pagination = Pagination::SinglePage;
        p.parser = ListParser::HtmlLinks {
            link_substring: "item.do".into(),
            id_query_key: "id".into(),
            total_marker: None,
            empty_marker: None,
        };
        let m = en.run(&p, &meta());
        assert_eq!(m.result.unique_item_count, 2);
        assert!(!m.result.empty_success);
        assert!(matches!(
            m.termination,
            Termination::NextPointerAbsent { .. }
        ));
    }

    /// type = "password"처럼 공백이 있는 속성도 로그인 표지다.
    #[test]
    fn login_detection_tolerates_attribute_spacing() {
        assert!(adapters::looks_like_login(
            b"<form><input type = \"password\" name='pw'></form>"
        ));
        assert!(adapters::looks_like_login(
            b"<form><input type= \"password\"></form>"
        ));
    }

    /// 엔티티로 숨긴 자격 증명 속성도 디코딩 뒤 비교한다 — `type="pass&#119;ord"`와
    /// `action="/auth"`는 로그인 표지이고, 같은 페이지의 목록 링크는 완료 근거가 못 된다.
    #[test]
    fn entity_encoded_login_form_is_blocked_not_enumerated() {
        let mut ff = FixtureFetch::new();
        allow_all_robots(&mut ff, "h.fixture");
        ff.add(
            "https://h.fixture/list",
            200,
            "<html><form action='/auth'><input name='id'><input type=\"pass&#119;ord\"></form>\
             <a href='item.do?id=1'>list</a></html>",
        );
        let mut gate = RobotsGate::new(86_400);
        let mut en = Enumerator {
            fetch: &ff,
            gate: &mut gate,
            clock: &clock,
            page_cap_bytes: adapters::LIST_PAGE_MAX_BYTES,
            rate_policy: "default".into(),
        };
        let mut p = plan("https://h.fixture/list");
        p.pagination = Pagination::SinglePage;
        let m = en.run(&p, &meta());
        assert!(matches!(m.termination, Termination::LoginPage { .. }));
        assert_eq!(m.result.unique_item_count, 0);
        assert!(m.discovered_ids.is_empty());
        assert!(!m.result.empty_success);
        assert_eq!(m.pages[0].page_kind, "login_page");
        assert_eq!(m.gaps[0].kind, "blocked");
        assert_eq!(
            exploration_state_of(&m.termination),
            ExplorationState::Blocked {
                reason: "login_page".into()
            }
        );
    }

    /// 자격 증명 표지는 실제 태그의 엔티티 디코딩·공백 제거·대소문자 무시 값으로 비교한다.
    /// 템플릿 안의 로그인 폼도 로그인 페이지다. 본문 텍스트의 'password'나 검색 폼은 아니다.
    #[test]
    fn login_detection_decodes_credential_attributes() {
        for body in [
            "<form action='/list'><input type=\"pass&#119;ord\"></form>",
            "<form><input type='PASS&#x57;ORD'></form>",
            "<form><input type=' password '></form>",
            "<form><input name='user&#95;pw'></form>",
            "<form><input id='Login_PW'></form>",
            "<form><input autocomplete='current-password'></form>",
            "<form action='/AUTH/login.do'></form>",
            "<form action='&#47;auth'></form>",
            "<template><form><input type='password'></form></template>",
            "<form onsubmit='return doLogin()'></form>",
        ] {
            assert!(adapters::looks_like_login(body.as_bytes()), "{}", body);
        }
        for body in [
            "<html><a href='item.do?id=1'>list</a><p>password 안내</p></html>",
            "<form action='/search'><input type='text' name='q'></form>",
            "<form action='/list'><input type='pass'></form>",
        ] {
            assert!(!adapters::looks_like_login(body.as_bytes()), "{}", body);
        }
    }

    /// 공시 건수 0과 첫 페이지 0건은 검증된 빈 목록이다 — '총건수 도달'이 아니라
    /// EmptyPage·empty_success로 끝나고 EnumeratedEmpty가 된다.
    #[test]
    fn advertised_zero_with_empty_first_page_is_a_verified_empty_list() {
        let mut ff = FixtureFetch::new();
        allow_all_robots(&mut ff, "h.fixture");
        ff.add_json(
            "https://h.fixture/api?p=1",
            200,
            r#"{"items":[],"total":0}"#,
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
        assert!(matches!(m.termination, Termination::EmptyPage { .. }));
        assert!(m.result.empty_success);
        assert_eq!(m.result.advertised_total, Some(0));
        assert_eq!(m.pages.len(), 1);
        assert_eq!(m.pages[0].advertised_total, Some(0));
        assert!(m.gaps.is_empty());
        assert_eq!(
            exploration_state_of(&m.termination),
            ExplorationState::EnumeratedEmpty
        );
    }

    /// 공시 건수 0이어도 끝점이 다음 커서를 주면 빈 페이지는 종료 증거가 아니다 —
    /// 걸음을 계속하고, 0건 총건수는 실제 항목으로 반박된다(빈 목록 성공이 아니다).
    #[test]
    fn advertised_zero_with_next_cursor_keeps_walking() {
        let mut ff = FixtureFetch::new();
        allow_all_robots(&mut ff, "h.fixture");
        ff.add_json(
            "https://h.fixture/api?c=c1",
            200,
            r#"{"items":[],"total":0,"next":"c2"}"#,
        );
        ff.add_json(
            "https://h.fixture/api?c=c2",
            200,
            r#"{"items":[{"id":"a"}],"total":0,"next":null}"#,
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
            first_cursor: "c1".into(),
        };
        p.parser = ListParser::Json {
            items_path: "items".into(),
            id_field: "id".into(),
            total_field: Some("total".into()),
            next_field: Some("next".into()),
        };
        let m = en.run(&p, &meta());
        assert_eq!(m.pages.len(), 2);
        assert!(ff
            .requested()
            .contains(&"https://h.fixture/api?c=c2".to_string()));
        assert!(matches!(
            m.termination,
            Termination::NextPointerAbsent { .. }
        ));
        assert!(!m.result.empty_success);
        assert_eq!(m.result.unique_item_count, 1);
        assert_eq!(
            exploration_state_of(&m.termination),
            ExplorationState::Enumerated
        );
    }

    /// 총건수에 도달했어도 끝점이 다음 커서를 주면 모순이다 — 커서를 따라가고 목록
    /// 자신의 '다음 없음'에서 끝난다. 두 번째 페이지의 항목이 빠지지 않는다.
    #[test]
    fn advertised_total_with_endpoint_next_cursor_is_not_termination() {
        let mut ff = FixtureFetch::new();
        allow_all_robots(&mut ff, "h.fixture");
        ff.add_json(
            "https://h.fixture/api?c=c1",
            200,
            r#"{"items":[{"id":"a"}],"total":1,"next":"c2"}"#,
        );
        ff.add_json(
            "https://h.fixture/api?c=c2",
            200,
            r#"{"items":[{"id":"b"}],"total":1,"next":null}"#,
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
            first_cursor: "c1".into(),
        };
        p.parser = ListParser::Json {
            items_path: "items".into(),
            id_field: "id".into(),
            total_field: Some("total".into()),
            next_field: Some("next".into()),
        };
        let m = en.run(&p, &meta());
        assert_eq!(m.pages.len(), 2);
        assert_eq!(m.result.unique_item_count, 2);
        assert!(matches!(
            m.termination,
            Termination::AdvertisedTotalReached {
                unique_items: 2,
                advertised_total: 1
            }
        ));
        assert_eq!(m.discovered_ids, vec!["a".to_string(), "b".to_string()]);
    }

    /// robots.txt가 잘려도 마지막 불완전 줄은 규칙으로 파싱하지 않는다
    /// (tools/crawler/robots.py `_read_capped` 이식) — 잘린 Allow: 줄이 허용 범위를
    /// 키우는 방향은 안전하지 않다.
    #[test]
    fn truncated_robots_ignores_partial_last_line() {
        let mut ff = FixtureFetch::new();
        // 본문이 "Allow: /p" 중간에서 잘렸다 — 완전한 규칙은 Disallow: / 뿐이다.
        ff.add_full(
            "https://h.fixture/robots.txt",
            200,
            vec![("content-type".into(), "text/plain".into())],
            b"User-agent: *\nDisallow: /\nAllow: /p",
            true,
        );
        let mut gate = RobotsGate::new(86_400);
        assert!(matches!(
            gate.check(&ff, "https://h.fixture/public", NOW),
            RobotsVerdict::Disallow
        ));
    }

    /// 제외 파일의 legacy `status` 열도 알 수 없는 라벨은 실패다 — 기본값으로 삼지
    /// 않는다 (어휘 규칙 4). 빈 값은 기존 호환을 유지한다.
    #[test]
    fn excluded_rows_reject_unknown_legacy_status() {
        let mut row = fixture_row("hist-x");
        row.remove("entity_evidence");
        row.insert("status".into(), "definitely_not_a_label".into());
        assert!(adapters::denominator_from_rows(vec![], vec![], vec![row]).is_err());
        let mut row = fixture_row("hist-y");
        row.remove("entity_evidence");
        row.insert("status".into(), "".into());
        let denom = adapters::denominator_from_rows(vec![], vec![], vec![row]).unwrap();
        assert_eq!(denom.exclusions[0].reason, "historical_or_non_insurer");
    }

    /// KNIA documents 축은 GET·HTML로 재현할 검증된 요청 형태가 없다
    /// (/popup/disclosureList.do는 POST+JS 객체 리터럴로만 관측, B_knia §2) — 계획을
    /// 만들지 않고 한계로 선언한다. 관측된 robots 403(WAF)도 한계로 드러낸다.
    #[test]
    fn knia_documents_axis_is_unexplored_not_planned() {
        let adapter = knia();
        let denom =
            adapters::denominator_from_rows(vec![fixture_row("ins-a")], vec![], vec![]).unwrap();
        let plans = adapter.plans(&denom.in_scope[0]);
        assert!(!plans.is_empty());
        assert!(plans.iter().all(|p| p.scope.axis != "documents"));
        let m = adapter.manifest();
        assert!(m
            .known_limitations
            .iter()
            .any(|l| l.contains("disclosureList.do") && l.contains("POST")));
        assert!(m
            .known_limitations
            .iter()
            .any(|l| l.contains("robots") && l.contains("403")));
    }

    /// InsurerAdapter 계획은 생성자에 묶인 기관 것이다 — 다른 entry를 넘겨도 그 기관
    /// 바깥의 진입점(manifest의 allowed_hosts 밖)을 가리키지 않는다.
    #[test]
    fn insurer_adapter_plan_is_bound_to_its_entry() {
        let mut row_a = fixture_row("life-kyobo-lifeplanet");
        row_a.insert(
            "disclosure_url".into(),
            "https://www.lifeplanet.co.kr/disclosure/good/HPDA01S0.dev".into(),
        );
        row_a.insert("disclosure_access".into(), "reachable".into());
        row_a.insert("disclosure_status".into(), "archived".into());
        let mut row_b = fixture_row("ins-b");
        row_b.insert("disclosure_url".into(), "https://b.fixture/disc".into());
        row_b.insert("disclosure_access".into(), "reachable".into());
        row_b.insert("disclosure_status".into(), "archived".into());
        let denom = adapters::denominator_from_rows(vec![row_a, row_b], vec![], vec![]).unwrap();
        let entry = denom
            .in_scope
            .iter()
            .find(|e| e.row.insurer_id == "life-kyobo-lifeplanet")
            .unwrap();
        let other = denom
            .in_scope
            .iter()
            .find(|e| e.row.insurer_id == "ins-b")
            .unwrap();
        let adapter = InsurerAdapter::for_entry(entry);
        let plans = adapter.plans(other);
        assert_eq!(plans.len(), 8);
        assert!(plans
            .iter()
            .all(|p| p.scope.institution_id == "life-kyobo-lifeplanet"
                && p.entrypoint.starts_with("https://www.lifeplanet.co.kr/")));
    }
}
