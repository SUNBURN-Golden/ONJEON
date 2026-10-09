# 상태 어휘 (생성 문서)

버전 1.1.0 | 2026-10-09 | 정본: `packages/schemas/vocabulary.json`

> 이 문서는 `python3 tools/vocab_check.py --write`로 생성한다. 직접 고치지 않는다.

## 규칙

- 축(axis)이 다른 상태를 한 값에 섞지 않는다. 값 상태·검수 상태·기능 자격·화면 상태·초안 상태는 서로 다른 축이다.
- 저장값은 소문자 snake_case ASCII다. 화면 문구는 이 파일의 screen_ko만 쓴다.
- deprecated_aliases는 과거 문서 표기다. 계약 문서와 코드에서 쓰지 않는다(tools/vocab_check.py가 검사).
- 알 수 없는 값은 성공으로 처리하지 않는다. 역직렬화 실패로 다룬다.
- 새 값은 이 파일에 먼저 추가하고 docs/blueprint/VOCABULARY.md를 다시 생성한다.

## 축 목록

| 축 | 이름 | 적용 대상 | 계층 |
|---|---|---|---|
| `acquisition_status` | 수집 상태 | ExpectedDocument, ExpectedPrice, DiscoveryManifest 항목 | L0-L1 |
| `entity_evidence` | 기관 존재 근거 | 수집 대상 목록의 보험사·공제 기관 행 | L0 |
| `host_access` | 호스트 접근 결과 | 출처·홈페이지·공시 페이지 요청 | L0-L1 |
| `pipeline_stage` | 처리 단계 | 보관된 문서와 그 파생물 | L1-L7 |
| `pipeline_block` | 처리 차단 | 처리 단계와 함께 기록 | L1-L7 |
| `value_state` | 필드 값 상태 | FieldAssertion, PremiumObservation의 각 값 | L3-L5 |
| `review_status` | 검수 상태 | FieldAssertion, PremiumObservation, Rule | L4 |
| `hold_reason` | 보류 사유 | review_status=hold 또는 pipeline_block=hold | L2-L7 |
| `capability` | 기능 자격 | 담보 발생본(및 필드 묶음) | L5-L8 |
| `capability_state` | 기능 자격 상태 | (대상, capability) 쌍 | L5-L8 |
| `display_status` | 화면 데이터 상태 | 화면에 나가는 필드·문장·칸 | L8-L9 |
| `plan_action` | 초안 행동 | 보완안 초안의 담보 그룹 행(사용자가 정함) | L8-L9 |
| `row_label` | 행 라벨 | 내 설계 담보 행의 우측 라벨(파생) | L8-L9 |
| `tri` | 3값 | 규칙 엔진의 조건 | L6 |
| `payout` | 지급 판정 | EvaluationResult | L6-L8 |
| `amount_kind` | 금액 형태 | EvaluationResult의 금액 | L6-L8 |
| `price_basis` | 가격 근거 | PremiumObservation | L3-L9 |
| `price_unavailable_reason` | 가격 미확인 사유 | 비교 기준 안에서 가격이 없을 때 | L5-L9 |
| `freshness` | 최신성 | 소스, 가격, 릴리스 | L0-L9 |
| `policy_holdings_status` | 가입내역 상태 | 프로필 | 개인 영역, L8 |
| `contract_version_match` | 계약 버전 매칭 | PersonalPolicy와 ProductVersion의 연결 | 개인 영역, L5 |
| `sensitivity` | 민감도 | 모든 데이터와 파생물 | 전 계층 |
| `criticality` | 중요도 | 필드·규칙 | L4 |
| `diff_group` | 차이 묶음 | 두 안 비교 | L8-L9 |
| `diff_type` | 차이 유형 | 두 안 비교의 항목 | L8-L9 |
| `doc_role` | 문서 역할 | RawAsset, ExpectedDocument | L0-L2 |
| `sale_status` | 판매 상태 | ProductVersion | L0, L5 |
| `publication_state` | 규칙 공개 상태 | Rule | L6-L7 |

