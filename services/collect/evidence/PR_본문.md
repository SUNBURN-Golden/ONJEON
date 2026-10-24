## 목적과 설계 연결

- 정보 비대칭(A), 소비자 질문(Q), 계층(L), 불변식(I), 마일스톤(M): A1·A2·A3 / Q2·Q4·Q7 / L0·L1 / I6·I11·I17 / M3.
- 해결하는 소비자 질문: 어떤 기관·상품·판매기간·문서를 발견했고 무엇이 보류·차단·미탐색인가(Q2·Q4·Q7).
- 요구 ID (`docs/blueprint/REQUIREMENTS.md`): R02·R03·R26(직접). R04·R10은 후속 소비 경로 지원이며 완료 주장 아님.
- 관련 결정 ID / ADR: ADR-0018 §3·§4, DATA_PIPELINE_CONTRACT §1·§2·§8, 조사 H1~H14, 09 P01·P02, D-04·O17 관문.
- 설계 변경인가, 기존 설계 구현인가: 기존 설계 구현(T-DT-04, fix round 4). 범위·접근 정책 변경 없음.

## 변경 내용

- 데이터·스키마·라벨·규칙·API 영향: 없음. 공유 스키마·어휘·가격 계산·규칙 결과·개인정보 경로를 바꾸지 않는다. 변경은 `services/collect/**` 안이다.
- 화면에서 보장·제외·가격·미확인을 표시하는 변화: 없음(화면 코드 없음). 분모 기록의 보류·차단·미탐색 사유가 더 정확해질 뿐 확보 수치는 늘지 않는다.
- 기존 결과·버전·캐시·개인정보 영향: 어댑터 버전 0.3.0 유지. 저장 형식(DiscoveryManifest·진행표) 변경 없음.

이번 회차(fix round 4) 수정 네 가지:

1. **라이프플래닛 내장 목록의 문맥 검증.** `var result = {…}` 문장은 실제로 실행되는 `script` 요소 본문에서만 받는다. HTML 주석(`<!-- var result = … -->`)·`template` 안·데이터 블록(`type="text/template"`, `application/json`)·JS 주석·문자열 리터럴 안의 문장은 목록이 아니라 파싱 실패이며 빈 목록 성공으로 완료되지 않는다. 실행문이 두 번 있으면 모호로 실패한다. 회귀시험 `adapters_lifeplanet_inventory_requires_executable_script_context`.
2. **로그인 표지의 엔티티 디코딩.** 자격 증명 속성은 HTML 토크나이저가 읽은 실제 태그에서 엔티티 디코딩·공백 제거·대소문자 무시 후 비교한다. `type="pass&#119;ord"`·`action="/auth"`·`name="user&#95;pw"`·`autocomplete="current-password"`·`template` 안의 로그인 폼이 모두 로그인 페이지다. 기존 원문 스캔은 보수 방향으로 함께 유지한다. 시험 `entity_encoded_login_form_is_blocked_not_enumerated`·`login_detection_decodes_credential_attributes`.
3. **공시 건수 0과 끝점 커서의 조정.** 고유 건수가 공시 건수에 도달해도 끝점이 다음 커서를 주면 모순이므로 종료 증거로 받지 않고 커서를 따라간다. 공시 건수 0은 "도달"이 아니라 빈 목록 규칙으로 간다: 첫 페이지 0건·다음 없음이면 `EmptyPage`·`empty_success`(EnumeratedEmpty), 다음 커서가 있으면 계속 걷고 실제 항목으로 0건 총건수를 반박한다. 시험 `advertised_zero_with_empty_first_page_is_a_verified_empty_list`·`advertised_zero_with_next_cursor_keeps_walking`·`advertised_total_with_endpoint_next_cursor_is_not_termination`.
4. **의존 경계 검사 기록 정정.** `tools/ci/check_deps.py`의 ontology 위반 3건은 `origin/main` 깨끗한 내보내기에서도 동일하게 재현된다(`dependency-boundary.json`: 두 트리의 결과가 같고 이 브랜치가 추가한 결과는 0건, 허용 경로 안 결과 0건). 이 검사기는 CI 워크플로와 감독자 로컬 시험 명령 어디에도 없고, 원인 파일과 규칙 파일은 이 노드 허용 경로 밖이다. 면제·억제·범위 축소 없이 그대로 두고, 이 PR의 차단 조건이 아니라 저장소의 선행 미해결 항목으로 기록한다.

변경된 동작은 모두 분모를 줄이거나 보류·차단·미탐색·실패로 남기는 방향이다. robots 확인 불가 보류, 200 로그인 HTML 차단, 공제 제외와 사유 보존, 원본+추출+판 연결이 모두 있어야 확보라는 규칙은 계속 적용한다. 미확보 사유는 확보 분자에 넣지 않는다.

## 검증과 한계

