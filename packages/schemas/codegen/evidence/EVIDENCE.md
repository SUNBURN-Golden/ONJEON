# T-CT-01 증거 색인 (`packages/schemas/codegen/evidence/`)

과제 **T-CT-01**: 계약 패키지 골격(onjeon-contracts), JSON Schema, 코드 생성(Rust·Dart·TS), 호환 검사. 구역 contracts, 단계 S0.

이 디렉터리의 로그는 아래 명령을 **이 트리에서 실제로 실행한 출력**이다. 리뷰어는 PR 본문이 아니라 대상 SHA에 커밋된 이 파일들을 읽는다. 로그 본문은 손으로 고치지 않았고 실행 머신의 절대 경로만 치환 규칙(§4)으로 바꿨다(실제로 바뀐 줄은 0개). 각 로그의 첫 줄이 명령, 마지막 줄이 `exit code: N`이다.

## 1. 로그를 만든 트리

| 항목 | 값 |
|---|---|
| 부모 커밋(로그 생성 시 HEAD) | `af2062d3bcedd7fe9861edc2f5f710635ca5ebec` — origin/main을 이 브랜치에 병합한 커밋. 그 main의 규칙 엔진은 rule-0.2(`contract_effect`)를 지원한다 |
| 작업 트리 | 위 커밋 + 이 라운드의 변경(§7). 커밋과 푸시는 감독자가 한다 |
| `packages/schemas` 트리 sha256 (`codegen/evidence/` 제외) | `400e051fbdbf2bb99e8600c49c8a0788d370c2f920b23f088dd2836b49e8ecb2` |
| 계산 명령 | `bash packages/schemas/codegen/tree_hash.sh` — `find packages/schemas -type f`에서 `codegen/evidence/`와 `__pycache__`를 빼고 `LC_ALL=C` 정렬, 각 파일 `sha256sum`의 `sha256sum` |
| 대상 SHA(PR head) | **감독자가 채운다.** 그 커밋에서 `tree_hash.sh`가 위 값을 내면 이 로그는 그 커밋의 코드에서 나온 것이다. 다르면 로그가 낡은 것이므로 §3의 명령을 다시 돌려 교체해야 한다 |
| 실행 일시 | 2026-10-17 (실행 VM 시계, UTC) |
| 실행 환경 | Linux x86_64 1대, 1회 실행. 로컬 cargo 캐시로 빌드(레지스트리 접근 없음) |

## 2. 도구 버전

| 도구 | 버전 | 비고 |
|---|---|---|
| cargo | 1.98.1 (797e8a9bc 2026-08-05) | |
| rustc | 1.98.1 (48a229cea 2026-09-01) | |
| python3 | 3.13.5 | 시험은 `-I`로 실행 |
| node | v20.19.2 | tsc 실행용 |
| tsc | Version 5.9.3 | `TSC='node /tmp/tsc/tsc.js'` (VM 임시 설치; PATH에 tsc 없음) |
| Dart SDK | 3.13.5 (stable) linux_x64 | `PATH=/tmp/dart-sdk/bin:$PATH` (VM 임시 설치) |
| bash | 5.2.37 | |
| git | 2.47.3 | |

## 3. 로그별 명령·종료 코드·결과

### `build_check.log` — 세 언어 생성물이 빌드된다

- 명령: `TSC='node /tmp/tsc/tsc.js' PATH=/tmp/dart-sdk/bin:$PATH ONJ_REQUIRE_TOOLCHAINS=1 bash packages/schemas/codegen/build_check.sh` (로그 첫 줄은 `env ONJ_REQUIRE_TOOLCHAINS=1 bash …`이고 `TSC`·`PATH`는 셸 환경으로 주었다)
- 종료 코드: **0**
- 결과: `gen.py --check` ok(생성물 14개 최신) → Rust `cargo build -p onjeon-contracts` built → TypeScript `tsc --noEmit` built, 픽스처 전부 타입 검사 + 기대 타입 오류 2개 확인(tsc 5.9.3) → Dart `dart analyze --fatal-infos --fatal-warnings` No issues, 픽스처 16개 왕복 + 거부 2건(unknown criticality, missing required) → **`RESULT: all three languages build`**. `SKIPPED` 없음.
- 수락 항목: "세 언어 생성물이 빌드된다". CI는 이 단계를 돌리지 않으므로(§6-2) 이 로그가 유일한 근거다.

### `cargo_test.log` — tests[] 1번

