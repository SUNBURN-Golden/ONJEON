## 목적과 설계 연결

- 과제 ID: **T-OP-09** (실제 실행기 검증, VM 가동 전). 구역 infra·ops, 단계 S5
- 정보 비대칭(A), 소비자 질문(Q), 계층(L), 불변식(I), 마일스톤(M): **해당 없음.** 자동 개발 운영의 개발 도구이고 소비자 기능·데이터·화면이 아니다. 출시 완성품의 일부가 아니다(09 §5). 그래서 A1~A6·Q1~Q7·L0~L9·I1~I18·M0~M6 어디에도 연결하지 않는다(BLUEPRINT §10 1항: 연결되지 않으면 범위 밖 — 이 PR은 제품 범위 밖의 운영 도구라는 점을 그대로 적는다)
- 해결하는 소비자 질문: 없음
- 요구 ID: **R1~R22**(05_VM실행준비 §6, 실제 실행기 검증 항목), U-04(자동 개발 운영)·U-05(비용 상한 없음, 기록만; R10). 필수 시험 ID 19개는 아래 표
- 관련 결정 ID / ADR: U-04, U-05(07_수정대응표). 새 결정 없음
- 설계 변경인가, 기존 설계 구현인가: 기존 설계(05 §6, 04 §8·§9)의 검증 도구 구현. 설계 문서·규칙 파일은 수정하지 않았다

## 변경 내용

- `tools/daemon/runner_verify/**`: 코어 포트의 실제 구현(별도 OS 프로세스, SIGKILL, flock 상태 저장소, 실제 git·원격 hook, 시험 프록시, 벤더 CLI 하나), R1~R22 시나리오, 자체 정적·로그 검사, 시험 58건
- `docs/vm_check/2026-10-16/`: `runner_verify.json`·`.log`, `RESULTS.md`, `exit_code_table.md`(05 §1b 확인표), `summary.json`(05 §2), `static_checks.log`, `unittest.log`(이 도구 시험), `unittest_T-OP-00.log`(T-OP-00 시험), `unittest_tools_tests.log`(CI와 같은 `tools/tests` 전체)
- 데이터·스키마·라벨·규칙·API 영향: 없음. `daemon_rules.json`·`tasks.json`·제품 코드 수정 없음
- 화면 표시 변화: 없음
- 기존 결과·버전·캐시·개인정보 영향: 없음. 시험 원격은 버려지는 로컬 bare 저장소이고, 과제는 `T-MOCK-*`뿐이다

## 검증과 한계

- 대상 SHA: 부모 `2f2d7a790747caf11ce5e3848789028624593d11`(브랜치 `grokbot/onjeon-T-OP-09`, T-OP-00b 병합 `a95dad0`을 포함) 위에 수정 라운드 1의 변경 하나를 더한 것이 PR head다. 커밋·푸시는 감독 프로세스가 하므로 head SHA는 이 문서에 쓸 수 없다. 모든 로그의 `parent commit`·`target`이 이 부모 SHA다(이전 라운드의 로그는 T-OP-00b 이전 기반 `c74a545…`에서 만든 것이라 버리고 다시 만들었다). **독립 리뷰는 PR head SHA에 고정해 감독 프로세스가 배정해야 한다.**
- 작성 참여 모델 역할·실행 경로: 빌더 역할 하나(작성·시험 실행). 실행 경로는 감독 프로세스가 연 Claude Code CLI 세션이고 이 작업 트리 안에서만 일했다. 모델 식별자 원문은 적지 않는다. 리뷰어 역할은 작성 계열이 아니어야 한다(L4 정책)
- 실행한 명령과 로그(모두 이 head의 작업 트리, 종료 코드 0):
  - `bash tools/daemon/runner_verify/run.sh --remote auto --report docs/vm_check/2026-10-16/runner_verify.json` → `runner_verify.log`(검사마다 기대·실제), `RESULTS.md`, `static_checks.log`(13항목 모두 PASS)
  - `python3 -m unittest tools/daemon/runner_verify/tests/test_runner_verify.py -v` → 58건 OK. `unittest.log`
  - `python3 -m unittest tools/tests/test_daemon_dry_run.py` → **182건 OK**(`runner_verify/`가 있는 상태). `unittest_T-OP-00.log`
  - `python3 -m unittest discover -s tools/tests -v`(CI 단계와 같은 명령) → 305건 OK(6건 skip: 보관 원문(ONJEON_ARCHIVE_RAW)·pdftotext 등 이 호스트에 없는 구성요소가 필요한 기존 시험). `unittest_tools_tests.log`
