## 목적과 설계 연결

- 정보 비대칭(A), 소비자 질문(Q), 계층(L), 불변식(I), 마일스톤(M): A1·A2·A3 / Q2·Q4·Q7 / L0·L1 / I6·I11·I17 / M3.
- 해결하는 소비자 질문: 어떤 기관·상품·판매기간·문서를 발견했고 무엇이 보류·차단·미탐색인가(Q2·Q4·Q7).
- 요구 ID (`docs/blueprint/REQUIREMENTS.md`): R02·R03·R26(직접). R04·R10은 후속 소비 경로 지원이며 완료 주장 아님.
- 관련 결정 ID / ADR: ADR-0018 §3·§4, DATA_PIPELINE_CONTRACT §1·§2·§8, 조사 H1~H14, 09 P01·P02, D-04·O17 관문.
- 설계 변경인가, 기존 설계 구현인가: 기존 설계 구현(T-DT-04, fix round 5). 범위·접근 정책 변경 없음.

## 변경 내용

- 데이터·스키마·라벨·규칙·API 영향: 공유 스키마·어휘·가격 계산·규칙 결과·개인정보 경로를 바꾸지 않는다. `DiscoveryManifest.termination`에 `kind: "access_denied"`(목록 URL의 401/403, `at_cursor`·`http_status`)가 추가된다. 저장 형식은 그 변형 추가 외에 동일하며 변경은 `services/collect/**` 안이다.
- 화면에서 보장·제외·가격·미확인을 표시하는 변화: 없음(화면 코드 없음). 분모 기록의 보류·차단·미탐색 사유가 더 정확해질 뿐 확보 수치는 늘지 않는다.
- 기존 결과·버전·캐시·개인정보 영향: 어댑터 버전 0.3.0 유지. 기존 매니페스트 재해석 없음. 개인정보 없음.

이번 회차(fix round 5) 수정 네 가지와 정리 하나:

1. **스크립트 어휘 문맥의 건전성(리뷰 1, P1).** `var result = {…}` 문장을 찾는 최소 JS 렉서가 정규식 리터럴을 토큰화한다. `/`는 스크립트 시작·연산자·`( , [ { ; :`·식 키워드(`return`·`typeof`·`in` 등)·`if/while/for/with` 머리 뒤에서는 정규식, 식별자·숫자·리터럴·`)`·`]` 뒤에서는 나눗셈이다. 두 해석이 모두 가능한 `}`·`++`·`--` 뒤의 `/`, 템플릿 치환 `${`, 끝나지 않은 문자열·주석·정규식, 괄호 불균형은 "분류 불가"로 거부해 파싱 실패로 끝난다(빈 목록 성공이 아니다). 선언은 중괄호 깊이 0에서만 인벤토리다(함수 본문 안은 아님). Annex B `-->` 줄 주석을 주석으로 읽는다. JSON 뒤에는 문장이 끝나야 한다(`;`·끝·줄바꿈 뒤 새 문장만 허용, `, result = …`·`.outData`·`(x)`·`in window`는 거부). 리뷰의 예(`const decoy = /;var result = {…}/;`)는 `inventory variable absent`로 실패한다. 회귀시험 `adapters_lifeplanet_inventory_rejects_unclassifiable_script_contexts`(거부 29건, 정상 스크립트 수용 13건 + 1행 사례).
2. **세미콜론 없는 문자 참조(리뷰 2, P1).** 숫자 참조는 브라우저처럼 `;` 없이도 디코딩한다(`pass&#119ord`·`&#112assword`·`pass&#x77ord`). 0·서로게이트·범위 밖은 U+FFFD. 명명 참조는 `;` 없는 레거시 `amp`·`lt`·`gt`·`quot`만, 뒤에 `=`나 영숫자가 오면 디코딩하지 않는다(속성값 규칙). `&#x70assword`는 브라우저와 같이 `&#x70a`+`ssword`로 읽어 비밀번호 표지가 아니다. 전체 분류 경로 시험 `unterminated_entity_password_field_is_blocked_not_enumerated`: `action="/list"`와 일치하는 목록 링크가 있어도 200 응답은 `login_page`, 항목 0, `blocked`, 진행표 `Blocked`. 단위 시험 `login_detection_decodes_credential_attributes`에 양성 7건·음성 2건 추가.
3. **401/403은 끝까지 blocked(리뷰 4, P2).** 목록 URL의 401/403은 새 종료 `Termination::AccessDenied { at_cursor, http_status }`로 기록하고 `exploration_state_of`가 `Blocked { reason: "access_denied" }`로 사상한다. 진행표의 범위 상태·문서 항목 상태(`AcquisitionStatus::Blocked`)·역할별 미확보 사유(`blocked`)에 그대로 전파되며 `failed`로 바뀌지 않는다. 500 등 다른 HTTP 오류는 종전처럼 `FetchFailed`→`Failed`다. 시험 `http_401_403_list_page_is_blocked_throughout`(401·403 단일 페이지, 500 대조, 2쪽에서 403이 난 문서 계획의 진행표 전파).
4. **PR 메타데이터(리뷰 3, P1).** 이 파일을 대상 head `c659ce8fedd22adde4e1796fa1e93456f6752f32`에 맞춰 갱신했다. 공개된 PR #144 본문은 최초 빌드 때 감독자가 한 번 자동 생성한 것으로, 이 노드는 GitHub를 호출할 수 없어 편집하지 못한다(아래 "과제와 작성 정보").
5. **정리.** `src/adapters/` 안에 남아 있던 과거 기록 JSON 2개(`verification-fix4.json`·`verification-fix5.json`, 모두 `historical_only`)를 `evidence/historical/`로 옮겼다. 제품 소스 디렉터리에 임시 데이터가 남지 않는다.

