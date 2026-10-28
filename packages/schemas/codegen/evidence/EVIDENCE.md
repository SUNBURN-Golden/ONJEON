# T-CT-01 · T-CT-02 증거 색인 (`packages/schemas/codegen/evidence/`)

Audit 2 어휘 1.8.0 변경의 현재 검증은 [별도 증거 색인](../../../../tools/evidence/audit2-engine-string-literals/README.md)에 기록했다. 아래 로그·트리 해시는 과거 T-CT-01·02 실행 기록이며 현재 트리의 세 언어 빌드를 증명하지 않는다. 이번에는 Rust 빌드·workspace 시험·생성물 최신성을 검증했고 TypeScript·Dart는 도구 미설치로 건너뛰었다.

과제 **T-CT-01**(계약 패키지 골격 `onjeon-contracts`, JSON Schema, 코드 생성 Rust·Dart·TS, 호환 검사)이 이 디렉터리를 만들었고, 과제 **T-CT-02**(어휘 정본 1.6.0: 새 축 12개와 `doc_role` 값 2개)가 어휘 변경에 맞춰 계약을 적응시킨 뒤 로그 전부를 다시 만들었다. 구역 contracts, 단계 S0.

이 디렉터리의 로그는 아래 명령을 **이 트리에서 실제로 실행한 출력**이다. 리뷰어는 PR 본문이 아니라 대상 SHA에 커밋된 이 파일들을 읽는다. 로그 본문은 손으로 고치지 않았고 실행 머신의 절대 경로만 치환 규칙(§4)으로 바꿨다(실제로 바뀐 줄은 0개). 각 로그의 첫 줄이 명령, 마지막 줄이 `exit code: N`이다.

## 1. 로그를 만든 트리