- 결과: 시나리오 22개 중 **PASS 17 · PARTIAL 5(R6·R7·R9·R11·R21) · FAIL 0 · UNCONFIRMED 0**. 검사 407건 중 실패 0, 미확인 13, 명세 불일치(GAP) 2
- PASS 17은 "스크립트 프로세스(`standin.py`) 또는 이 도구의 어댑터로 시험한 PASS"를 포함한다. 05 §6이 **실제 CLI**를 요구하는 R9·R11·R21은 벤더 CLI 변형을 시험하지 못해 PARTIAL로 적었다(R1~R5도 A를 스크립트 프로세스로 대신했고, 각 R의 "증명하지 않은 것"에 적혀 있다)
- 합성 검증 / 실제 원문 검증 / 사용자 검증: 모두 해당 없음(제품 데이터 없음). 실행기 검증이며 이 호스트의 로컬 구성요소로 했다

### 필수 시험 ID → R → 결과

| 시험 ID | R | 결과 |
|---|---|---|
| late-write-fenced | R1·R3 | PASS · PASS (스크립트 프로세스) |
| late-result-rejected | R2 | PASS (스크립트 프로세스) |
| resume-after-interrupt | R4 | PASS |
| duplicate-run-prevented | R5 | PASS |
| provider-scoped-switch | R6·R7 | **PARTIAL** · **PARTIAL** (claude CLI만 재현, 나머지 5경로 미확인) |
| hard-stop-heartbeating-job | R9 | **PARTIAL** (스크립트 프로세스는 PASS, 실제 CLI는 SIGTERM에 스스로 종료해 grace 뒤 그룹 종료를 시험하지 못함) |
| usage-recorded-not-capped | R10 | PASS |
| handoff-quiescent-before-preserve | R11 | **PARTIAL** (쓰기 루프는 스크립트 프로세스; 실제 CLI 변형 미확인) |
| duplicate-delivery-noop | R12 | PASS |
| retry-new-idempotency-key | R13 | PASS |
| preserve-manifest-same-function | R14 | PASS |
| preserve-failure-recoverable-stop | R15 | PASS |
| daemon-restart-during-handoff | R16 | PASS |
| envelope-id-distinct-events | R17 | PASS |
| lease-issue-atomic-single-owner | R18 | PASS |
| restart-ttl-expired-no-resend | R19 | PASS |
| restart-revoked-pending-void | R20 | PASS |
| restart-valid-pending-resend | R21 | **PARTIAL** (receiver_validation은 이 도구의 빌더 쪽 어댑터가 했다; 벤더 CLI 어댑터는 이 저장소에 없다) |
| restart-corrupt-record-returned | R22 | PASS |

(R8은 필수 시험 ID가 없는 반송 재개·결정 관문 시험이고 PASS.)

### 인수 기준별 증거

- R1~R22 기록, 실패는 실패로: `RESULTS.md`·`runner_verify.log`. 이번 실행에 FAIL은 없고, PARTIAL·미확인·GAP은 숨기지 않고 표에 있다
- 제품 브랜치에 쓰기·병합 없음: `static_checks.log`(병합 호출 0건, 제품 저장소 ref·HEAD·원격 실행 전후 동일, 시험 원격에 적용된 ref는 `task/T-MOCK-*`뿐), `RESULTS.md`의 "제품 브랜치" 블록(`merge_calls: 0`)
- 확인되지 않은 종료 코드는 `runner_profile`에 넣지 않았다: `summary.json`의 `limit_exit_codes`·`unavailable_exit_codes`는 전부 비어 있다. claude CLI는 모든 실패 상황이 종료 코드 1이라 구분되지 않아 비웠다
- 비밀값·모델 식별자 원문·원문 발췌 없음: `static_checks.log`의 누출 검사 두 항목. 시험 프록시 응답 원문은 저장하지 않고 상태 필드만 남겼다
- 시험 전용 데이터: `fixtures/`는 `origin=fixture`, `fixture_only=true`
- 스켈레톤 비노출 시험·누출 정적 검사: 이 저장소의 시험 코드(`tools/tests`, Rust 시험)에는 스켈레톤 비노출 시험이 없고(문서·`vocabulary.json` 외에 "skeleton" 문자열이 있는 코드가 없다), 이 PR은 소비자 화면을 만들지 않는다. 그래서 해당 제품 시험은 적용 대상이 없다. 적용 가능한 것은 (1) 이 도구 자체의 누출 정적 검사(`static_checks.log`, 통과), (2) CI의 `tools/tests` 전체와 같은 명령의 통과(`unittest_tools_tests.log`)다