- 수락 사례와 기대 결과: 기관마다 진행표가 있고 미확보 사유를 확보로 세지 않는다 → `acquisition_reason_not_counted`(필수 ID `acquisition-reason-not-counted`) 통과. robots 확인 불가 보류 → `robots_unverifiable_holds_host_and_never_fetches`. 200 로그인 HTML 미성공 → `login_html_200_is_blocked_not_enumerated`·`entity_encoded_login_form_is_blocked_not_enumerated`. 공제 제외·사유 보존 → `denominator_loads_registry_with_adr0018_scope`. 문서 종류별 확보·미확보(사유) 분리 → `adapters_scope_role_progress_preserves_every_hold_block_and_reason_in_either_order`.
- 실제 수행한 검증 및 결과: 재실행 명령 `python3 -B services/collect/tests/verify.py`. 명령별 로그 `verification-00.log`~`verification-12.log`, 종료 코드·소스 파일 SHA-256은 `verification.json`이 정본이다. 어댑터 시험 67개(라이브러리 회귀 18 + 통합 49), 이번 회차 신규 6개. 신규 6개는 수정 전 소스(`7292cf3`의 `listpage.rs`·`enumerate.rs`)에 대해 모두 실패하고 수정 후 통과함을 확인했다(변이 확인). fmt·clippy(`-D warnings`)·build·전체 workspace 시험·Python 상호운용·도구 시험·누출 검사·스켈레톤 비노출 검사·`git diff --check`를 실행했다. 의존 경계 검사(`verification-07.log`)만 exit 1이며 위 4항과 `dependency-boundary.json`이 그 근거다.
- 합성 검증 / 실제 원문 검증 / 사용자 검증 중 해당 범위: 합성 검증만. 모든 응답은 `fixture_only` transport이며 네트워크 열거·공시 원문 발췌가 없다. 라이프플래닛 구조는 저장소 조사 근거(C_life §2·§3.5) 구현이며 실서버 재검증을 뜻하지 않는다. 실제 수집은 D-04·O17 관문을 따른다.
- 미정 또는 지원하지 않는 동작: HTML 파서는 정적 목록의 보수적 지원 범위에 한정하며 완전한 HTML5 DOM 복구를 주장하지 않는다. JS 스캐너는 주석·문자열·템플릿 리터럴만 구분하는 최소 렉서이며 정규식 리터럴은 구분하지 않는다(실패 방향으로만 오류). 동적 JavaScript를 실행하지 않는다. 라이프플래닛 외 보험사 구체 파서, 특약·별표·가격 열거, 확정 판매본 모델, 실제 문서 확보, /coverage 화면은 미지원·미완료다.

## 과제와 작성 정보

- 과제 ID: T-DT-04 (fix round 4).
- 작성에 참여한 모델 역할: 구현 및 자체 검증(단일 역할). 모델 식별자 원문은 기록하지 않는다. 실행 경로: 감독자 fix 프롬프트 → CLI → 이 과제 worktree → Rust cargo / Python unittest / `tools/ci` 검사기.
- 입력 리뷰 대상 SHA: `7292cf3e0c340f280acbf375bfaf9f3cbc697412`(리뷰 역할 `st_re_review`, 판정 BLOCK). 이번 수정본의 소스 바이트는 `verification.json`의 파일별 SHA-256으로 고정한다. 최종 커밋 SHA는 감독자가 만든 뒤 이 본문에 기입해야 한다.
- 독립 리뷰: 미실시. 작성 계열과 다른 리뷰어가 최종 SHA에 고정해 수행해야 한다. 자체 검증은 독립 리뷰를 대신하지 않는다.
- 커밋·푸시·GitHub 호출을 하지 않았다. 공개된 PR #144 본문은 최초 빌드 때 감독자가 자동 생성한 것으로 이 노드가 편집할 수 없다. 감독자는 이 파일을 `gh pr edit 144 --body-file services/collect/evidence/PR_본문.md`로 적용하고, 자동 생성된 `Builder:` 줄(모델 식별자 원문)을 싣지 않아야 한다.
- 수정 경로: `services/collect/**`만. 레지스트리 CSV와 금지 경로는 수정하지 않았다.

## 확인

- [x] `docs/BLUEPRINT.md` 및 `docs/PRINCIPLES.md` 체크리스트를 확인했다.
- [x] 범위·개인정보·추천 기준 변경을 단순 구현 변경으로 숨기지 않았다(해당 변경 없음).
- [x] 규칙/가격/라벨 변경의 근거·버전·영향 사례를 연결했다. 해당 없으면 이유를 적었다(규칙·가격·라벨 변경 없음).
- [x] CI 성공을 실제 상품 정확도나 출시 승인으로 표현하지 않았다.
- [x] 설계와 구현의 상태를 요구사항 추적표에 반영했다(R02·R03·R26 구현 진행, 완료 주장 아님; 추적표 파일은 이 노드 허용 경로 밖이라 본문에 기록).
- [x] 비밀값·개인 자료·모델 식별자 원문·공시 원문 발췌를 넣지 않았다.
- [ ] 감독자의 최종 SHA 고정과 작성 계열 외 독립 리뷰.
- [ ] 저장소 선행 항목: packages/ontology 의존 경계 위반 3건(이 PR 밖).

`STATUS: READY`는 허용 범위 수정본 인계 상태이며 병합·출시 관문 통과를 뜻하지 않는다.
