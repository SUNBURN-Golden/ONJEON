# Audit 3: 정확한 0 채움 날짜 형식 재검증

검증일: 2026-10-28. 노드: `audit3-engine-parse-date-strict`.
BLUEPRINT A2·A5, Q2·Q5·Q7, L6, I18, M0 엔진 유지보수와
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P08·P14에 연결된다.

## 발견 판정과 변경

`2026-+1-+5`를 허용하던 문제는 이 작업 시작 시점에
[Audit 2 수정](2026-10-26_engine_parse_date_plus_sign.md)으로 이미 해결돼 있었다.
[공통 파서](../../../packages/rules-engine/src/date.rs)는 길이 10바이트,
고정 위치의 `-`, 연·월·일 전체의 ASCII 숫자 여부를 검사한 뒤 정수 변환과
1900~2199년 범위·달력 유효성 검사를 수행한다. 따라서 월·일은 정확히 두 자리여야 한다.
이번 작업은 기존 실행 로직을 유지하고 계약 주석과 회귀 시험·실행 증거를 보강했다.

[date_format.rs](../../../packages/rules-engine/tests/date_format.rs)는 두 DSL 버전에서
17개 비정상 표기(감리 예시, 한쪽 부호, 연도 부호, 0 채움 누락·과잉, 잘못된 구분자,
공백·개행, 전각·아라비아 인도 숫자)를 날짜 리터럴과 평가 입력으로 각각 검사한다.
리터럴은 `eligibility.eq[1].date`의 `RuleError`, 입력은 `event_date`의
`EvalError::BadInput`으로 거부돼야 한다. 기존 단위 시험에도 감리 예시와 정상 대응 날짜를 추가했다.

새 해시 경로 시험은 정상 날짜 `2026-01-05`의 JSON 재로드·평가 결과에 같은 내용 해시가
붙는지 확인한다. 날짜 값만 비정상 표기로 교체하면 JSON 텍스트 로드가 실패해야 한다.
`+`를 `\u002b`로 이스케이프해도 같다. 잘못된 날짜를 같은 논리의 다른 해시로 받아들이지
않으며, 기존 내용 해시 계산 방식과 골든 고정값은 변경하지 않았다.
정상 날짜·윤일·지원 경계의 지급 결과도 유지한다.

## 직접 실행한 검증

로컬 rustc/cargo 1.98.1, 오프라인 검증이다. Cargo 산출물은 이 작업 트리 내부의
`target/`에 생성했다. 원격 CI 결과를 주장하지 않는다.
로그 위치: [tools/evidence/audit3-engine-parse-date-strict/](../../../tools/evidence/audit3-engine-parse-date-strict/).