## `acquisition_status` 수집 상태

분모의 한 항목을 확보했는가, 못 했다면 왜인가

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `unqueried` | 아직 조회하지 않음 | 아직 확인하지 않았어요 | - |
| `blocked` | 소스가 접근을 막음(인증·차단·요청 제한). 우회하지 않음 | 접근이 막혀 있어요 | - |
| `failed` | 시도했으나 오류로 실패(재시도 상한 도달 포함) | 가져오지 못했어요 | - |
| `not_found` | 조회 증거가 있으나 해당 항목이 없음 | 찾지 못했어요 | - |
| `not_disclosed` | 소스가 공개하지 않는다는 근거가 있음 | 공개되지 않았어요 | - |
| `archived` | 원문을 받아 무결성 검사 후 불변 보관함 | 원문 확보 | fetched, integrity_checked |

## `entity_evidence` 기관 존재 근거

이 기관이 대상이라는 근거가 몇 개의 서로 다른 기관 출처에서 나왔는가(같은 기관의 여러 페이지는 하나로 셈)

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `two_or_more_sources` | 서로 다른 기관 출처 2곳 이상 | (화면에 직접 표시 안 함) | verified_2_sources |
| `one_source` | 기관 출처 1곳 | (화면에 직접 표시 안 함) | verified_1_source |
| `seed` | 가져온 페이지에 없음. 기억 기반 후보로 분모에 넣지 않음 | (화면에 직접 표시 안 함) | unverified_seed |

## `host_access` 호스트 접근 결과

이 환경에서 요청했을 때의 결과. acquisition_status로 요약된다(대응은 maps_to)

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 | 수집 상태로 |
|---|---|---|---|---|
| `not_checked` | 요청하지 않음 | (화면에 직접 표시 안 함) | - | `unqueried` |
| `reachable` | 정상 응답, 내용 확인 | (화면에 직접 표시 안 함) | - | `archived` |
| `js_shell` | 정상 응답이지만 JS 로더뿐이라 정적 수집 불가 | (화면에 직접 표시 안 함) | 200_js_shell | `failed` |
| `geo_blocked` | 해외 IP 차단 안내 | (화면에 직접 표시 안 함) | 200_geoblock_notice | `blocked` |
| `service_outage` | 점검·장애 안내 | (화면에 직접 표시 안 함) | 200_service_outage_notice | `failed` |
| `origin_denied` | 원 서버가 403 등으로 거부 | (화면에 직접 표시 안 함) | 403_origin | `blocked` |
| `rate_limited` | 요청 제한(429) | (화면에 직접 표시 안 함) | 429_rate_limited | `blocked` |
| `connection_reset` | 연결이 끊김 | (화면에 직접 표시 안 함) | - | `failed` |
| `tls_error` | TLS 실패(구식 재협상 등). 검증을 끄지 않음 | (화면에 직접 표시 안 함) | ssl_legacy_renegotiation, tls_handshake_fail | `failed` |
| `timeout` | 시간 초과 | (화면에 직접 표시 안 함) | - | `failed` |
| `empty_reply` | 빈 응답 | (화면에 직접 표시 안 함) | - | `failed` |
| `redirect_loop` | 리다이렉트 순환 | (화면에 직접 표시 안 함) | - | `failed` |
| `proxy_error` | 경유 프록시가 연결하지 못함(502 등) | (화면에 직접 표시 안 함) | proxy_502 | `failed` |

## `pipeline_stage` 처리 단계

마지막으로 완료한 처리 단계. 보류·실패는 pipeline_block 축

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `discovered` | 목록에서 발견함 | (화면에 직접 표시 안 함) | - |
| `archived` | 원문 불변 보관 | (화면에 직접 표시 안 함) | fetched, integrity_checked |
| `parsed` | 구조 복원(페이지·좌표·표) | (화면에 직접 표시 안 함) | - |
| `labeled` | 필드·관계 추출, 참조 해결 포함 | (화면에 직접 표시 안 함) | references_resolved |
| `validated` | AI 검수와 코드 검사 통과 | (화면에 직접 표시 안 함) | - |
| `compiled` | 실행 규칙과 설명 템플릿 생성 | (화면에 직접 표시 안 함) | - |
| `candidate` | 후보 릴리스에 포함, 그림자 비교 중 | (화면에 직접 표시 안 함) | - |
| `released` | 불변 공개 릴리스에 포함 | (화면에 직접 표시 안 함) | - |

