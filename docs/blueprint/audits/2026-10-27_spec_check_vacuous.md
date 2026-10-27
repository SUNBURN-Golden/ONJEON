# Audit 2: 빈 입력으로 통과하던 명세 검사 차단

2026-10-27 · 노드 `audit2-spec-check-vacuous` · 기준 커밋 `40ceef77003697ffb356a98cbc68bb70bc9324e1`

G4c·G7b·G9·G26은 문제 항목이 없다는 조건만 확인해, 검사할 항목 자체가 없어도 통과했다. G4c의 제목 정규식이나 G26의 범위 정규식이 아무것도 찾지 못해도 같은 결과였다. 각 검사는 이제 검사한 항목이 1개 이상이어야 통과하고, 결과의 `detail`에 개수를 남긴다.

| 검사 | 추가한 통과 조건 | 현재 묶음에서 확인한 수 |
|---|---|---|
| G4c | 통합안에서 읽은 기능 행과 feature_registry가 모두 비어 있지 않음. 모든 행의 매핑도 계속 확인 | 기능 행 60개, 등록 기능 64개 |
| G7b | 종료 아닌 상태와 전이가 모두 비어 있지 않음. 각 상태의 반송 외 전이도 계속 확인 | 종료 아닌 상태 19개, 전이 90개 |
| G9 | 전환 신호와 판정 규칙이 비어 있지 않음. 각 신호에도 detect가 필요하며 기존 출처·HTTP 범위 검사 유지 | 신호 4개, 판정 규칙 7개 |
| G26 | T-box 제약과 찾은 범위 표기가 비어 있지 않음. 빈 제약은 예외 대신 실패로 보고 | 제약 16개, 범위 표기 14개 |

G26은 구분자 `~`·`～`·`〜`·`-`·`–`·`—`와 주변 공백을 인식한다. 따라서 일부 문서의 오래된 `K1–K15` 표기가 다른 문서의 정상 `K1~K16` 표기에 가려지지 않는다. 지원 구분자를 사용한 정상 범위는 계속 통과한다.

## 검증 증거

- [회귀 테스트](../../../tools/tests/test_spec_check_vacuous.py): 25개. 빈 문서·빈 목록·빠진 상태/정책·종료 상태만 있는 목록·판정 규칙 없는 단일 신호·제목 패턴 불일치·범위 표기 소실·빈 T-box를 실패로 판정한다. 기존 미매핑 행·막힌 상태·잘못된 출처·HTTP 범위·오래된 제약 범위도 거부한다. 지원 구분자 7가지(공백 포함)는 정상/오래된 범위를 각각 확인한다.
- [기준본/수정본 비교](../../../tools/evidence/audit2-spec-check-vacuous/before_after.log): 같은 변형에서 기준본의 잘못된 PASS가 수정본의 FAIL로 바뀐다. 정상 묶음은 양쪽 모두 통과하고, 기존 음성 대조군도 양쪽 모두 실패한다. 빈 T-box는 기준본의 `ValueError`에서 명시적인 FAIL로 바뀐다. 재현 도구는 같은 폴더의 [mutations.py](../../../tools/evidence/audit2-spec-check-vacuous/mutations.py)다.
- `python3 -m unittest tools/tests/test_spec_check_vacuous.py tools/tests/test_spec_check_cond.py -v`: 관련 46개 통과([로그](../../../tools/evidence/audit2-spec-check-vacuous/focused-tests.log)).
- `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py`: 기계 44/44, 존재 72/72 통과([로그](../../../tools/evidence/audit2-spec-check-vacuous/spec-check.log), [개수 포함 JSON](../../../tools/evidence/audit2-spec-check-vacuous/spec-check.json)).
- 전체 Python: 1099개 실행, 실패 0·skip 6([로그](../../../tools/evidence/audit2-spec-check-vacuous/python-tests.log)). `env -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -v`로 실행했다. Python 시험에서 만드는 온톨로지 실행기가 시험이 기대하는 로컬 `target` 경로에 생성되도록 외부 target 설정을 해제했다.
- Rust: 447개 통과, 실패 0·ignored 1([로그](../../../tools/evidence/audit2-spec-check-vacuous/rust-tests.log)). `CARGO_TARGET_DIR="$PWD/target" cargo test --all`로 실행했다.
- 어휘·검증 자료·검증기 selftest·제품 목적 대응표 연결·설계도 결정 색인·`git diff --check`: [일관성 검사 로그](../../../tools/evidence/audit2-spec-check-vacuous/consistency-checks.log).

## 제품 목적과 증명 범위

이 수정은 BLUEPRINT §9 M6 및 T-OP-08 출시 관문의 명세 검증을 보강한다. G4c가 전 계층(L0~L9)의 기능 누락을 빈 스캔으로 통과시키지 못하게 하며, A1~A6를 위한 작업 연결의 정적 검증을 지원한다. [09_제품목적_대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 실제 데이터·트윈·소비자 화면·출시 완료 증거는 여전히 필요하다.

이 노드의 완료는 검사기 회귀 검증의 완료다. G4c·G26의 양수 조건은 전체 스캔 집합에 적용하므로, 일부 절·문서만 패턴에서 빠지는 모든 경우까지 검출한다는 뜻은 아니다. 실제 데몬 실행·공시 수집·소비자 화면의 동작이나 P01~P19의 완료를 증명하지 않는다.