| 항목 | 값 |
|---|---|
| 부모 커밋(로그 생성 시 HEAD) | `c0e43949d0dd858f43097ac2f2ae1b5dd289682a` — T-CT-02의 어휘 1.6.0 커밋(PR #118). 작업 트리에는 origin/main `57f14e7054cce2743c822af24cf9e823d6c683a6`(T-CT-01 PR #102 포함)이 병합되어 있고 병합 커밋은 감독자가 만든다 |
| 작업 트리 | 위 두 커밋의 병합 + 이 라운드의 변경(§7). 커밋과 푸시는 감독자가 한다 |
| `packages/schemas` 트리 sha256 (`codegen/evidence/` 제외) | `3cff44974d8e132b0907ae88d5cbc395eb825231f020a7e26f885ac4d2bf6c0e` |
| 계산 명령 | `bash packages/schemas/codegen/tree_hash.sh` — `find packages/schemas -type f`에서 `codegen/evidence/`와 `__pycache__`를 빼고 `LC_ALL=C` 정렬, 각 파일 `sha256sum`의 `sha256sum` |
| 대상 SHA(PR head) | **감독자가 채운다.** 그 커밋에서 `tree_hash.sh`가 위 값을 내면 이 로그는 그 커밋의 코드에서 나온 것이다. 다르면 로그가 낡은 것이므로 §3의 명령을 다시 돌려 교체해야 한다 |
| 실행 일시 | 2026-10-17 (실행 VM 시계, UTC) |
| 실행 환경 | Linux x86_64 1대, 1회 실행. 마지막 라운드(검증·마무리) 직전에 실행 VM의 도구 캐시가 비워져 있어 Rust 안정판 도구 모음, 크레이트(`cargo fetch`, Cargo.lock으로 고정), tsc, Dart SDK를 다시 설치해 받은 뒤 로그 전부를 다시 만들었다. 코드는 바꾸지 않았다(위 트리 해시가 앞 라운드와 같다) |

## 2. 도구 버전

| 도구 | 버전 | 비고 |
|---|---|---|
| cargo | 1.99.1 (5f94df478 2026-08-27) | 앞 라운드의 로그는 1.98.1로 만들었다. 이번 라운드가 안정판을 새로 설치해 전부 다시 돌렸다 |
| rustc | 1.99.1 (58cf8f9c3 2026-10-13) | |
| clippy | 0.1.99 (58cf8f9c35 2026-10-13) | `cargo clippy --all-targets -- -D warnings` |
| rustfmt | 1.10.0-stable (58cf8f9c35 2026-10-13) | `cargo fmt --all -- --check` |
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
- 결과: `gen.py --check` ok(생성물 14개 최신, 어휘 1.6.0 기준) → Rust `cargo build -p onjeon-contracts` built → TypeScript `tsc --noEmit` built, 픽스처 전부 타입 검사 + 기대 타입 오류 2개 확인(tsc 5.9.3) → Dart `dart analyze --fatal-infos --fatal-warnings` No issues, 픽스처 16개 왕복 + 거부 2건(unknown criticality, missing required) → **`RESULT: all three languages build`**. `SKIPPED` 없음.
- 수락 항목: "세 언어 생성물이 빌드된다". CI는 이 단계를 돌리지 않으므로(§6-2) 이 로그가 유일한 근거다.

### `cargo_test.log` — 계약 crate 시험

- 명령: `cargo test -p onjeon-contracts`
- 종료 코드: **0**
- 결과: Rust 시험 25개 ok(T-CT-01의 22개 + T-CT-02가 더한 3개: `error_class_words_and_code_letters_correspond_one_to_one`, `a_class_letter_is_no_longer_a_valid_error_class_on_the_wire`, `promoted_axes_reject_unknown_values_instead_of_keeping_a_string`). 그 안에서 `generated_files_are_up_to_date`(= `gen.py --check`), `python_codegen_suite_passes`(= `python3 -I -m unittest discover -s packages/schemas/codegen/tests`, 64개 OK), `compat_check_selftest_detects_a_deleted_field`(= `check_compat.sh --selftest`, self-test ok)가 실제로 돈 출력이 섞여 있다. doc-test 0개.
- 수락 항목: "스키마의 모든 enum이 어휘 정본에서만 온다"(`test_every_enum_comes_only_from_the_vocabulary`, `generated_enums_equal_the_vocabulary_exactly`: 어휘 1.6.0의 45개 축과 생성 enum이 정확히 같다); "어휘에 들어온 대기 축은 `$ref`가 됐다"(`test_pending_axes_must_move_to_the_vocabulary_once_it_has_them`, 남은 대기 축과 README 표의 일치는 `Readme.test_pending_axis_table_matches_the_schemas`); "필드 삭제 자체 시험 실패"(`compat_check_selftest_detects_a_deleted_field`); 시험 전용 표시·스켈레톤 비노출(`every_fixture_satisfies_the_cross_field_checks_and_is_test_only`, `test_fixtures_are_marked_test_only`: origin이 있는 픽스처는 전부 `origin=fixture`(이제 enum `AssertionOrigin::Fixture`), accepted·comparison_eligible 없음).

### `vocab_check.log` — 어휘 정본 검사(T-CT-02 tests[] 1번)

- 명령: `python3 tools/vocab_check.py`
- 종료 코드: **0**
- 결과: `vocabulary ok: 45 axes, 228 values` (1.5.0은 33 axes, 177 values). 생성 문서 `docs/blueprint/VOCABULARY.md`가 어휘와 바이트 단위로 같다는 확인을 포함한다. 1.5.0 대비 순수 추가인지는 같은 도구의 `--additive-since <1.5.0 사본>`이 검사한다(`+12 axes, +51 values, nothing removed/renamed/reworded`; 이 호출은 origin/main의 사본이 필요해 로그에 넣지 않았고 `generic_checks.log`의 범위 밖이다). T-CT-02 tests[] 2번 `cargo test -p onjeon-rules-engine --test vocabulary`는 `generic_checks.log`의 `cargo test --all` 안에서 돈다(`Running tests/vocabulary.rs` 줄).

### `check_compat.log` — 호환 검사(`<prev_tag>` 형식) + 자체 시험

- 명령 4개와 종료 코드: `git tag --list 'contracts-*'` → 출력 없음(태그 없음), 0 · `bash packages/schemas/codegen/check_compat.sh --selftest` → **0**, `self-test ok` · `bash packages/schemas/codegen/check_compat.sh contracts-0.1.0` → **0**, `BASELINE: no contracts-* tag exists yet (first release); nothing to compare with.` 뒤 자체 시험 `self-test ok` · `ONJ_REQUIRE_BASELINE=1 bash … contracts-0.1.0` → **2**(의도된 거부: 태그가 생긴 뒤 CI가 쓸 형식이며 첫 릴리스 통과를 막는다)
- 자체 시험이 증명한 것: `Assertion.created_by_run`을 지운 변이 스키마에 대해 (1) 구조 비교가 `field removed`로 실패하고 (2) 이전 생성 Rust 클라이언트가 새 문서를 읽는 컴파일 탐침이 `missing field`로 실패한다. 같은 스키마끼리는 둘 다 통과한다(어휘 1.6.0의 enum `$ref` 열두 필드를 포함해서).
- **UNVERIFIED (실제 태그 대비):** 저장소에 `contracts-*` 태그가 하나도 없어 **실제 이전 태그와의 비교는 한 번도 일어나지 않았다.** 따라서 T-CT-02가 바꾼 전송 형태(`ErrorResponse.error_class` 글자 → 낱말, 열한 필드 문자열 → enum, §7)에 대한 호환 판정도 없다. 태그 경로 자체는 `codegen/tests/test_compat.py` `CheckCompatScript`가 임시 저장소에 합성 태그 `contracts-0.1.0`을 찍어 돌린다(위 `cargo_test.log`의 파이썬 묶음에 포함).

### `rule02.log` — 엔진 round-trip이 공허하지 않음

- 명령 2개: `ONJ_REQUIRE_RULE_02=1 cargo test -p onjeon-contracts` → **0** · `ONJ_REQUIRE_RULE_02=1 cargo test -p onjeon-contracts rule_02 -- --nocapture` → **0**
- 결과: `rule_02_contract_effects_round_trip_when_the_engine_supports_them ... ok`. 두 번째 명령은 stderr를 가로채지 않으므로 엔진이 rule-0.2를 거부했다면 찍혔을 건너뜀 메시지가 보였을 자리인데 없다. 즉 엔진(origin/main 병합분)이 탐침 규칙을 적재해 `applies`·`none`·`undetermined` 세 모양을 실제로 평가했고 `EvaluationResult`로 왕복했다. `ONJ_REQUIRE_RULE_02=1`은 건너뜀을 실패로 바꾸므로 이 통과는 건너뜀이 아니다.

### `generic_checks.log` — 저장소 공통 시험 명령(CI와 같은 단계)

- 명령: `cargo fmt --all -- --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test --all`, `python3 -m unittest discover -s tools/tests`, `python3 tools/vocab_check.py`, `python3 tools/validation_check.py`(+ `--selftest`), `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py`, `python3 -I packages/schemas/codegen/gen.py --check`
- 종료 코드: 전부 **0**. 긴 출력은 마지막 줄들만 적었다(`tail`; 각 구간 머리에 표시). 전체 출력이 필요한 두 명령은 위의 전용 로그에 있다. `cargo test --all`에는 규칙 엔진의 `tests/vocabulary.rs`(어휘 정본을 읽는 다른 crate의 시험)와 계약 crate가 함께 들어 있다. `tools/tests`의 `skipped=6`은 이 패키지와 무관하다: 로컬 원본 보관소·pdftotext가 없어 건너뛰는 시험 3개, `ONJEON_ARCHIVE_RAW` 미설정 2개, 설치된 botocore가 If-None-Match를 지원해 대체 경로 시험을 건너뛰는 1개. CI의 같은 단계처럼 `boto3==1.43.100`을 설치한 뒤 돌렸다.

## 4. 치환과 누출 확인

- 치환(sed): 실행 머신의 작업 트리 절대 경로 → `<repo>`, 같은 작업 루트 아래의 다른 절대 경로 → `<path>`, 사용자 홈 디렉터리 → `<home>`. 실제로 치환된 줄: **0**(로그에 그런 경로가 없었다; 규칙은 그래도 적용했다). `/tmp/…`는 임시 설치한 도구 위치라 그대로 두었다.
- 확인(grep, 0건): 절대 경로(작업 루트·홈 디렉터리 접두어), 모델 계열 이름·버전 문자열, 비밀값 형태(클라우드 액세스 키, API 키 접두어, PRIVATE KEY 블록, 저장소 토큰), cargo 잠금 대기 메시지.
- `cargo_test.log`·`rule02.log` 안에서 도는 `test_evidence.py`는 그 실행 **직전**의 이 디렉터리를 읽었다(T-CT-01의 통과 로그를 자리에 둔 채 새 로그는 임시 파일에 받아 실행이 끝난 뒤 옮겼다). 로그가 자기 자신을 담을 수는 없으므로, 커밋된 최종 파일은 대상 SHA에서 묶음을 다시 돌려 검사한다. `generic_checks.log`는 이 색인을 쓴 뒤 마지막으로 만들었다.
- 상시 검사: `codegen/tests/test_evidence.py`가 경로·비밀값·`이름-숫자.숫자` 꼴 버전 식별자·잠금 메시지·로그 완전성(명령 줄, 종료 코드, 통과 문구)을 검사한다. 모델 계열 이름은 그 시험에 적지 않았다(커밋 파일에 그 이름을 적는 것 자체가 막으려는 노출이다). 그 부분은 이번 라운드에 손으로 grep했다.

## 5. PR 템플릿 항목

### T-CT-02 (이 라운드)

- **정보 비대칭(A)**: A1~A6 전부에 걸친 상태 이름. 근거 역할(`evidence_role`)·범위 관계(`scope_relation`)·사실 출처와 확인 주체(`fact_source`·`confirm_party`)·지식 최신성과 사용 제한(`knowledge_freshness`·`usage_restriction`)이 화면과 API가 같은 낱말로 "왜 이 결과가 보류인가, 이 값은 어디서 왔나"를 말하게 한다.
- **소비자 질문(Q)**: 직접 해결하는 질문은 없다. 결과가 보류·정정·제한된 이유를 묻는 질문(Q2·Q5 계열)의 답에 쓰일 상태 이름을 고정한다.
- **계층(L)**: 축마다 어휘의 `layer` 필드(L2~L4). 계약 적응은 L8(화면이 받는 형식)·L6(`EvaluationResult`)·L3(`Assertion`·`PremiumObservation`) 타입의 모양만 바꾼다.
- **불변식(I)**: 미확인은 성공이 아니다(`need_verdict.hold`, `knowledge_freshness.stale`은 정상 결과이지 오류 클래스가 아니다); `origin=fixture`는 절대 accepted가 아니다(이제 enum으로 고정, `chk_fixture_never_accepted`).
- **마일스톤(M)**: M1(S0 계약·어휘).
- **요구 ID(R)**: R08(근거 없는 AI 결과 차단 — `assertion_origin`·`evidence_role`), R15(내 계약 정확히 이해 — `fact_source`·`confirm_party`·`fact_kind`), R21(최신성과 변경 이유 — `knowledge_freshness`·`correction_reason`), R22(잘못된 결과 복구 — `usage_restriction`·`error_class`). 요구의 충족이 아니라 그 상태를 부르는 이름이다.
- **관련 결정**: DEC-CANON-T-CT-02(정본 변경 승인, `canon_change_approval`), ADR-0011, ADR-0012. 입력: 02_구현계약 §1.2·§1.4·§1.5·§4.2, 온톨로지 설계안 §13, BLUEPRINT §6·§10.2.
- **설계 변경인가**: 어휘는 추가만(삭제·개명·재서술 없음, `vocab_check.py --additive-since`). 계약 쪽은 T-CT-01이 설계해 둔 승격 경로(`x-onjeon-pending-axis` → `$ref`)의 실행이다. 그 안의 선택: `error_class` 전송값을 어휘 낱말로(글자↔낱말 대응은 `checks.rs`), 객체 정의 `ScopeRelation` → `ScopeRelationEntry`(타입 이름만, 필드·전송 형태 불변), `Assertion.correction_reason` 자유 문자열 → 어휘 enum(§7).
- **데이터·스키마·라벨·규칙·API 영향**: 어휘 1.6.0; JSON Schema 9개 파일, 생성 Rust·TS·Dart; 규칙 엔진 코드 불변(어휘 시험 통과). 저장된 데이터 없음(S0).
- **화면 표시 변화**: 없음(앱 없음). 새 값의 `screen_ko`는 정본에 있으나 어느 화면도 아직 쓰지 않는다. **기존 결과·버전·캐시·개인정보 영향**: 없음. 픽스처는 전부 `origin=fixture`, 개인 데이터 없음.
- **과제 ID**: T-CT-02.
- **작성에 참여한 모델 역할·실행 경로**: 구현 역할(implementer)이 감독자가 연 과제 전용 워크트리에서 과제 사양·운영자 점검표(2026-10-16 23:15 KST, 2026-10-17 12:20 KST)에 따라 자동 실행한 라운드(앞선 라운드는 다른 계열의 구현 역할). 리뷰 역할은 작성 계열이 아닌 독립 리뷰어이며 감독자가 대상 SHA에 고정한다. 모델 계열·버전은 식별자 비노출 규칙에 따라 여기 적지 않는다(감독자 기록에 있다).
- **대상 SHA**: 감독자가 채운다. 독립 리뷰의 SHA 고정도 감독자 몫이다.
- **수락 사례와 기대 결과**: 기존 값 무삭제·무개명 ↔ `vocab_check.py --additive-since`(§3 `vocab_check.log` 항목); 새 값마다 정의·화면 문구 ↔ `vocab_check.py`의 `validate()`가 빈 `concept_ko`·`screen_ko`를 거부(`vocab_check.log`); 생성 문서 최신 ↔ `vocab_check.log`(바이트 비교); enum은 어휘에서만 ↔ `cargo_test.log`; 세 언어 빌드 ↔ `build_check.log`.
- **실제 수행한 검증**: §3 전부, 이 트리에서, 마지막 코드 변경 뒤에.
- **합성 / 실제 원문 / 사용자 검증**: 합성만(픽스처, `origin=fixture`). 실제 원문 검증·사용자 검증 없음.
- **미정·지원하지 않는 동작**: §6.

### T-CT-01 (디렉터리를 만든 과제, 요약)

- A1~A6의 전송 형태; Q7(EvidenceView); L8·L6·L7·L3의 모양; I4(금액 정수 원 — `test_money_is_integer_krw`, `no_wire_type_exposes_floating_point_money`), I6·I7·I8·I12의 형태만; M1; R07, R10, R11, R13, R14, R16, R17(형태 고정, 충족 아님); ADR-0011, ADR-0012. 새 crate `onjeon-contracts`, JSON Schema 13개(어휘 스키마 1개는 생성물), 생성 TS·Dart 패키지, 규칙 엔진은 dev-dependency로 소비만. 그 라운드의 변경 목록은 그 PR(#102)에 있다.

## 6. 건너뜀·공허·미검증 (숨기지 않는다)

1. **실제 이전 태그와의 호환 비교는 하지 않았다.** `contracts-*` 태그가 없다. 태그는 릴리스 절차가 찍는다. UNVERIFIED. 그래서 T-CT-02의 전송 형태 변경(§7)도 호환 판정 없이 들어간다. 1.5.0 생성물을 쓰는 클라이언트는 없다(앱 없음, 태그 없음).
2. **CI는 TypeScript·Dart를 빌드하지 않는다.** CI 단계 연결(`.github/workflows/`)은 이 과제의 허용 경로 밖이다(구현자 관리). 세 언어 빌드의 근거는 이 VM에서의 `build_check.log` 1회 실행뿐이다.
3. 호환 컴파일 탐침은 Rust만이다. TypeScript·Dart는 현재 스키마의 빌드·픽스처 확인만 하고 이전 태그 생성물로의 교차 컴파일은 없다.
4. 어휘 승격 대기 축(`x-onjeon-pending-axis`)은 1.6.0 뒤에도 **18개, 필드 21개** 남아 있다(README 표). 닫힌 enum이 아니라 소문자 snake_case 패턴 문자열이다. 축이 어휘에 들어오면 lint가 실패해 `$ref`로 바꾸게 한다(이번 라운드가 그 경로로 아홉 축·열한 필드를 옮겼다).
5. 생성 클라이언트는 `pattern`·`minimum`·`minItems`를 강제하지 않는다(시험용 `validate.py`만). Dart `fromJson`은 필수-nullable 키의 부재와 null을 구분하지 않는다.
6. 의미 검사(릴리스 빌더, DB 제약, evidence_ref 파서, OpenAPI, 오류 코드 표, 이벤트)는 T-CT-03~05·T-KN-* 몫이다. `ErrorResponse`는 형태만 있다. `error_class` 낱말과 `code` 글자의 대응표는 `checks.rs`에 있고 오류 코드 표(T-CT-04)가 이를 흡수해야 한다.
7. 로그 신선도는 수동이다: 대상 SHA에서 `tree_hash.sh` 값을 §1과 대조한다. `test_evidence.py`는 형식·통과·누출만 본다.
8. 실행은 한 머신에서 1회다. 재현은 트리 해시가 같은 체크아웃에서 같은 명령으로 한다.
9. `rule_02_…` 시험은 엔진이 rule-0.2를 거부하는 체크아웃에서는 건너뜀 메시지를 찍고 통과한다(공허). 이 트리에서는 공허하지 않음을 `rule02.log`로 보였다. CI가 `ONJ_REQUIRE_RULE_02=1`로 불러 건너뜀을 실패로 만드는 단계는 연결되지 않았다(§6-2와 같은 이유).
10. 독립 리뷰의 SHA 고정과 최종 대상 SHA는 이 파일에 없다(감독자).
11. 02가 닫지 않은 항목(주장 ID 표기 `a:`/`assertion:`, `release_hash`↔`content_sha256`, `need_result.id` 형식, `special_conditions`·`usage_counters` 항목 형식, `judged_by` 값 집합)은 자리만 두었다. `scope_relation`은 어휘 1.6.0이 닫았다.
12. 어휘 1.6.0의 값 가운데 출처가 글자·한국어 표기뿐이어서 영문 코드가 작성자의 명명인 것: `error_class`(출처는 V A N S L U X T), `correction_reason`(출처는 한국어 표기 네 개). `doc_role.disclosure_list`·`guide_page`는 02 §1.1의 문서 역할 목록에서 왔고 기존 `disclosure_page`와 겹칠 수 있다. `doc_role.applies_to`는 재서술 금지 규칙 때문에 그대로다. 열린 항목으로 남긴다.
13. 어휘 1.6.0의 `fact_kind`·`criterion_source_kind`와 `doc_role`의 새 값은 이 패키지의 스키마에 해당 필드가 없어 생성물에 enum 타입으로만 들어간다(쓰는 필드 없음).
14. **경로 범위.** §7의 계약 쪽 변경은 T-CT-02의 원래 허용 경로(`vocabulary.json`, `VOCABULARY.md`, `vocab_check.py`) 밖이었다. 어휘 1.6.0과 계약 적응은 서로를 요구한다(어휘만 넣으면 T-CT-01의 lint가 `cargo test --all`을 실패시키고, 계약만 바꾸면 없는 축을 `$ref`해 lint가 실패한다). 그래서 한 PR에 있어야 하고, 운영자가 2026-10-17 12:20 KST에 허용 경로를 이 변경이 닿는 파생물·시험·증거 파일로만 좁게 확장했다(`json/*.schema.json`, `src/generated/*.rs`, `checks.rs`, `tests.rs`, 생성 Dart·TS의 types·vocabulary, `test_compat.py`, `test_schemas.py`, 픽스처, 이 디렉터리, 패키지 README). 정본 변경 승인 범위(`canon_change_approval`: 추가만)는 그대로이고 금지 경로도 바뀌지 않았다. 이 PR이 origin/main과 다른 파일 31개는 전부 그 확장된 허용 경로 안이며 금지 경로는 하나도 없다.

## 7. 이 라운드의 변경(T-CT-02)

어휘(허용 경로 안):

- `packages/schemas/vocabulary.json`: 1.6.0. 새 축 12개(`evidence_role`, `scope_relation`, `correction_reason`, `assertion_origin`, `fact_source`, `fact_kind`, `confirm_party`, `error_class`, `usage_restriction`, `knowledge_freshness`, `need_verdict`, `criterion_source_kind`), `doc_role` 값 2개(`disclosure_list`, `guide_page`). 값마다 `concept_ko`·`screen_ko`. 삭제·개명·재서술 없음.
- `docs/blueprint/VOCABULARY.md`: `python3 tools/vocab_check.py --write`로 재생성.
- `tools/vocab_check.py`: `validate()`가 축 id 형식과 빈 `concept_ko`·`screen_ko`(null은 '화면 비표시'로 허용)를 거부; `--additive-since <baseline>`(기존 축·값·정의·화면 문구·별칭·규칙 줄 불변, 내용이 바뀌면 버전 상승 요구).

계약 적응(2026-10-17 12:20 KST에 확장된 허용 경로 안, §6-14):

- `json/*.schema.json`(9개 파일): 열한 개 대기 필드를 `vocabulary.schema.json#/$defs/<축>` `$ref`로(README '1.6.0에서 승격된 축' 표). `compare_view.schema.json`의 객체 정의 `ScopeRelation` → `ScopeRelationEntry`(어휘 축 enum `ScopeRelation`과 이름 충돌). `assertion.schema.json`의 `correction_reason`도 `$ref`로(lint 요구는 아님; 어휘가 `applies_to`를 Assertion으로 정했다).
- `json/vocabulary.schema.json`, `src/generated/*.rs`, `codegen/generated/ts/*.ts`, `codegen/generated/dart/lib/src/*.dart`: `gen.sh`로 재생성(생성물 14개).
- `src/checks.rs`: `ORIGIN_FIXTURE`가 `AssertionOrigin::Fixture`; `error_class_letter`·`error_class_for_letter`(`VANSLUXT` ↔ 어휘 낱말)와 그것을 쓰는 `check_error_response`.
- `src/tests.rs`: enum 사용으로 갱신, 시험 3개 추가(§3 `cargo_test.log`).
- `codegen/tests/test_schemas.py`: 대기 축 승격 시험이 `need_verdict` 대신 아직 대기 중인 `judged_by`를 쓴다. `codegen/tests/test_compat.py`: 타입 변경 변이의 대상이 자유 문자열이 아니게 된 `Assertion.correction_reason` 대신 `CoverageDetail.title`.
- `codegen/tests/fixtures/`: `ErrorResponse`(`"V"` → `"validation"`), `CompareView`(`"superset"` → `"broader"`), `Assertion.value`(`correction_reason` 자유 문자열 → `error_correction`).
- `README.md`(packages/schemas): 어휘 1.6.0, 남은 대기 축 표(18개), '1.6.0에서 승격된 축' 절.
- 이 디렉터리: 로그 6개 전부 재생성, 이 색인.