### T-OP-00과의 관계 (이전 라운드의 "열린 항목 1"은 철회한다)

이전 라운드는 T-OP-00 시험 11건 실패와 병합 불가를 적었다. 그것은 T-OP-00b(`1daa4d1`) 이전 기반에서의 결과였다. T-OP-00b가 `tools/daemon/static_checks.py`·`tools/daemon/README.md`의 해시 명령·`tools/tests/test_daemon_dry_run.py`에서 `runner_verify/`를 제외했으므로, 이 head에서 `test_daemon_dry_run.py`는 182건 모두 통과한다(`unittest_T-OP-00.log`). `T-OP-00_충돌.md`는 거짓이 되어 지웠다. 이 PR은 T-OP-00의 파일을 건드리지 않는다.

### 알려진 열린 항목 (실패로 적는다)

1. R6·R7: 확인표 6경로 중 claude CLI(이 버전·출력 모드)만 시험 프록시로 재현했다. Cursor·Devin은 설치되어 있으나 프록시 지정 방법과 로그인이 없고, grokbuild·GLM 프로필·GPT 경로는 설치·정의가 없다. 전부 **미확인**이다. R6의 전환 신호는 CLI 스트림에 상태가 실려 오는 것까지를 보였고, 신호로 바꾸는 것은 이 도구(`scn_cli.py`)다. 그 뒤의 데몬 반응은 데몬이 한다("채널 재현됨" 수준)
2. R9·R11·R21: 위 표대로 실제 CLI 변형이 없다
3. R9 GAP: `hard_stop_deadline` 전이의 부수 효과에 `worktree_readonly`가 없어 코어가 끝난 임대의 작업 트리를 읽기 전용으로 만들지 않는다(04 §8 문장과 다름). R9의 통과 기준에는 들어 있지 않다. 코어는 이 과제에서 고치지 않았다
4. R1 GAP: 05 §6의 "원격 거부 + 데몬 R-11 기록"은 별개 관찰이다. 직접 푸시의 원격 거부는 R-11 기록을 만들지 않고, R-11은 A의 데몬 경유 봉투·푸시 요청·하트비트에서 나온다. 두 가지를 각각 확인했다
5. 실제 Git 호스트의 보호 브랜치·단기 자격은 사람이 적용하는 설정이라 이 도구가 만들지 못한다. 로컬 bare 저장소의 hook으로 대신했다. 전원 차단·디스크 캐시 유실은 시험하지 않았다(SIGKILL까지)
6. §1a(설치·인증·모델 증거)와 `model_matches_role`은 이 과제의 범위가 아니라 확인하지 않았다
7. **이 과제 완료는 가동 승인이 아니다.** 가동은 05 §7 점검표와 사용자 결정으로만 정해진다

## 확인

- [x] `docs/BLUEPRINT.md` 및 `docs/PRINCIPLES.md` 체크리스트를 확인했다(수정하지 않음)
- [x] 범위·개인정보·추천 기준 변경 없음
- [x] 규칙/가격/라벨 변경 없음 — 해당 없음(개발 도구)
- [x] CI 성공을 실제 상품 정확도나 출시 승인으로 표현하지 않았다. 가동 승인도 아니다
- [ ] 요구사항 추적표에 상태 반영: 08 표는 허용 경로 밖이라 고치지 않았다. 결과는 이 디렉터리에만 있다
