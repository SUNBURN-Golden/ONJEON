## 목적과 설계 연결

- 과제 ID: **T-OP-09** (실제 실행기 검증, VM 가동 전). 구역 infra·ops, 단계 S5
- 정보 비대칭(A), 소비자 질문(Q), 계층(L), 불변식(I), 마일스톤(M): **해당 없음.** 자동 개발 운영의 개발 도구이고 소비자 기능·데이터·화면이 아니다. 출시 완성품의 일부가 아니다(09 §5). 그래서 A1~A6·Q1~Q7·L0~L9·I1~I18·M0~M6 어디에도 연결하지 않는다(BLUEPRINT §10 1항: 연결되지 않으면 범위 밖 — 이 PR은 제품 범위 밖의 운영 도구라는 점을 그대로 적는다)
- 해결하는 소비자 질문: 없음
- 요구 ID: **R1~R22**(05_VM실행준비 §6, 실제 실행기 검증 항목), U-04(자동 개발 운영)·U-05(비용 상한 없음, 기록만; R10). 필수 시험 ID 19개는 아래 표
- 관련 결정 ID / ADR: U-04, U-05(07_수정대응표). 새 결정 없음
- 설계 변경인가, 기존 설계 구현인가: 기존 설계(05 §6, 04 §8·§9)의 검증 도구 구현. 설계 문서·규칙 파일은 수정하지 않았다

## 변경 내용

- `tools/daemon/runner_verify/**`: 코어 포트의 실제 구현(별도 OS 프로세스, SIGKILL, flock 상태 저장소, 실제 git·원격 hook, 시험 프록시, 벤더 CLI 하나), R1~R22 시나리오, 자체 정적·로그 검사, 시험 58건
- `docs/vm_check/2026-10-15/`: `runner_verify.json`·`.log`, `RESULTS.md`, `exit_code_table.md`(05 §1b 확인표), `summary.json`(05 §2), `static_checks.log`, `unittest.log`, `T-OP-00_충돌.md`
- 데이터·스키마·라벨·규칙·API 영향: 없음. `daemon_rules.json`·`tasks.json`·제품 코드 수정 없음
- 화면 표시 변화: 없음
- 기존 결과·버전·캐시·개인정보 영향: 없음. 시험 원격은 버려지는 로컬 bare 저장소이고, 과제는 `T-MOCK-*`뿐이다

## 검증과 한계

- 대상 SHA: 부모 `c74a545a45d1aba9eee71b76d81b3017ac16bbbb`(브랜치 `grokbot/onjeon-T-OP-09`). PR head는 이 부모에 변경 커밋 하나를 더한 것이다. 커밋·푸시는 감독 프로세스가 하므로 head SHA는 이 문서에 쓸 수 없다. **독립 리뷰는 PR head SHA에 고정해 감독 프로세스가 배정해야 한다. 아직 없다.**
- 작성 참여 모델 역할·실행 경로: 빌더 역할 하나(작성·시험 실행). 실행 경로는 감독 프로세스가 연 Claude Code CLI 세션이고 이 작업 트리 안에서만 일했다. 모델 식별자 원문은 적지 않는다. 리뷰어 역할은 작성 계열이 아니어야 한다(L4 정책)
- 실행한 명령과 로그:
  - `bash tools/daemon/runner_verify/run.sh --remote auto --report docs/vm_check/2026-10-15/runner_verify.json` → 종료 코드 0. `runner_verify.log`(검사마다 기대·실제), `RESULTS.md`
  - `python3 -m unittest tools/daemon/runner_verify/tests/test_runner_verify.py` → 58건 OK. `unittest.log`
- 결과: 시나리오 22개 중 **PASS 19 · PARTIAL 3(R6·R7·R9) · FAIL 0 · UNCONFIRMED 0**. 검사 404건 중 실패 0, 미확인 11, 명세 불일치(GAP) 1
- 합성 검증 / 실제 원문 검증 / 사용자 검증: 모두 해당 없음(제품 데이터 없음). 실행기 검증이며 이 호스트의 로컬 구성요소로 했다

### 필수 시험 ID → R → 결과