## `pipeline_block` 처리 차단

다음 단계로 못 가는 이유

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `none` | 차단 없음 | (화면에 직접 표시 안 함) | - |
| `hold` | 판단 보류(충돌·반례·검사 실패). 근거가 해소되면 재개 | 판단 보류 | quarantined |
| `failed` | 처리 오류. 원인 수정 후 재처리 | 처리 실패 | - |

## `value_state` 필드 값 상태

이 값에 대해 무엇을 알고 있는가. 검수 여부는 review_status 축

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `observed` | 원문에서 직접 읽음 | (화면에 직접 표시 안 함) | verified |
| `derived` | 확인된 다른 값에서 정해진 규칙으로 계산 | (화면에 직접 표시 안 함) | - |
| `not_found` | 조사 범위에서 아직 찾지 못함 | 자료 필요 | unresolved, missing |
| `unreadable` | 원문은 있으나 판독 실패 | 읽지 못했어요 | - |
| `conflicting` | 근거끼리 충돌 | 근거가 서로 달라요 | conflict |
| `not_applicable` | 확인된 근거로 적용 대상이 아님 | 해당 없음 | - |
| `not_disclosed` | 공개되지 않는다는 근거가 있음 | 공개되지 않았어요 | - |

## `review_status` 검수 상태

AI 검수 결과(ADR-0006). 사람 검수 아님

과거 필드 이름: `validation_status` → `review_status`

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `pending` | 검수 대기 | 확인 중 | pending_review |
| `accepted` | AI 승인 정책 통과 | AI 검증 | verified |
| `hold` | 보류(에이전트 불일치·반례·코드 검사 실패·참조 미해결) | 판단 보류 | conflict, quarantined |
| `rejected` | 근거 없음 등으로 기각. 재추출 필요 | (화면에 직접 표시 안 함) | - |

## `hold_reason` 보류 사유

왜 보류했는가

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `agent_disagreement` | 다른 계열 에이전트끼리 불일치 | 판단 보류 | - |
| `counterexample` | 레드팀이 반례를 찾음 | 판단 보류 | - |
| `quote_mismatch` | 정확 인용이 원문 위치와 다름 | 판단 보류 | - |
| `code_check_failed` | 타입·단위·경계값 등 코드 검사 실패 | 판단 보류 | - |
| `reference_unresolved` | 필수 별표·정의·참조를 못 찾음 | 판단 보류 | - |
| `conflicting_sources` | 약관·요약서 등 근거 간 충돌 | 근거가 서로 달라요 | - |
| `circuit_breaker` | 오류 신고·재추출 불일치 임계 초과로 자동 중단 | 판단 보류 | - |

## `capability` 기능 자격

무엇을 해도 되는가. 각 기능은 독립이며 하나가 다른 것을 자동으로 켜지 않는다(ADR-0012)

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `search` | 원문 검색·열람 | 원문 보기 | indexed, indexed_only |
| `explain` | 검증된 필드로 쉬운 설명 | (화면에 직접 표시 안 함) | explained, explanation_enabled |
| `compare_conditions` | 같은 비교축으로 조건 비교 | 조건 비교 가능 | comparable, comparison_enabled |
| `compare_price` | 같은 비교 기준으로 가격 비교 | 가격 비교 가능 | - |
| `simulate` | 규칙 엔진으로 상황 계산 | 가정 계산 가능 | simulatable, simulation_enabled, scenario_ready |
| `quote` | 개인 견적(스켈레톤) | (화면에 직접 표시 안 함) | quotable, quote_verified |