| 명령 | 결과·증거 |
|---|---|
| `cargo test -p onjeon-rules-engine --locked --offline --lib --test date_format` | 단위 10개·통합 4개 통과: [focused.log](../../../tools/evidence/audit3-engine-parse-date-strict/focused.log) |
| `python3 -I tools/evidence/audit3-engine-parse-date-strict/negative_control.py` | 임시 크레이트의 정상 파서는 4개 통과. ASCII 숫자 검사만 제거하면 로드·입력·해시 거부 시험 3개가 실패(기대 종료 코드 101), 정상 날짜 시험 1개는 통과: [요약](../../../tools/evidence/audit3-engine-parse-date-strict/negative-control.log), [정상](../../../tools/evidence/audit3-engine-parse-date-strict/control-baseline.log), [변이](../../../tools/evidence/audit3-engine-parse-date-strict/control-permissive.log) |
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 단위·통합·문서 시험 471개 통과, 실패 0, 기존 ignored 1개. 내부 Python 시험 39개·129개 통과. 골든 trace·내용 해시·입력 해시·실제 조항·변이·건전성 및 README 시험 표 포함: [workspace.log](../../../tools/evidence/audit3-engine-parse-date-strict/workspace.log) |
| `cargo fmt --all -- --check` | 종료 코드 0: [fmt.log](../../../tools/evidence/audit3-engine-parse-date-strict/fmt.log) |
| `cargo clippy --all-targets --locked --offline -- -D warnings` | 종료 코드 0: [clippy.log](../../../tools/evidence/audit3-engine-parse-date-strict/clippy.log) |
| `python3 -I tools/blueprint_counts.py --write` 후 `python3 -I tools/blueprint_counts.py` | 엔진 단위·통합 등록 206개, doctest 3개와 일치: [갱신](../../../tools/evidence/audit3-engine-parse-date-strict/counts-write.log), [검사](../../../tools/evidence/audit3-engine-parse-date-strict/counts.log) |
| `python3 -I -m unittest discover -s tools/tests -p test_blueprint_counts.py -v` | 17개 통과: [counts-tests.log](../../../tools/evidence/audit3-engine-parse-date-strict/counts-tests.log) |
| `python3 -I -m unittest discover -s tools/tests -p test_product_purpose.py -v` | 14개 통과: [purpose-tests.log](../../../tools/evidence/audit3-engine-parse-date-strict/purpose-tests.log) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업 연결·필수 시험 등록 정합성 통과: [product-purpose.log](../../../tools/evidence/audit3-engine-parse-date-strict/product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 45/45·존재 검사 72/72 통과: [spec-check.log](../../../tools/evidence/audit3-engine-parse-date-strict/spec-check.log) |
| `python3 -I tools/blueprint_status.py` | 기존 결정 색인 일치: [status.log](../../../tools/evidence/audit3-engine-parse-date-strict/status.log) |

음성 대조는 작업 트리 내부 임시 크레이트만 수정하고 실행 후 삭제한다. 실제 파서와
fixture를 바꾸지 않는다. 새 시험은 기존 CI의 `cargo test --all`에 포함된다.
[scope.log](../../../tools/evidence/audit3-engine-parse-date-strict/scope.log)는 허용 경로,
보호 문서·fixture·실행 파서 불변, 변경 문서의 로컬 링크·diff 공백 검사를 기록한다.

## 제품 목적과 한계

날짜 조건을 계산하는 엔진과 결과의 규칙 식별을 뒷받침하는 `fixture_only` 합성 회귀
증거다. 실제 릴리스의 감액·면책 경계일 시나리오, 화면 숫자→원문 좌표의 근거 사슬,
전 상품 데이터 연결 또는 첫 출시 완료 판정을 대신하지 않는다.
09 §7에 이 증명 범위를 연결하고 BLUEPRINT §11의 엔진 등록 수만 생성기로 갱신했다.
commit·push·GitHub 호출은 수행하지 않았다.

## Fix round 1: 공유 Cargo 캐시의 다른 작업 트리 경로

감독자가 보고한 `fixture_supplements` 실패 2건을
[공유 바이너리 직접 실행](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round1/stale-cache-reproduction.log)으로 재현했다. 상속된
`CARGO_TARGET_DIR=/workspace/onjeon-run/shared-target`의 시험 바이너리는
`CARGO_MANIFEST_DIR`에 삭제된 `_review_2305007_97522277/packages/rules-engine`
경로를 담고 있었다. 따라서 `read_dir`와 fixture 파일 읽기가 `NotFound`로 실패했다.
현재 작업 트리에는 두 fixture 디렉터리와 대상 JSON이 모두 존재한다.
[cache-diagnosis.log](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round1/cache-diagnosis.log)는
공유 바이너리와 이 작업 트리의 바이너리에서 추출한 경로 및 파일 존재 여부를 대조한다.

공유 캐시를 변경하지 않고 이 작업 트리의 `target/`을 사용해 직접 재검증했다.
날짜 파서와 fixture 결합 로직·사례·59개 추가 경계 사례의 필수 개수 검사는 유지했다.
시험을 건너뛰거나 기대값을 완화하지 않았다. 재검증 명령은 아래와 같으며,
Cargo를 실행하는 Python 검사도 `CARGO_TARGET_DIR="$PWD/target"`을 상속했다.
README에 같은 작업 트리별 검증 명령을 기록했다.

음성 대조 스크립트에도 반복 실행 시 이전 변이 바이너리를 정상 대조에서 재사용하는
문제가 있었다. `copy2`가 원본 수정 시간을 보존하는 상태에서 두 대조가 `target/`을
공유했기 때문이다. 스크립트를 수정해 정상·변이 대조 각각이 임시 크레이트 내부의
새 target을 사용하도록 했다. 임시 크레이트 삭제 시 두 target도 함께 삭제된다.
두 번 연속 실행해 정상 파서 4개 통과·숫자 검사 제거 시 거부 시험 3개 실패를 확인했다.

| 명령 | 결과·로그 |
|---|---|
| `CARGO_TARGET_DIR="$PWD/target" cargo test -p onjeon-rules-engine --locked --offline --lib --test date_format --test fixture_supplements` | 단위 10개·날짜 4개·fixture supplement 4개 통과. 보고된 실패 2건 모두 통과: [focused.log](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round1/focused.log) |
| `CARGO_TARGET_DIR="$PWD/target" ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 471개 통과·실패 0·기존 ignored 1개. 내부 Python 시험 39개·129개 통과: [workspace.log](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round1/workspace.log) |
| `cargo fmt --all -- --check` | 통과: [fmt.log](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round1/fmt.log) |
| `CARGO_TARGET_DIR="$PWD/target" cargo clippy --all-targets --locked --offline -- -D warnings` | 통과: [clippy.log](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round1/clippy.log) |
| `python3 -I tools/evidence/audit3-engine-parse-date-strict/negative_control.py` (연속 2회) | 정상 4개 통과·변이 3개 실패를 두 번 확인: [첫 실행](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round1/negative-control.log), [반복 실행](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round1/negative-control-repeat.log). 대조별 상세 출력: [정상](../../../tools/evidence/audit3-engine-parse-date-strict/control-baseline.log), [변이](../../../tools/evidence/audit3-engine-parse-date-strict/control-permissive.log) |
| `CARGO_TARGET_DIR="$PWD/target" python3 -I -m unittest discover -s tools/tests -v` | 1,271개 실행·실패 0·skip 36: [python-tests.log](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round1/python-tests.log) |
| `CARGO_TARGET_DIR="$PWD/target" python3 -I tools/blueprint_counts.py` | 단위·통합 206개·doctest 3개 등록 수 일치: [counts.log](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round1/counts.log) |
| `python3 -I tools/ci/check_product_purpose.py` | 통과: [product-purpose.log](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round1/product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 45/45·존재 검사 72/72 통과: [spec-check.log](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round1/spec-check.log) |

이 재검증은 로컬 결과다. 감독자 재검증도 위처럼 작업 트리 내부 target을 지정해야
삭제된 검토 작업 트리의 바이너리를 재사용하지 않는다. commit·push·GitHub 호출은 수행하지 않았다.

## Fix round 2: main 병합 충돌과 결합 검증

병합 중 충돌은 BLUEPRINT §11의 자동 생성 엔진 시험 등록 수 한 곳이었다.
날짜 회귀 시험과 main의 금액 범위 비교 회귀 시험·I5 근거 연결을 모두 유지하고,
`CARGO_TARGET_DIR="$PWD/target" CARGO_NET_OFFLINE=true python3 -I tools/blueprint_counts.py --write`로
결합된 코드에서 표를 재생성했다. 어느 한쪽의 206·207을 선택하지 않고 실제 등록 수
**208개·doctest 3개**로 해결했다. 충돌 해결 파일을 index에 반영했으며 병합 commit은
감독자에게 남겼다. main에서 들어온 증거 로그 두 파일의 마지막 빈 줄만 제거해
`git diff --cached --check`도 통과시켰다.

아래 검증은 모두 이 작업 트리에서 직접 실행했다. Cargo 실행과 Cargo를 호출하는
Python 검사는 `CARGO_TARGET_DIR="$PWD/target"`을 사용했다.
로그 위치: [fix-round2/](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round2/).

| 명령 | 결과·로그 |
|---|---|
| `cargo test -p onjeon-rules-engine --locked --offline --lib --test date_format --test range_comparisons --test fixture_supplements` | 단위 10개·날짜 4개·범위 비교 10개·fixture supplement 4개 통과: [focused.log](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round2/focused.log) |
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 473개 통과·실패 0·기존 ignored 1개. 내부 Python 39개·129개 통과: [workspace.log](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round2/workspace.log) |
| `CARGO_NET_OFFLINE=true python3 -I -m unittest discover -s tools/tests -v` | 1,271개 실행·실패 0·skip 36: [python-tests.log](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round2/python-tests.log) |
| `python3 -I tools/evidence/audit3-engine-parse-date-strict/negative_control.py` | 정상 날짜 시험 4개 통과, 숫자 검사 제거 시 거부 시험 3개 실패: [요약](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round2/negative-control.log), [정상](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round2/control-baseline.log), [변이](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round2/control-permissive.log) |
| `cargo fmt --all -- --check` · `cargo clippy --all-targets --locked --offline -- -D warnings` | 모두 종료 코드 0: [fmt.log](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round2/fmt.log), [clippy.log](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round2/clippy.log) |
| `python3 -I tools/blueprint_counts.py` | 등록 수 일치: [counts.log](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round2/counts.log) |
| `python3 -I tools/ci/check_product_purpose.py` · `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 목적 대응 검사 통과·기계 검사 45/45·존재 검사 72/72 통과: [목적](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round2/product-purpose.log), [명세](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round2/spec-check.log) |
| `python3 -I tools/blueprint_status.py` · `python3 -I tools/vocab_check.py` · `python3 -I tools/validation_check.py` | 모두 통과: [상태](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round2/status.log), [어휘](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round2/vocab.log), [검증 자료](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round2/validation.log) |

이 결과는 병합된 엔진의 로컬 회귀 검증이며 제품 출시 완료 증거는 아니다.
보호 문서·공유 fixture·날짜 파서 실행 로직은 변경하지 않았다.
[scope.log](../../../tools/evidence/audit3-engine-parse-date-strict/fix-round2/scope.log)에
미해결 충돌 없음·양쪽 시험 보존·허용 경로·문서 링크·diff 공백 검사를 기록했다.
