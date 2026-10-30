# Audit 4: 온톨로지 검증의 미확정·범위 금액 표시와 비교

2026-10-30. 노드 `audit4-ontology-check-unknown-as-zero`의 로컬 검증 기록이다.
BLUEPRINT A1·A2·A5, Q5·Q7, L6, I1, 기반 M0와 09의 P08·P14에 연결한다.

## 결함과 수정

`ontology_check.py`는 조건부 금액에서 `krw`가 없으면 0을 출력했고,
지급 대상 금액에서는 `krw`가 항상 있다고 가정했다. `outcome()`도 범위와
미확정 금액을 모두 `krw: None`으로 축약했다.

[수정 전 재현](../../../tools/evidence/audit4-ontology-check-unknown-as-zero/before-fix.log)은
기준 revision의 검사기를 `git show`로 읽어 메모리에서 실행하고, 이 작업 트리에서
빌드한 실제 Rust 실행기에 기존 하나 규칙을 전달한 결과다. 가입금액 10,000,001원과
감액률 0.5·`unspecified` 반올림의 지급액은 5,000,000~5,000,001원이다.
기존 설명은 지급 대상일 때 `KeyError: 'krw'`, 조건부일 때 `대상이라면 0원`이었다.
조건부 금액 미확정도 같은 0원 문구였고, 범위와 미확정의 결과 비교값도 같았다.

수정한 `amount_text()`는 엔진의 `exact`·`range`·`unknown`을 각각 확정 금액,
`5,000,000~5,000,001원 (범위)`, `금액 미확정`으로 표시한다. 확정된 0원은
계속 0원으로 표시한다. 지급 여부와 조건부 여부에 같은 금액 표시 함수를 사용한다.

`outcome()`은 이제 엔진의 지급 결과 객체를 그대로 복사한다. 지급 대상은
`amount`, 판단 불가는 `conditional_amount` 안에 금액 종류와 범위 양 끝을
보존한다. 기존 질문의 기대값도 이 형태로 갱신했다. 규칙·계산·동결 릴리스는
변경하지 않았다. `검증/결과.txt`는 수정한 검사기의 출력으로 갱신했다.

## 시험과 실행 증거

새 자체 시험은 지급 대상·판단 불가 각각에 확정 금액·확정 0원·범위·가입금액
null·가입금액 키 누락을 적용하는 10개다. 기존 하나 `fixture_only` 규칙을
`resolve()` → Rust 실행기 → `outcome()`·`explain()` 순서로 실행한다.
금액 종류·범위·설명·누락 입력을 확인하고 전체 검사기의 종료 판정에 포함한다.

Python 회귀 시험은 두 지급 종류의 표시·비교, 서로 다른 범위와 미확정·0원의
구별, 근거·규칙 메타데이터 유지, 기존 계산 차단·지급 대상 아님 상태를 검사한다.
실제 실행기로 10개 자체 시험을 실행하며, 자체 시험이 하나라도 실패하면
검사기 `main()`이 종료 코드 1을 반환하는 것도 검증한다.

아래 명령은 저장소 루트에서 실행했다. Cargo에는
`CARGO_TARGET_DIR="$PWD/target"`, Python에는
`ONJEON_ONTOLOGY_RUNNER="$PWD/target/debug/ontology-case-runner"`를 전달했다.
보조 검사별 명령·종료 코드는 [checks.json](../../../tools/evidence/audit4-ontology-check-unknown-as-zero/checks.json)에 있다.

| 실행 | 결과·증거 |
|---|---|
| `python3 -m unittest discover -s tools/tests -v` | 1,301개 실행, 실패 0, 기존 skip 6: [전체 Python 로그](../../../tools/evidence/audit4-ontology-check-unknown-as-zero/python-tests.log) |
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 475개 통과, 실패 0, 기존 ignored doctest 1개: [워크스페이스 로그](../../../tools/evidence/audit4-ontology-check-unknown-as-zero/workspace-tests.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_ontology*.py' -v` | 금액·실행기·자체 시험 실패 전파 회귀: [집중 로그](../../../tools/evidence/audit4-ontology-check-unknown-as-zero/focused-tests.log) |
| `cargo test --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml` | 실행기 단위 시험: [로그](../../../tools/evidence/audit4-ontology-check-unknown-as-zero/runner-tests.log) |
| `python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py "$ONJEON_ONTOLOGY_RUNNER"` | 질문 11/11, 제약 15/15, 릴리스·문서 모델 25/25, 금액 10/10: [검사 로그](../../../tools/evidence/audit4-ontology-check-unknown-as-zero/ontology-check.log) |
| `spec_check.py`·제품 목적 검사·BLUEPRINT 수치·어휘·검증 자료 및 변조 자체 시험 | [명령·종료 코드](../../../tools/evidence/audit4-ontology-check-unknown-as-zero/checks.json)와 같은 디렉터리의 검사별 로그 |

Python skip 6개 중 5개는 로컬 원본 보관소 부재, 1개는 설치된 botocore가 이미
조건부 쓰기를 지원해 구버전 분기 시험을 적용할 수 없기 때문이다.

## 완료 범위

이 finding의 출력·비교 결함과 회귀 시험을 해결했다. 엔진 fixture를 사용하는
설계 검증 도구의 증거다. 09 P08·P14가 요구하는 실제 상품 릴리스 시나리오,
소비자 화면에서 원문까지의 추적, 전 상품 수집·첫 출시 완료 증거를 대신하지 않는다.
외부 서비스·운영 데이터 접근, commit·push·GitHub 호출은 수행하지 않았다.