- 명령: `cargo test -p onjeon-contracts`
- 종료 코드: **0**
- 결과: Rust 시험 22개 ok. 그 안에서 `generated_files_are_up_to_date`(= `gen.py --check`), `python_codegen_suite_passes`(= `python3 -I -m unittest discover -s packages/schemas/codegen/tests`, 64개 OK), `compat_check_selftest_detects_a_deleted_field`(= `check_compat.sh --selftest`, self-test ok)가 실제로 돈 출력이 섞여 있다. doc-test 0개.
- 수락 항목: "tests의 명령을 실행하고 로그를 첨부했다"; "스키마의 모든 enum이 어휘 정본에서만 온다"(`test_every_enum_comes_only_from_the_vocabulary`, `generated_enums_equal_the_vocabulary_exactly`); "필드 삭제 자체 시험 실패"(`compat_check_selftest_detects_a_deleted_field`); 시험 전용 표시·스켈레톤 비노출(`every_fixture_satisfies_the_cross_field_checks_and_is_test_only`, `test_fixtures_are_marked_test_only`: origin이 있는 픽스처는 전부 `origin=fixture`, accepted·comparison_eligible 없음).

### `vocab_check.log` — tests[] 2번

- 명령: `python3 tools/vocab_check.py`
- 종료 코드: **0**
- 결과: `vocabulary ok: 33 axes, 177 values`. 이 과제는 어휘 정본을 읽기만 한다.

### `check_compat.log` — tests[] 3번 (`<prev_tag>` 형식) + 자체 시험

- 명령 4개와 종료 코드: `git tag --list 'contracts-*'` → 출력 없음(태그 없음), 0 · `bash packages/schemas/codegen/check_compat.sh --selftest` → **0**, `self-test ok` · `bash packages/schemas/codegen/check_compat.sh contracts-0.1.0` → **0**, `BASELINE: no contracts-* tag exists yet (first release); nothing to compare with.` 뒤 자체 시험 `self-test ok` · `ONJ_REQUIRE_BASELINE=1 bash … contracts-0.1.0` → **2**(의도된 거부: 태그가 생긴 뒤 CI가 쓸 형식이며 첫 릴리스 통과를 막는다)
- 자체 시험이 증명한 것: `Assertion.created_by_run`을 지운 변이 스키마에 대해 (1) 구조 비교가 `field removed`로 실패하고 (2) 이전 생성 Rust 클라이언트가 새 문서를 읽는 컴파일 탐침이 `missing field`로 실패한다. 같은 스키마끼리는 둘 다 통과한다.
- **UNVERIFIED (실제 태그 대비):** 저장소에 `contracts-*` 태그가 하나도 없어 **실제 이전 태그와의 비교는 한 번도 일어나지 않았다.** 이 로그를 그 증거로 읽지 말 것. 태그 경로 자체(`git archive`, 태그 대비 탐침, 버전 규칙, enum 값 추가·삭제)는 `codegen/tests/test_compat.py` `CheckCompatScript`가 임시 저장소에 합성 태그 `contracts-0.1.0`을 찍어 돌린다(위 `cargo_test.log`의 파이썬 묶음에 포함).

### `rule02.log` — 엔진 round-trip이 공허하지 않음

- 명령 2개: `ONJ_REQUIRE_RULE_02=1 cargo test -p onjeon-contracts` → **0** · `ONJ_REQUIRE_RULE_02=1 cargo test -p onjeon-contracts rule_02 -- --nocapture` → **0**
- 결과: `rule_02_contract_effects_round_trip_when_the_engine_supports_them ... ok`. 두 번째 명령은 stderr를 가로채지 않으므로 엔진이 rule-0.2를 거부했다면 찍혔을 건너뜀 메시지가 보였을 자리인데 없다. 즉 엔진(origin/main 병합분)이 탐침 규칙을 적재해 `applies`·`none`·`undetermined` 세 모양을 실제로 평가했고 `EvaluationResult`로 왕복했다. `ONJ_REQUIRE_RULE_02=1`은 건너뜀을 실패로 바꾸므로 이 통과는 건너뜀이 아니다.

### `generic_checks.log` — 저장소 공통 시험 명령(CI와 같은 단계)

- 명령: `cargo fmt --all -- --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test --all`, `python3 -m unittest discover -s tools/tests`, `python3 tools/vocab_check.py`, `python3 tools/validation_check.py`(+ `--selftest`), `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py`, `python3 -I packages/schemas/codegen/gen.py --check`
- 종료 코드: 전부 **0**. 긴 출력은 마지막 줄들만 적었다(`tail`; 각 구간 머리에 표시). 전체 출력이 필요한 두 명령은 위의 전용 로그에 있다.

## 4. 치환과 누출 확인

