# T-CT-04 증거 색인 (`packages/schemas/codegen/evidence/ct04/`)

과제 **T-CT-04**: 오류 코드(C-22), 분석 이벤트 허용 목록(C-17), 도메인 이벤트 스키마(C-21), evidence_ref 문법 검사기, 계약 패키지 버전 고정(C-23). 구역 contracts, 단계 S0. 리뷰어는 PR 본문이 아니라 대상 SHA에 커밋된 이 파일들을 읽는다. 각 로그의 첫 줄이 명령(`$ …`), 마지막 줄이 `exit code: N`이다. 로그 본문은 손으로 고치지 않았고 실행 머신의 작업 트리 절대 경로 한 곳만 `<repo>`로 바꿨다(cargo가 찍는 크레이트 경로). 상위 디렉터리의 `EVIDENCE.md`와 다른 과제의 로그(`ct03/`)는 이 과제가 건드리지 않았다.

## 1. 로그를 만든 트리

| 항목 | 값 |
|---|---|
| 과제 ID | T-CT-04 (fix round 4) |
| 작성 | 모델 역할: 구현자(작성 계열). 실행 경로: 감독자가 띄운 격리 작업 트리(worktree)에서 에이전트가 직접 명령 실행. 리뷰어는 별도 계열 |
| 부모 커밋(로그 생성 시 HEAD) | `3ee000b3f45844fef857ff251f505a00392f299d`(main 그대로, T-CT-06의 `tools/ci` 포함) + 이 과제의 변경(커밋·푸시는 감독자) |
| `packages/schemas` 트리 sha256 (`codegen/evidence/` 제외) | `bb2ff999d7348cb71af9c2fa28f5fb736b82dae1e0aa10904f414fedf136280a` |
| 계산 명령 | `bash packages/schemas/codegen/tree_hash.sh` (`tree_hash.log`) |
| 대상 SHA(PR head) | **감독자가 채운다.** 그 커밋에서 `tree_hash.sh`가 위 값을 내면 이 로그는 그 커밋의 코드에서 나온 것이다. 다르면 낡은 로그이므로 §3 명령을 다시 돌린다 |
| 실행 일시 | 2026-10-18 (VM 시계, UTC 00시대) |

이 과제가 바꾼 경로(전부 allowed_paths 안): `packages/schemas/errors.json`, `packages/schemas/analytics-events.json`, `packages/schemas/events/**`(색인 1 + 스키마 21), `packages/schemas/evidence_ref.md`, `packages/schemas/src/{lib.rs, allowlist.rs, errors.rs, events.rs, evidence_ref.rs}`, `packages/schemas/codegen/check_allowlist.py`, `packages/schemas/codegen/tests/test_allowlist.py`, `packages/schemas/codegen/evidence/ct04/**`(이 디렉터리). 앞선 라운드가 막힌 이유는 `check_allowlist.py`·`test_allowlist.py`가 allowed_paths 밖이었기 때문이며, 이번 라운드에서 두 경로와 `evidence/ct04/**`가 허용 목록에 들어왔다. 작업 내용은 그대로 두고 검증만 다시 했다.

## 2. 도구 버전

cargo 1.99.1, rustc 1.99.1, clippy 0.1.99, rustfmt 1.10.0, python3 3.13.5(`-I`). TypeScript·Dart 도구는 이 과제의 명령에 쓰이지 않는다(생성물을 바꾸지 않았다).

## 3. 로그별 명령·결과

