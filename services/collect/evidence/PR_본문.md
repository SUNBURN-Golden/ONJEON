## 목적과 설계 연결

- 과제: T-DT-04. 기존 설계 구현, 범위·정책 변경 없음.
- A1·A2·A3 / Q2·Q4·Q7 / L1 / I6·I11·I17 / M3.
- 요구 ID: R02·R03·R26(직접). R04·R10은 후속 소비 경로 지원이며 완료 주장 아님.
- 소비자 질문: 어떤 기관·상품·문서를 다루고, 무엇을 놓쳤고 왜 놓쳤는가(/coverage의 분모)?
- 계약: DATA_PIPELINE_CONTRACT §1·§2·§8, ADR-0018 §3·§4, 조사 H1~H14, Masterplan §23~24, 09 대응표 P01·P02.

## 변경 내용

- `onjeon-collect`에 `adapters` 모듈 추가: 기관 분모 적재, 분모 열거 어댑터, DiscoveryManifest 기록, 기관 진행표.
- 기관 분모: `data/registry` CSV에서 보험사 53곳 + 우체국보험을 분모로 적재하고, 공제·한국무역보험공사·seed·역사/비보험 행은 사유와 출처를 남기고 제외(ADR-0018). 알 수 없는 어휘값은 실패로 처리(어휘 규칙 4).
- 열거: 주입형 Fetch(리다이렉트 추종 없음·본문 상한) + robots 게이트(확인 불가 호스트는 UTC 일 끝까지 보류, 401/403 차단, RFC 9309 최장 매칭) + 페이지 기록(종료 증거: 공시 건수 도달·빈 페이지·다음 포인터 없음). 같은 마지막 페이지 반복·정지·상한 도달은 미탐색으로 기록하고 성공으로 세지 않는다. 성공한 빈 목록과 오류는 구분된다.
- 로그인 HTML 200은 차단(login_page)이지 성공이 아니다(§8).
- 진행표: 기관마다 행이 있고 문서 종류(약관·특약·별표·사업방법서·상품요약서·가격)별 확보·미확보(사유)를 따로 센다. 확보는 원본 보존+구획 추출+판 연결 모두 있을 때만(09 P02).
- 화면·가격·규칙·공유 스키마 변경 없음.

## 실제 검증과 한계

- 재실행: `python3 services/collect/tests/verify.py`. 전체 명령·종료 코드·파일별 SHA-256: `verification.json`.
- `cargo test -p onjeon-collect adapters` 22개 통과(필수 시험 `acquisition_reason_not_counted` 포함). 전체 workspace 통과. fmt·clippy·누출·스켈레톤 정적 검사 통과.
- 의존 경계 검사는 실패: 수정하지 않은 packages/ontology의 knowledge→twin 위반 3개(T-DT-01과 동일, `verification-07.log`). 허용 경로 밖이라 수정하지 않았다.
- 실제 열거는 없었다: 네트워크 Fetch 구현을 넣지 않았고(HTTPS 미구축, 실제 수집은 D-04·O17 관문), 모든 어댑터 시험은 합성 fixture transport로 했다.
- 협회 어댑터의 진입점은 레지스트리·2026-10-10 조사에서 실제 관측한 URL만 쓴다. 비교공시 판매본 키는 H1 반례로 불안정해 known_limitations로 선언하고 지어내지 않았다.
- 보험사 어댑터는 registry가 `disclosure_status=archived`+`reachable`로 검증한 진입점(53곳 중 8곳)에만 계획을 만든다. 나머지는 기록된 미확보 사유를 진행표 상태로 이어간다.
- 합성 fixture 검증만으로 P01·P02 실제 데이터 확보율이나 /coverage 렌더링, 첫 출시 완료를 선언하지 않는다.

## 작성·리뷰·대상 고정

- 작성 역할: 구현 및 자체 검증. 실행 경로: CLI → 이 worktree → cargo / Python unittest. 모델 식별자 원문은 기록하지 않았다.
- 기준 SHA: `ea23bb57307a5a9669c6252418a3caf13a56fff5`.
- 대상 commit SHA: 감독자 커밋 후 기입 필요. 이 세션은 커밋·푸시·GitHub 호출을 하지 않았다. 현재 코드 바이트는 `verification.json`의 파일별 SHA-256으로 고정했다.
- 독립 리뷰: 미실시. 작성 계열과 다른 리뷰어가 감독자 생성 대상 SHA에 고정해 리뷰해야 한다.
- 변경 범위: services/collect/**, data/registry/README.md. CSV·금지 문서는 수정하지 않았다.
- 감독자는 allowed_paths 대비 최종 범위를 확인해야 한다.

## 확인

- [x] BLUEPRINT·PRINCIPLES 및 계약을 확인했다.
- [x] 비밀값·실제 개인 자료·원문 발췌를 증거에 넣지 않았다. 합성 입력은 fixture transport(fixture_only)로만 썼다.
- [x] 예산·보안 정책을 완화하지 않았고, 실제 원격 호출·삭제를 하지 않았다. robots·차단을 우회하지 않는다.
- [ ] 의존 경계의 기존 위반은 담당 과제에서 해결 필요.
- [ ] 대상 commit SHA와 독립·타 계열 리뷰는 감독자 후속 관문.
- [ ] 실제 데이터와 화면을 포함한 P01·P02 제품 완료 증거는 후속 관문.