변경된 동작은 모두 분모를 줄이거나 보류·차단·미탐색·실패로 남기는 방향이다. robots 확인 불가 보류, 200 로그인 HTML 차단, 공제 제외와 사유 보존, 원본+추출+판 연결이 모두 있어야 확보라는 규칙은 계속 적용한다. 미확보 사유는 확보 분자에 넣지 않는다.

## 검증과 한계

- 수락 사례와 기대 결과: 기관마다 진행표가 있고 미확보 사유를 확보로 세지 않는다 → `acquisition_reason_not_counted`(필수 ID `acquisition-reason-not-counted`) 통과. robots 확인 불가 보류 → `robots_unverifiable_holds_host_and_never_fetches`. 200 로그인 HTML 미성공 → `login_html_200_is_blocked_not_enumerated`·`entity_encoded_login_form_is_blocked_not_enumerated`·`unterminated_entity_password_field_is_blocked_not_enumerated`. 접근 거부는 차단 → `http_401_403_list_page_is_blocked_throughout`. 공제 제외·사유 보존 → `denominator_loads_registry_with_adr0018_scope`. 문서 종류별 확보·미확보(사유) 분리 → `adapters_scope_role_progress_preserves_every_hold_block_and_reason_in_either_order`.
- 실제 수행한 검증 및 결과: 재실행 명령 `python3 -B services/collect/tests/verify.py`. 명령별 로그 `verification-00.log`~`verification-12.log`, 종료 코드·소스 파일 SHA-256은 `verification.json`이 정본이다. 어댑터 시험 69개(라이브러리 회귀 19 + 통합 50), 이번 회차 신규 3개·확장 1개. 변이 확인: `listpage.rs`를 입력 SHA 판으로 되돌리면 신규·확장 시험 3개가 실패하고, `enumerate.rs`에서 401/403 분기를 끄거나 `AccessDenied`를 `Failed`로 사상하면 `http_401_403_list_page_is_blocked_throughout`이 실패하며, 수정본에서는 모두 통과한다(`handoff.json` `mutation_check`). fmt·clippy(`-D warnings`)·build·전체 workspace 시험·Python 상호운용·도구 시험·누출 검사·스켈레톤 비노출 검사·`git diff --check`를 실행했다. 의존 경계 검사(`verification-07.log`)만 exit 1이며 `origin/main`(b0b6942)에서 동일하게 재현되는 저장소 선행 항목이다(`dependency-boundary.json`). `git merge-tree`로 `origin/main`과 충돌이 없음을 확인했다.
- 합성 검증 / 실제 원문 검증 / 사용자 검증 중 해당 범위: 합성 검증만. 모든 응답은 `fixture_only` transport이며 네트워크 열거·공시 원문 발췌가 없다. 라이프플래닛 구조는 저장소 조사 근거(C_life §2·§3.5) 구현이며 실서버 재검증을 뜻하지 않는다. 실제 수집은 D-04·O17 관문을 따른다.
- 미정 또는 지원하지 않는 동작: HTML 파서는 정적 목록의 보수적 지원 범위에 한정하며 완전한 HTML5 DOM 복구를 주장하지 않는다. JS 스캐너는 렉서이지 파서가 아니다 — 어휘 문맥(주석·문자열·템플릿·정규식·괄호 깊이·문장 종결)은 건전하게 분류하거나 거부하지만, 어휘적으로 유효하되 문법적으로 잘못된 스크립트(예: `var x = ;`)는 식별하지 못한다. 동적 JavaScript를 실행하지 않는다. 실제 라이프플래닛 페이지가 `}` 뒤 나눗셈·템플릿 치환·함수 본문 안 선언을 쓴다면 열거는 파싱 실패로 남고(위조 아님) 어댑터 계획을 다시 조사해야 한다. 라이프플래닛 외 보험사 구체 파서, 특약·별표·가격 열거, 확정 판매본 모델, 실제 문서 확보, /coverage 화면은 미지원·미완료다.

