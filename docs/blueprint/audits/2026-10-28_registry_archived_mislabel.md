# Audit 3 — 원장 8행의 보관 오표기 재검증

대상: `audit3-registry-archived-mislabel`, `tools/registry_normalize.py`와 `data/registry/insurers.csv`.
연결: Blueprint A1·Q7·L0/L1·I6(근거 사슬 기반)·M1, 09 제품 목적 대응표 P01·P02.

## 현재 상태와 판정

작업 시작 시 이미 [Audit 2 정정](2026-10-27_registry_archived_overclaim.md)이 반영되어 있었다. 정규화기의 `disclosure()`는 공시 URL 접근 확인만으로 보관 완료를 판단하지 않고 `unqueried`와 `공시 URL 접근 확인(reachable). 원문 무결성 검사·불변 보관 전`을 반환한다. 실제 원장에서도 접근 확인 8곳은 모두 이 상태이며 `archived`는 0이다. 이번 작업에서는 기존 정규화 코드와 CSV를 다시 변경하지 않았다.

`reachable`은 접근 결과(`host_access`), `unqueried`는 아직 수행하지 않은 원문 보관 작업(`acquisition_status`)을 나타낸다. 접근은 했지만 보관 전이라는 사실은 사유 열로 구분한다. README의 scratchpad 보관, HTTP 200 또는 응답 해시만으로 무결성 검사 후 불변 보관을 증명할 수 없다.

| 원장 지표 | 재검증 결과 |
|---|---|
| 보험사 | 53행 |
| 공시 URL 접근 확인 | `reachable` 8 |
| 공시 원문 보관 상태 | `archived` 0, `failed` 31, `blocked` 3, `unqueried` 19 |
| 공시 진입점 미확보 | 45 |
| 상품·특약 목록 | `unqueried` 53 |

## 추가한 회귀 시험

[실제 원장 일괄 정정 시험](../../../tools/tests/test_registry_denominator.py)의 `test_repairs_exactly_eight_legacy_archived_rows_without_changing_evidence`는 원본 CSV를 읽고 임시 복사본만 수정한다.

1. 보험사 53행 중 실제 접근 확인 8곳의 ID가 AIA·카디프·처브라이프·라이프플래닛·흥국화재·DB손보·에이스아메리칸·미쓰이스미토모 한국지점과 정확히 일치하는지 확인한다.
2. 복사본의 해당 8행만 과거 오표기인 `archived`와 빈 사유로 바꾼다.
3. 정규화 후 정확히 8행의 `disclosure_status`·`disclosure_gap_reason`만 변경되는지 대조한다. URL·접근 결과·원문 상세·기관 근거·관측 시각·메모·상품 목록 정보와 나머지 45행을 보존해야 한다.
4. 결과가 현재 원장과 바이트 단위로 일치하고 재실행 후에도 같은지 검사한다.

[과거 분기 모의 실행](../../../tools/evidence/audit3-registry-archived-mislabel/legacy-mutation.log)에서는 메모리의 `disclosure()`만 과거 `reachable → archived` 동작으로 교체했다. 신규 시험이 `'archived' != 'unqueried'`로 실패하여 결함을 검출했다. 이 로그의 실패는 의도한 변이 검출이며 실제 코드의 실패가 아니다. 기존 코드는 변경하지 않았다.

## 실행 증거

실행 결과는 [Audit 3 로그](../../../tools/evidence/audit3-registry-archived-mislabel/)에 기록한다. 모든 실행은 이 작업 트리 안의 빌드 산출물과 로컬·합성 자료를 사용한다. 실제 공시·R2 요청은 수행하지 않았다.

| 명령 | 결과 | 로그 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_registry*.py' -v` | 40개 통과, 종료 코드 0 | [원장 시험](../../../tools/evidence/audit3-registry-archived-mislabel/registry-tests.log) |
| `ONJEON_ONTOLOGY_RUNNER="$PWD/target/onto/debug/ontology-case-runner" python3 -m unittest discover -s tools/tests -v` | 1,255개 실행, 1,249개 통과·6개 건너뜀, 종료 코드 0 | [전체 Python 시험](../../../tools/evidence/audit3-registry-archived-mislabel/python-tests.log) |
| `CARGO_TARGET_DIR="$PWD/target" cargo test --all --locked` | Rust 466개 통과·기존 픽스처 재생성 시험 1개 무시, 내장 Python 39개·129개 통과, 종료 코드 0 | [전체 Rust 시험](../../../tools/evidence/audit3-registry-archived-mislabel/rust-tests.log) |
| `cargo build --locked --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir "$PWD/target/onto"` | 종료 코드 0 | [실행기 빌드](../../../tools/evidence/audit3-registry-archived-mislabel/ontology-build.log) |
| 어휘·검증 자료·검증기 selftest·Blueprint 결정 색인·제품 목적 연결·설계 명세·온톨로지 검사·`git diff --check` | 모두 종료 코드 0 | [정합성 검사와 정확한 명령](../../../tools/evidence/audit3-registry-archived-mislabel/consistency-checks.log) |

Python 건너뜀은 비공개 로컬 보관본이 필요한 기존 시험 5개와 설치된 botocore의 조건부 PUT 지원으로 해당하지 않는 구버전 시험 1개다. 신규 시험은 실행됐다. 전체 Python 시험 전에 온톨로지 실행기를 이 작업 트리에 빌드했다. Cargo 출력도 이 작업 트리의 `target/`에 한정했다.

이 증거는 P01·P02의 기관 원장 상태 정확성과 회귀 방지에 한정된다. 상품·특약 분모의 전수 열거, 원문 불변 보관, 실제 확보율, 트윈·소비자 화면 또는 첫 출시 완료를 증명하지 않는다. 출시 판정은 계속 09의 완료 증거와 T-OP-08을 따른다.