## `capability_state` 기능 자격 상태

켜졌는가. 꺼졌으면 막은 이유를 함께 저장

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `enabled` | 필요한 필드·근거·검수가 갖춰짐 | (화면에 직접 표시 안 함) | - |
| `blocked` | 필요한 것이 빠졌거나 보류. 사유 목록을 함께 저장 | (화면에 직접 표시 안 함) | - |

## `display_status` 화면 데이터 상태

value_state·review_status·사용자 입력에서 서버가 계산하는 표시 상태. 저장하지 않고 파생한다

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `confirmed` | 값이 observed/derived이고 review_status=accepted | 조건 확인됨 | - |
| `input_missing` | 판단에 필요한 사용자 입력이 없음 | 입력 필요 | confirm_input |
| `data_missing` | 원문·계약의 필수 근거가 없음. 0원 아님 | 자료 필요 | unverified |
| `under_review` | 검수 대기 중 | 확인 중 | - |
| `hold` | 보류 | 판단 보류 | - |
| `not_applicable` | 확인된 조건상 해당 없음 | 해당 없음 | - |

## `plan_action` 초안 행동

사용자가 이 초안에서 무엇을 하려는가. AI가 정답으로 지정하지 않는다

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `keep` | 이번 초안에서 변경하지 않음 | 유지 | - |
| `add` | 사용자가 고른 추가 후보 | 추가 검토 | add_review, review_add |
| `remove` | 사용자가 고른 제외 후보 | 제외 검토 | review_reduce |
| `modify` | 사용자가 고른 금액·구성 변경 후보 | 변경 검토 | - |

## `row_label` 행 라벨

미해결 항목(input_missing·data_missing·hold)이 있으면 needs_condition, 없으면 plan_action 문구

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `needs_condition` | 해결할 질문이 있음. 저장값이 아니라 파생 | 조건 확인 | - |
| `from_plan_action` | plan_action의 screen_ko를 그대로 표시 | (화면에 직접 표시 안 함) | - |

## `tri` 3값

Kleene 3값 논리

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `true` | 참 | (화면에 직접 표시 안 함) | - |
| `false` | 거짓 | (화면에 직접 표시 안 함) | - |
| `unknown` | 모름. 0이나 거짓으로 바꾸지 않음 | (화면에 직접 표시 안 함) | - |

## `payout` 지급 판정

규칙을 입력 가정에 적용한 결과. 보험사 지급 결정이 아님

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `not_payable` | 확인된 조건상 지급 대상 아님 | 이 조건에서는 지급 대상이 아니에요 | - |
| `payable` | 지급 조건 충족(금액은 amount_kind) | 이 조건에서 지급 대상이에요 | - |
| `undetermined` | 필요한 사실이 없어 판단 불가 | 판단에 필요한 정보가 부족해요 | - |

## `amount_kind` 금액 형태

금액이 하나인가, 범위인가, 모르는가

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `exact` | 단일 금액 | (화면에 직접 표시 안 함) | - |
| `range` | 반올림 미지정 등으로 하한~상한 | (화면에 직접 표시 안 함) | - |
| `unknown` | 금액을 정할 수 없음 | 금액 확인 필요 | - |

## `price_basis` 가격 근거

이 가격이 어떤 종류의 근거인가. 신뢰 순위가 아니다

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `illustrative` | 공시된 명시 조건의 예시 보험료 | 공시 예시 | public_disclosed |
| `table_derived` | 공개 요율·산식을 모두 확보해 재현 | 요율표 재현 | - |
| `contract_observed` | 가입내역 PDF에서 확인한 내 계약 납입액 | 내 계약 납입액 | contract_actual |
| `quoted` | 개인 견적(스켈레톤) | 내 견적 | personal_quote |

쓰지 않는 값: estimated, estimated_range

## `price_unavailable_reason` 가격 미확인 사유