| 로그 | 명령 | 종료 | 결과 |
|---|---|---|---|
| `tree_hash.log` | `bash packages/schemas/codegen/tree_hash.sh` | 0 | §1의 트리 해시 |
| `check_allowlist.log` | `python3 -I packages/schemas/codegen/check_allowlist.py`(과제 tests 명령), 같은 명령 `--selftest` | 0 | 허용 목록 12 이벤트·7 필드, 유효 예제 5개 통과·거부 예제 9개 거부, `PASSED`. 자체 시험: 심은 결함 8개가 각각 의도한 이유로 실패 |
| `evidence_ref_test.log` | `cargo test -p onjeon-contracts evidence_ref`(과제 tests 명령) | 0 | 8개 통과: 열 종류 왕복, 조항 변형 왕복, 잘못된 입력 거부, 문법 밖 검증, 스키마 정규식과 일치, 픽스처 ID 변환·거부 |
| `cargo_test_all.log` | `cargo test --all`(CI와 같은 명령) | 0 | 전부 통과. `onjeon_contracts` 54개(errors 8·allowlist 7·events 6·evidence_ref 8 + 기존 25)에는 파이썬 시험 묶음 실행(`python_codegen_suite_passes`)이 들어 있다 |
| `lint_fmt.log` | `cargo clippy --all-targets -- -D warnings`, `cargo fmt --all -- --check` | 0 | 경고 없음(두 크레이트를 `cargo clean -p`로 지운 뒤 돌려 `Checking` 줄이 보인다) |
| `python_tests.log` | `python3 -I -m unittest discover -s packages/schemas/codegen/tests -v` | 0 | 129개 OK: 기존 104개 + `test_allowlist.py` 25개(허용 목록·값 모양·심은 결함·명령줄·이 디렉터리의 완전성) |
| `tools_tests.log` | `python3 -I -m unittest discover -s tools/tests`, `python3 -I -m unittest discover -s tools/ci/tests` | 0 | 388개 OK(건너뜀 21개는 외부 서비스·선택 의존 시험으로 이 과제와 무관), 20개 OK |
| `leak_skeleton.log` | `python3 -I tools/ci/check_leak.py`, `python3 -I tools/ci/check_skeleton.py` | 0 | 누출 패턴 없음(I10·I11·§52.3), 스켈레톤 플래그 꺼짐·비노출(정적). 서버가 없어 `--base-url` 실행 검사는 해당 없음 |

## 4. 수락 항목 대응