- 치환(sed): 실행 머신의 작업 트리 절대 경로 → `<repo>`, 같은 작업 루트 아래의 다른 절대 경로 → `<path>`, 사용자 홈 디렉터리 → `<home>`. 실제로 치환된 줄: **0**(로그에 그런 경로가 없었다; 규칙은 그래도 적용했다). `/tmp/…`는 임시 설치한 도구 위치라 그대로 두었다.
- 확인(grep, 0건): 절대 경로(작업 루트·홈 디렉터리 접두어), 모델 계열 이름·버전 문자열, 비밀값 형태(클라우드 액세스 키, API 키 접두어, PRIVATE KEY 블록, 저장소 토큰), cargo 잠금 대기 메시지.
- `cargo_test.log`·`rule02.log` 안에서 도는 `test_evidence.py`는 그 실행 **직전**의 이 디렉터리(직전 실행의 통과 로그)를 읽었다. 로그가 자기 자신을 담을 수는 없으므로, 커밋된 최종 파일은 대상 SHA에서 묶음을 다시 돌려 검사한다.
- 상시 검사: `codegen/tests/test_evidence.py`가 경로·비밀값·`이름-숫자.숫자` 꼴 버전 식별자·잠금 메시지·로그 완전성(명령 줄, 종료 코드, 통과 문구)을 검사한다. 모델 계열 이름은 그 시험에 적지 않았다(커밋 파일에 그 이름을 적는 것 자체가 막으려는 노출이다). 그 부분은 이번 라운드에 손으로 grep했다.

## 5. PR 템플릿 항목

- **정보 비대칭(A)**: A1~A6. CoverageDetail(A1·A2), CompareView(A3), PremiumObservation(A4), EvaluationResult·ContractSnapshot(A5), PlanView(A6)의 전송 형태.
- **소비자 질문(Q)**: Q1~Q7(EvidenceView가 Q7). 직접 해결하는 질문은 없다. 화면·API·엔진이 같은 모양을 쓰게 하는 기반이다.
- **계층(L)**: L8(화면이 받는 유일한 형식: PlanView·CoverageDetail·CompareView·EvidenceView), L6(EvaluationResult), L7(ReleaseManifest), L3(Assertion·PremiumObservation 후보). 모양만이고 계층의 동작 구현이 아니다.
- **불변식(I)**: I4(금액은 정수 원 — 스키마 lint `test_money_is_integer_krw`, Rust `no_wire_type_exposes_floating_point_money`, 부동소수점은 화면 표시용 만원 6개 필드뿐). I6·I7·I8·I12는 근거 참조·가격 조건·비교 기준·공개/개인 분리의 **형태**만 둔다. 의미 검사·DB 제약은 T-CT-03~05, T-KN-* 몫이다.
- **마일스톤(M)**: M1(§6 어휘를 `packages/schemas`로 생성 — Rust·Dart·TS).
- **요구 ID(R)**: R07, R10, R11, R13, R14, R16, R17 — 각 객체의 전송 형태를 고정한다. 요구의 충족이 아니다.
- **관련 결정/ADR**: ADR-0011, ADR-0012. 입력: 02_구현계약 §1·§5·§6(검토용 묶음, 채택 전), 화면 설계서 §11, 어휘 1.5.0.
- **설계 변경인가**: 기존 설계의 구현. 02가 닫지 않은 항목은 정하지 않고 자리만 두었다(README '한계와 열린 항목').
- **데이터·스키마·라벨·규칙·API 영향**: 새 crate `onjeon-contracts`, JSON Schema 13개(어휘 스키마 1개는 생성물), 생성 TS·Dart 패키지. 규칙 엔진 코드는 바꾸지 않고 dev-dependency로 소비만 한다. 어휘 정본 변경 없음.
- **화면 표시 변화**: 없음(앱 없음). **기존 결과·버전·캐시·개인정보 영향**: 없음. 픽스처는 전부 `origin=fixture`, 개인 데이터 없음.
- **과제 ID**: T-CT-01.
- **작성에 참여한 모델 역할·실행 경로**: 구현 역할 하나(implementer)가 감독자가 연 과제 전용 워크트리에서 과제 사양과 운영자 점검표(2026-10-16 23:10 KST)에 따라 자동 실행한 라운드. 리뷰 역할은 작성 계열이 아닌 독립 리뷰어이며 감독자가 대상 SHA에 고정한다. 모델 계열·버전은 식별자 비노출 규칙에 따라 여기 적지 않는다(감독자 기록에 있다).
- **대상 SHA**: 감독자가 채운다. 독립 리뷰의 SHA 고정도 감독자 몫이다.
- **수락 사례와 기대 결과**: done_criteria 3개 ↔ 로그: 세 언어 빌드 ↔ `build_check.log`; 필드 삭제 시 호환 검사 실패 ↔ `check_compat.log`·`cargo_test.log`; enum은 어휘에서만 ↔ `cargo_test.log`(`vocab_check.log`가 어휘 자체).
- **실제 수행한 검증**: §3 전부, 이 트리에서, 마지막 코드 변경 뒤에.
- **합성 / 실제 원문 / 사용자 검증**: 합성만(픽스처, `origin=fixture`). 실제 원문 검증은 이 과제 범위가 아니다(엔진의 `real_clauses` 시험은 `cargo test --all`에 포함되지만 엔진 과제의 것). 사용자 검증 없음.
- **미정·지원하지 않는 동작**: §6.