가격을 보여줄 수 없는 이유. 0원·예산 초과로 바꾸지 않는다

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `unqueried` | 아직 조회하지 않음 | 가격 미확인 · 아직 확인 전 | - |
| `blocked` | 소스 접근 차단 | 가격 미확인 · 접근 막힘 | - |
| `failed` | 수집 실패 | 가격 미확인 · 가져오지 못함 | - |
| `not_found` | 찾지 못함 | 가격 미확인 · 찾지 못함 | - |
| `not_disclosed` | 공개되지 않는다는 근거 있음 | 가격 미확인 · 공개되지 않음 | - |
| `unreadable` | 판독 실패 | 가격 미확인 · 읽지 못함 | - |
| `conflicting` | 근거 충돌 | 가격 미확인 · 근거 충돌 | conflict |
| `under_review` | 검수 대기 | 가격 미확인 · 확인 중 | pending_review |
| `hold` | 보류 | 가격 미확인 · 판단 보류 | - |
| `condition_mismatch` | 공개된 조건이 비교 기준과 달라 적용 불가 | 가격 미확인 · 조건이 달라요 | - |

## `freshness` 최신성

정책 기한 안에 다시 확인했는가. 값의 존재와 별개 축

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `fresh` | 기한 안에 확인 | (화면에 직접 표시 안 함) | - |
| `stale` | 기한을 넘김. 마지막 검증값을 유지하고 경고 | 확인일이 오래됐어요 | - |

## `policy_holdings_status` 가입내역 상태

이 프로필의 기존 계약을 얼마나 알고 있는가

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `confirmed` | PDF를 올리고 사용자가 추출 내용을 확인함 | 확인된 가입내역 | uploaded |
| `pending_confirmation` | PDF를 올렸으나 확인 전. 계산에 쓰지 않음 | 확인 전 | unconfirmed |
| `none_declared` | 사용자가 '보험 없음'이라고 답함 | 보험 없음(본인 답변) | none |
| `unknown` | 모름(대신 보는 경우 흔함). 0으로 보지 않음 | 아직 모름 | - |
| `skipped` | 지금은 안 올림 | 아직 안 올렸어요 | - |

## `contract_version_match` 계약 버전 매칭

내 계약이 어느 상품 버전인지

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `matched` | 하나로 확정 | (화면에 직접 표시 안 함) | - |
| `ambiguous` | 후보가 여럿. 개인 계산 차단 | 상품 버전 확인 필요 | - |
| `unmatched` | 분모에 없음. 분모 누락 신호 | 아직 수집하지 않은 상품이에요 | - |

## `sensitivity` 민감도

저장·권한·로그 경계. 파생물로 상속된다

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `public_product` | 공시 상품 데이터 | (화면에 직접 표시 안 함) | - |
| `private_policy` | 사용자 계약 정보 | (화면에 직접 표시 안 함) | - |
| `private_health` | 건강·가족력 | (화면에 직접 표시 안 함) | - |
| `genetic_private` | DNA와 그 파생정보. 보험사·설계사 전달 금지 | (화면에 직접 표시 안 함) | - |

## `criticality` 중요도

결과를 바꾸면 c0로 승격

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `c0` | 지급 여부·금액·기산점·면책·감액·정의·한도·상품 버전·가격 조건 | (화면에 직접 표시 안 함) | C0 |
| `c1` | 관계·갱신 등 | (화면에 직접 표시 안 함) | C1 |
| `c2` | 검색 태그·서식 | (화면에 직접 표시 안 함) | C2 |

## `diff_group` 차이 묶음

네 묶음은 같은 시각 비중으로 보인다

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `added` | 새로 생기거나 늘어나는 것 | 추가되는 것 | - |
| `reduced` | 사라지거나 줄거나 새로 붙는 제한 | 줄어드는 것 | - |
| `unchanged` | 그대로인 것 | 그대로인 것 | - |
| `cost_and_unknown` | 비용 차이와 미확인 | 비용과 미확인 | - |

## `diff_type` 차이 유형