- **허용 목록 밖 필드를 가진 이벤트 예제가 검사에서 실패한다.** `analytics-events.json`의 `examples.rejected` 9개(계약 금액·담보 명·사용자 식별자·자유 입력·어휘 밖 값·다른 이벤트 전용 필드·목록 밖 이벤트)를 Rust(`allowlist_listed_examples_pass_and_fail_as_declared`, `allowlist_event_with_a_field_outside_the_list_fails`)와 Python(`test_examples_pass_and_fail_as_declared`, `test_a_field_outside_the_list_fails_and_is_named`, `test_fails_on_a_leaking_copy`)이 똑같이 거부한다. 실패 메시지는 필드 이름과 금지 범주를 댄다. `check_allowlist.log`, `cargo_test_all.log`, `python_tests.log`.
- **evidence_ref 전 종류가 왕복 파싱된다.** 02 §6.1의 열 가지 생성 규칙(`seg`·`clause`·`ted`·`premium`·`assertion`·`rule`·`obs`·`raw`·`eval`·`crit`)을 `RefKind::ALL`로 고정하고 `evidence_ref_every_kind_round_trips`가 종류마다 `parse` → `Display`가 바이트 그대로인지 확인한다. 조항의 좌표 유무·구획 페이지 범위 변형은 `evidence_ref_clause_variants_round_trip`. Rust 문법과 `json/common.schema.json`의 정규식이 같은 열 모양인지는 `evidence_ref_matches_the_schema_alternatives`. `evidence_ref_test.log`.
- **오류 코드마다 화면 상태 매핑이 있다.** `errors.json`의 12개 코드(02 §4.2 표 전부) 각각에 `screen_state`(§44.2의 부분·판단 불가·오류·변경됨 + 02 §4.2의 운영 오류)와 `screen_ko`가 있고, `errors_every_code_maps_to_a_screen_state`가 빠진 코드를 잡는다(`errors_unmapped_screen_state_is_reported`가 '넣으면 실패'). 클래스 글자 ↔ 어휘 `error_class` 대응은 `checks.rs`와 일치한다(`errors_class_letters_name_their_vocabulary_values`). `cargo_test_all.log`.
- **계약 패키지 버전 고정(C-23).** `errors.json`·`analytics-events.json`·`events/index.json`의 `contracts_version`이 `packages/schemas/Cargo.toml`의 `version`과 같아야 하며, 어긋나면 Rust(`*_file_is_consistent`)와 Python(`test_contracts_version_is_the_crate_version`, 자체 시험 'version drift')이 실패한다.
- **도메인 이벤트 스키마(C-21).** 02 §3.1의 21개 이벤트(보내지 않는 `personal.denominator_signal`은 `not_sent`로만 기록) 각각 스키마 한 파일·색인 한 항목·예제 하나. `events_examples_validate`가 예제를 스키마로 검사하고 `events_reject_extra_missing_and_wrong_shape`가 필드 추가·누락·모양 오류를 거부하며 `events_personal_ids_stay_on_the_personal_queue`가 개인 ID가 개인 큐 밖 이벤트에 없음을 확인한다.
- **PR 템플릿의 A·Q·L·I·M과 R 요구 ID.** PR 본문은 감독자가 쓴다. 초안은 §6.
- **과제 ID, 모델 역할·실행 경로, 대상 SHA.** §1.
- **tests의 명령을 실행하고 로그를 첨부했다.** 과제의 tests 두 명령이 `check_allowlist.log`·`evidence_ref_test.log`의 첫 줄이며, `test_allowlist.py`의 `Ct04Evidence`가 그 두 명령이 이 디렉터리 로그에 있는지, 로그마다 종료 코드 0인지, 색인에 이름이 있는지 검사한다.
- **시안 숫자·임시 데이터·미연결 경로가 제품 코드에 없다.** 계약 파일의 숫자는 02에서 온 것(HTTP 상태, 날짜 범위 1900~2199, 코드 번호)뿐이다. JSON의 `examples`·`example`은 시험이 읽는 예제이고 서비스 데이터가 아니다. 픽스처 ID 변환 결과는 항상 `origin=fixture`(`FixtureRef::ORIGIN`)이며 변환이 fixture를 승격하지 않는다(02 §8).
- **스켈레톤 비노출 시험과 누출 정적 검사가 통과한다.** `leak_skeleton.log`(T-CT-06 도구, main 기준). 한계는 §5.
- **독립 리뷰가 대상 SHA에 고정되어 있고 리뷰어는 작성 계열이 아니다.** 리뷰어의 몫. 이 색인의 트리 해시로 리뷰 대상이 이 로그의 트리인지 확인한다.
- **비밀값·모델 식별자 원문·원문 발췌를 포함하지 않는다.** `test_evidence.py`의 `test_no_leaks`가 이 디렉터리까지 재귀로 검사한다(`python_tests.log`). 약관 원문 발췌는 없고 예제의 문자열은 합성이다.
- **allowed_paths 밖을 수정하지 않았다.** §1의 경로 목록 = `git status`의 전부. `infra/ci/deps.json`·`tools/ci/**`·`test_evidence.py`·`README.md`는 손대지 않았다(§5).

## 5. 한계와 열린 항목