## 6. 건너뜀·공허·미검증 (숨기지 않는다)

1. **실제 이전 태그와의 호환 비교는 하지 않았다.** `contracts-*` 태그가 없다. 태그는 릴리스 절차가 찍는다. UNVERIFIED.
2. **CI는 TypeScript·Dart를 빌드하지 않는다.** CI 단계 연결(`.github/workflows/`)은 이 과제의 허용 경로 밖이다(구현자 관리). 세 언어 빌드의 근거는 이 VM에서의 `build_check.log` 1회 실행뿐이다.
3. 호환 컴파일 탐침은 Rust만이다. TypeScript·Dart는 현재 스키마의 빌드·픽스처 확인만 하고 이전 태그 생성물로의 교차 컴파일은 없다.
4. 어휘 승격 대기 축(`x-onjeon-pending-axis`) **27개, 필드 32개**는 닫힌 enum이 아니라 소문자 snake_case 패턴 문자열이다. 어휘에 넣는 것은 T-CT-02 몫이고 이 과제는 `vocabulary.json`을 바꿀 수 없다. 축이 어휘에 들어오면 lint가 실패해 `$ref`로 바꾸게 한다.
5. 생성 클라이언트는 `pattern`·`minimum`·`minItems`를 강제하지 않는다(시험용 `validate.py`만). Dart `fromJson`은 필수-nullable 키의 부재와 null을 구분하지 않는다.
6. 의미 검사(릴리스 빌더, DB 제약, evidence_ref 파서, OpenAPI, 오류 코드 표, 이벤트)는 T-CT-03~05·T-KN-* 몫이다. `ErrorResponse`는 형태만 있다.
7. 로그 신선도는 수동이다: 대상 SHA에서 `tree_hash.sh` 값을 §1과 대조한다. `test_evidence.py`는 형식·통과·누출만 본다.
8. 실행은 한 머신에서 1회다. 재현은 트리 해시가 같은 체크아웃에서 같은 명령으로 한다.
9. `rule_02_…` 시험은 엔진이 rule-0.2를 거부하는 체크아웃에서는 건너뜀 메시지를 찍고 통과한다(공허). 이 트리에서는 공허하지 않음을 `rule02.log`로 보였다. CI가 `ONJ_REQUIRE_RULE_02=1`로 불러 건너뜀을 실패로 만드는 단계는 연결되지 않았다(§6-2와 같은 이유).
10. 독립 리뷰의 SHA 고정과 최종 대상 SHA는 이 파일에 없다(감독자).
11. 02가 닫지 않은 항목(주장 ID 표기 `a:`/`assertion:`, `release_hash`↔`content_sha256`, `need_result.id` 형식, `special_conditions`·`usage_counters` 항목 형식, `scope_relation`·`judged_by` 값 집합)은 자리만 두었다.
12. 호환 탐침의 enum 값 선택을 이번에 고쳤다(§7). 그 전에는 새 어휘 값이 축의 맨 앞에 들어오면 거짓 비호환이 났을 것이다. 실제 태그가 없어 운영에서 그 오판이 난 적은 없다.

## 7. 이 라운드의 변경(허용 경로 안)

- `codegen/compat.py`: `minimal_value`가 enum 값을 새 어휘의 `values[0]`에서 고르던 것을 `enum_sample`로 바꿨다 — 이전·새 어휘에 모두 있는 값 중 새 어휘 순서의 첫 값. 폴백(이전에 없던 축, 이전 값 전부 삭제)은 함수 설명에 적었다.
- `codegen/tests/test_compat.py`: 회귀 시험 4개 — 새 값을 맨 앞에 넣어도 탐침 문서가 구버전이 아는 값을 쓴다(단위), 폴백 2가지(단위), 임시 저장소의 실제 태그 대비 `check_compat.sh`가 새 값 맨 앞 삽입 + 0.1.1에서 호환(컴파일 탐침 포함), 값 삭제 + 0.1.1에서 `BREAKING enum value removed`로 실패. 고치기 전 `compat.py`로 돌리면 삽입 시험이 `unknown variant` → `INCOMPATIBLE`로 실패함을 확인했다. 임시 저장소 복사에서 `evidence/`를 뺐다.
- `codegen/tests/test_evidence.py`, `codegen/tree_hash.sh`: §4·§1.
- `README.md`(packages/schemas): '증거' 절 추가, 세 언어 빌드 근거가 커밋 로그임을 명시, 탐침 enum 값 규칙, 태그 부재 명시.
- 이 디렉터리.