각 유형은 하나의 diff_group에 속한다(group 필드)

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 | 묶음 |
|---|---|---|---|---|
| `gain_coverage` | 새로 생기는 보장 | (화면에 직접 표시 안 함) | - | `added` |
| `gain_amount` | 금액 증가 | (화면에 직접 표시 안 함) | - | `added` |
| `lose_coverage` | 사라지는 보장 | (화면에 직접 표시 안 함) | - | `reduced` |
| `lose_amount` | 금액 감소 | (화면에 직접 표시 안 함) | - | `reduced` |
| `new_waiting` | 면책기간 새로 시작·재시작 | (화면에 직접 표시 안 함) | - | `reduced` |
| `new_reduction` | 감액기간·감액률 적용 | (화면에 직접 표시 안 함) | - | `reduced` |
| `new_exclusion` | 새 제외 조건 | (화면에 직접 표시 안 함) | - | `reduced` |
| `term_change` | 보장 종료가 앞당겨짐 | (화면에 직접 표시 안 함) | - | `reduced` |
| `limit_change` | 한도·횟수 축소 | (화면에 직접 표시 안 함) | - | `reduced` |
| `surrender_loss` | 해지 시 환급금 손실 | (화면에 직접 표시 안 함) | - | `reduced` |
| `unchanged` | 변하지 않는 보장·조건 | (화면에 직접 표시 안 함) | - | `unchanged` |
| `renewal_change` | 갱신 구조 변화, 갱신 시 보험료 변동 가능 | (화면에 직접 표시 안 함) | - | `cost_and_unknown` |
| `price_basis_diff` | 가격 기준이 달라 절감액 계산 불가 | (화면에 직접 표시 안 함) | - | `cost_and_unknown` |
| `underwriting_unknown` | 인수 심사에 따라 달라질 수 있음 | (화면에 직접 표시 안 함) | - | `cost_and_unknown` |
| `unknown` | 원문·가격 미확인 | (화면에 직접 표시 안 함) | - | `cost_and_unknown` |

## `doc_role` 문서 역할

이 문서가 무엇인가

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `terms` | 보통약관·주계약 약관 | 약관 | official_terms |
| `rider_terms` | 특약 약관 | 특약 약관 | - |
| `annex` | 별표·부표(질병분류표·수술분류표 등) | 별표 | - |
| `business_method` | 사업방법서 | 사업방법서 | - |
| `summary` | 상품요약서 | 상품요약서 | - |
| `price_table` | 보험료 예시표·보험료표 | 보험료표 | price_example |
| `standard_terms` | 감독규정의 표준약관 | 표준약관 | - |
| `disclosure_page` | 공시 웹페이지 | 공시 페이지 | - |
| `notice` | 개정·판매중지 공지 | 공지 | - |

## `sale_status` 판매 상태

판매 중인가

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `on_sale` | 판매 중 | 판매 중 | - |
| `discontinued` | 판매 중지(기존 계약 해석에 필요) | 판매 중지 | - |
| `unknown` | 판매 상태 미확인 | 판매 상태 미확인 | - |

## `publication_state` 규칙 공개 상태

합성 픽스처와 실제 규칙을 구분

| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |
|---|---|---|---|
| `fixture_only` | 합성 규칙. 근거·릴리스 없이 허용 | (화면에 직접 표시 안 함) | - |
| `candidate` | 후보 릴리스 | (화면에 직접 표시 안 함) | - |
| `released` | 공개 릴리스 | (화면에 직접 표시 안 함) | published |

## 시각 필드

| 필드 | 개념 | 폐기된 표기 |
|---|---|---|
| `source_published_at` | 소스가 밝힌 게시 시각 | - |
| `source_as_of` | 소스가 밝힌 기준일(가격 등) | - |
| `observed_at` | 우리가 관측한 시각 | seen_at, fetched_at |
| `effective_from` | 적용 시작(valid time) | valid_from |
| `effective_to` | 적용 종료(valid time) | valid_to |
| `recorded_at` | 시스템이 알게 된 시각 | - |
| `released_at` | 릴리스 공개 시각 | - |