- `infra/ci/deps.json`의 `leak.analytics.allowed_fields`는 비어 있다(T-CT-06 README: "이벤트 스키마를 정하는 과제가 채운다"). 그 파일은 이 과제의 allowed_paths 밖이라 채우지 못했다. 오늘 `check_leak.py`가 통과한 것은 코드에 분석 호출이 아직 없기 때문이다. 후속: `allowed_fields`에 `analytics-events.json`의 7개 필드를 넣거나 `check_leak.py`가 `check_allowlist.py`의 `AllowList.is_allowed_field`를 읽게 한다(구현자 또는 T-CT-06 후속).
- 02 §5 마지막 행의 `ONJ-AP-S`(앱 지원 범위 밖) 오류는 번호가 없어 코드로 넣지 않았다. `message_key`는 키 이름만 정했고 문구 사전은 앱의 몫이다(`errors.json` `open_items_ko`).
- 분석 이벤트의 세션 난수는 허용 필드로 두지 않았고, `state_code`의 어휘 축 네 개는 02가 "등"으로 비워 둔 범위를 이 과제가 정한 것이다(`analytics-events.json` `open_items_ko`).
- 도메인 이벤트 색인의 `publisher`는 한 값이며 02가 두 발행자를 적은 행(`ops.circuit_breaker.*`, `knowledge.task.updated`)은 `note_ko`에 다른 발행자를 적었다. `state`·일부 ID의 값 집합은 02에 없어 Identifier로 두었다(`events/index.json` `open_items_ko`).
- `Ct04Evidence` 시험은 `test_evidence.py`(allowed_paths 밖)가 아니라 `test_allowlist.py`에 있다. `python_tests.log`·`cargo_test_all.log`는 자기 자신을 담을 수 없으므로, 두 로그는 다른 로그와 이 색인을 먼저 둔 뒤 만들었고 최종 디렉터리에서 같은 시험을 다시 돌려 통과를 확인했다(로그 없음, 리뷰어가 대상 SHA에서 재현).
- 생성물(`src/generated/**`, `codegen/generated/**`)과 OpenAPI는 바꾸지 않았다. `gen.sh --check`·`build_check.sh`는 `cargo test --all` 안의 `generated_files_are_up_to_date`가 전자를 확인하고, 후자는 T-CT-03의 로그가 그대로 유효하다(세 언어 생성물에 변화 없음).

## 6. PR 본문 초안 (감독자가 옮겨 적는다)

- 정보 비대칭(A)·소비자 질문(Q)·계층(L)·불변식(I)·마일스톤(M): A1~A6 공통 기반(직접 해결하는 질문 없음), Q7(이 숫자는 어디서 왔나: `evidence_ref`가 근거 사슬의 참조 형식), L8(화면·API가 받는 계약 형식; `evidence_ref`는 L1·L2·L6·L7의 ID를 가리킨다), I2(결과가 규칙 판·릴리스·해시·근거를 갖는다: `rule_ref`·`eval_ref`), I6(근거 사슬), I11(분석 허용 목록이 민감 값을 막는다), I16(릴리스 불변: `knowledge.release.*` 이벤트), M1(데이터 척추).
- 요구 ID(R): R04(원문 보존: `raw_ref`·`obs_ref`·`data.raw.archived`), R08(근거 없는 결과 차단: `knowledge.review.decided`·`ONJ-KN-S-050`), R17(설명 가능한 계산: `rule_ref`·`eval_ref`), R21(변경 이유: `ONJ-AP-N-002` '변경됨'·`knowledge.release.*`), R22(잘못된 결과 복구: `knowledge.assertion.superseded`·`conflict.*`·S 클래스 오류), R23(개인자료 최소화: 분석 허용 목록·개인 큐 분리). 과제 그래프의 required_test_ids는 없음.
- 관련 결정: C-17·C-21·C-22·C-23(02_구현계약 §3·§4·§5·§6), ADR-0011·0012. 설계 변경이 아니라 기존 설계(02 검토용 묶음)의 구현이며 02가 비워 둔 곳은 §5처럼 열린 항목으로 적었다.
- 데이터·스키마 영향: 계약 파일 3종과 이벤트 스키마 21개 추가, 크레이트에 모듈 4개 추가. 생성물·OpenAPI·어휘 정본 변경 없음. 화면 표시 변화 없음(화면 상태 매핑은 표일 뿐이다). 개인정보: 분석 허용 목록과 개인 큐 분리가 경계를 좁힐 뿐 넓히지 않는다.
- 검증: §3의 로그. 합성 검증만이며 실제 원문·사용자 검증은 해당 없음. 미지원: §5.