## 과제와 작성 정보

- 과제 ID: T-DT-04 (fix round 5).
- 작성에 참여한 모델 역할: 구현 및 자체 검증(단일 역할). 모델 식별자 원문은 기록하지 않는다. 실행 경로: 감독자 fix 프롬프트 → CLI → 이 과제 worktree → Rust cargo / Python unittest / `tools/ci` 검사기.
- 입력 리뷰 대상 SHA: `c659ce8fedd22adde4e1796fa1e93456f6752f32`(리뷰 역할 `st_re_review`, 판정 BLOCK, 리뷰가 확인한 PR #144 head와 일치). 이번 수정본의 소스 바이트는 `verification.json`의 파일별 SHA-256으로 고정한다. 최종 커밋 SHA는 감독자가 만든 뒤 이 본문에 기입해야 한다.
- 독립 리뷰: 미실시. 작성 계열과 다른 리뷰어가 최종 SHA에 고정해 수행해야 한다. 자체 검증은 독립 리뷰를 대신하지 않는다.
- 커밋·푸시·GitHub 호출을 하지 않았다. 공개된 PR #144 본문은 최초 빌드 때 감독자가 자동 생성한 것으로 이 노드가 편집할 수 없다(감독자 코드는 PR이 있으면 본문을 다시 쓰지 않는다). 감독자 조치: 커밋 뒤 `gh pr edit 144 --body-file services/collect/evidence/PR_본문.md`로 이 본문을 적용하고, 위 "최종 커밋 SHA" 자리에 그 커밋 SHA를 기입하며, 자동 생성된 `Builder:` 줄(모델 식별자 원문)을 싣지 않아야 한다.
- 수정 경로: `services/collect/**`만. 레지스트리 CSV와 금지 경로는 수정하지 않았다.

## 확인

- [x] `docs/BLUEPRINT.md` 및 `docs/PRINCIPLES.md` 체크리스트를 확인했다.
- [x] 범위·개인정보·추천 기준 변경을 단순 구현 변경으로 숨기지 않았다(해당 변경 없음).
- [x] 규칙/가격/라벨 변경의 근거·버전·영향 사례를 연결했다. 해당 없으면 이유를 적었다(규칙·가격·라벨 변경 없음).
- [x] CI 성공을 실제 상품 정확도나 출시 승인으로 표현하지 않았다.
- [x] 설계와 구현의 상태를 요구사항 추적표에 반영했다(R02·R03·R26 구현 진행, 완료 주장 아님; 추적표 파일은 이 노드 허용 경로 밖이라 본문에 기록).
- [x] 비밀값·개인 자료·모델 식별자 원문·공시 원문 발췌를 넣지 않았다.
- [ ] 감독자의 최종 SHA 고정, PR 본문 적용, 작성 계열 외 독립 리뷰.
- [ ] 저장소 선행 항목: packages/ontology 의존 경계 위반 3건(이 PR 밖).

`STATUS: READY`는 허용 범위 수정본 인계 상태이며 병합·출시 관문 통과를 뜻하지 않는다.