| 시험 ID | R | 결과 |
|---|---|---|
| late-write-fenced | R1·R3 | PASS · PASS |
| late-result-rejected | R2 | PASS |
| resume-after-interrupt | R4 | PASS |
| duplicate-run-prevented | R5 | PASS |
| provider-scoped-switch | R6·R7 | **PARTIAL** · **PARTIAL** (claude CLI만 재현, 나머지 5경로 미확인) |
| hard-stop-heartbeating-job | R9 | **PARTIAL** (스크립트 프로세스는 PASS, 실제 CLI는 SIGTERM에 스스로 종료해 grace 뒤 그룹 종료를 시험하지 못함) |
| usage-recorded-not-capped | R10 | PASS |
| handoff-quiescent-before-preserve | R11 | PASS |
| duplicate-delivery-noop | R12 | PASS |
| retry-new-idempotency-key | R13 | PASS |
| preserve-manifest-same-function | R14 | PASS |
| preserve-failure-recoverable-stop | R15 | PASS |
| daemon-restart-during-handoff | R16 | PASS |
| envelope-id-distinct-events | R17 | PASS |
| lease-issue-atomic-single-owner | R18 | PASS |
| restart-ttl-expired-no-resend | R19 | PASS |
| restart-revoked-pending-void | R20 | PASS |
| restart-valid-pending-resend | R21 | PASS |
| restart-corrupt-record-returned | R22 | PASS |

(R8은 필수 시험 ID가 없는 반송 재개·결정 관문 시험이고 PASS.)

### 인수 기준별 증거

- R1~R22 기록, 실패는 실패로: `RESULTS.md`·`runner_verify.log`. 이번 실행에 FAIL은 없고, PARTIAL·미확인·GAP은 숨기지 않고 표에 있다
- 제품 브랜치에 쓰기·병합 없음: `static_checks.log`(병합 호출 0건, 제품 저장소 ref·HEAD·원격 실행 전후 동일, 시험 원격에 적용된 ref는 `task/T-MOCK-*`뿐), `RESULTS.md`의 "제품 브랜치" 블록(`merge_calls: 0`)
- 확인되지 않은 종료 코드는 `runner_profile`에 넣지 않았다: `summary.json`의 `limit_exit_codes`·`unavailable_exit_codes`는 전부 비어 있다. claude CLI는 모든 실패 상황이 종료 코드 1이라 구분되지 않아 비웠다
- 비밀값·모델 식별자 원문·원문 발췌 없음: `static_checks.log`의 누출 검사 두 항목. 시험 프록시 응답 원문은 저장하지 않고 상태 필드만 남겼다
- 시험 전용 데이터: `fixtures/`는 `origin=fixture`, `fixture_only=true`
- 스켈레톤 비노출 시험·누출 정적 검사: 이 도구에는 해당 제품 화면이 없다. 이 도구 자체의 누출 정적 검사(위)가 통과한다. **저장소 전체의 스켈레톤 비노출 시험을 이 PR에서 따로 실행하지는 않았다.**

### 알려진 열린 항목 (실패로 적는다)

1. **T-OP-00 시험 11건이 이 작업 트리에서 실패한다.** `tools/daemon/static_checks.py`가 `tools/daemon/` 전체를 훑고, 증거 해시가 `tools/daemon/` 전체의 내용 해시이기 때문이다. 두 파일은 이 과제의 허용 경로 밖이라 고치지 않았다. 원인·건수·필요한 변경은 `T-OP-00_충돌.md`. **감독 프로세스가 T-OP-00 쪽에 한 줄 예외와 증거 로그 재생성을 배정해야 이 PR이 병합 가능하다.**
2. R6·R7: 확인표 6경로 중 claude CLI(이 버전·출력 모드)만 시험 프록시로 재현했다. Cursor·Devin은 설치되어 있으나 프록시 지정 방법과 로그인이 없고, grokbuild·GLM 프로필·GPT 경로는 설치·정의가 없다. 전부 **미확인**이다
3. R9 GAP: `hard_stop_deadline` 전이의 부수 효과에 `worktree_readonly`가 없어 코어가 끝난 임대의 작업 트리를 읽기 전용으로 만들지 않는다(04 §8 문장과 다름). R9의 통과 기준에는 들어 있지 않다. 코어는 이 과제에서 고치지 않았다
4. 실제 Git 호스트의 보호 브랜치·단기 자격은 사람이 적용하는 설정이라 이 도구가 만들지 못한다. 로컬 bare 저장소의 hook으로 대신했다. 전원 차단·디스크 캐시 유실은 시험하지 않았다(SIGKILL까지)
5. §1a(설치·인증·모델 증거)와 `model_matches_role`은 이 과제의 범위가 아니라 확인하지 않았다
6. **이 과제 완료는 가동 승인이 아니다.** 가동은 05 §7 점검표와 사용자 결정으로만 정해진다

## 확인

- [x] `docs/BLUEPRINT.md` 및 `docs/PRINCIPLES.md` 체크리스트를 확인했다(수정하지 않음)
- [x] 범위·개인정보·추천 기준 변경 없음
- [x] 규칙/가격/라벨 변경 없음 — 해당 없음(개발 도구)
- [x] CI 성공을 실제 상품 정확도나 출시 승인으로 표현하지 않았다. 가동 승인도 아니다
- [ ] 요구사항 추적표에 상태 반영: 08 표는 허용 경로 밖이라 고치지 않았다. 결과는 이 디렉터리에만 있다
