# audit6-registry-csv-ci-check 실행 증거

작업일: 2026-11-16. Blueprint A1·Q7·L0·I6(근거 사슬 기반)·I17·V0/M3, 09 P01·P02.
설명과 검사 범위: [Audit 6 기록](../../../docs/blueprint/audits/2026-11-16_registry_csv_ci_check.md).

## 데이터 정정과 실패 재현

- [셀별 대조](registry-correction.json): 기준 HEAD와 비교해 ID 참조 3개·현대해상 메모 1개만 변경했다. 6개 CSV의 행 수와 나머지 모든 셀을 보존했다. 제외 파일은 바이트 단위로 동일하고 기존 `entity_evidence` 집계(2/47), 현행 목록 밖 상태를 유지한다.
- [기준 원장 검사](before-check.log): 현재 검사기와 기준 HEAD의 CSV를 임시 트리에 복사해 실행했다. 원래 접근 목적 2개·출처 ID 1개의 없는 기관 참조를 각각 줄 번호와 함께 검출하고 예상대로 종료 코드 1을 반환한다.
- [기준 원장 회귀](before-tests.log): 같은 임시 복사본에서 현행 원장 통과 시험과 현대해상 메모 시험을 실행했다. 각각 참조 오류·메모 모순으로 실패한다(2개 실행·2개 실패, 예상 종료 코드 1). 실제 원장에는 쓰지 않았다.

## 정정 후 결과

모든 명령은 이 작업 트리에서 실행했다. Cargo 산출물은 이 디렉터리 안에 한정했고 무시되는 `target/`에 보관한다(별도 `ontology-target/`은 검증 뒤 `target/ontology/`로 이동). 실제 GitHub Actions 실행·원격 조회는 하지 않았다.

| 명령 | 결과 | 로그 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p test_registry_check.py -v` | 17개 통과. CI 명령의 정상 원장·원래 참조 3개·과거 제외 상태 열의 개별 종료 코드 0/1 및 CSV 바이트 보존 포함 | [신규 회귀](registry-check-tests.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_registry*.py' -v` | 82개 통과 | [원장 전체](registry-tests.log) |
| `python3 -m unittest discover -s tools/tests -p test_vocab_check.py -v` | 27개 통과 | [어휘](vocab-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,650개 실행·1,644개 통과·기존 6개 건너뜀, 실패·오류 0 | [Python 전체](python-tests.log) |
| `cargo test --all --locked --offline` | Rust 532개 통과·1개 무시, 내장 Python 시험 39개·129개도 통과 | [Rust 전체](rust-tests.log) |
| `cargo fmt --all -- --check` | 종료 코드 0 | [형식 검사](rust-format.log) |
| `cargo clippy --all-targets --locked --offline -- -D warnings` | 종료 코드 0 | [린트](rust-lint.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4개 통과 | [온톨로지 실행기](ontology-tests.log) |
| 원장 검사·어휘·워크플로·검증 자료·변이 selftest·Blueprint 결정 색인/등록 수·제품 목적 연결·설계 명세·CRLF를 인정하는 `git diff --check` | 모두 종료 코드 0. 각 명령과 종료 코드 기록 | [일관성 검사](consistency-checks.log) |

전체 Python 시험의 기존 건너뜀은 보관 원본이 없는 로컬 시험 5개와 현재 botocore에서 해당하지 않는 구버전 조건부 PUT 시험 1개다. 신규 17개는 모두 실행했다. 전체 시험 뒤 CI 명령 회귀를 원래 참조 3개와 과거 상태 열의 개별 검사로 넓혔고 신규 17개·관련 82개를 다시 통과했다(시험 개수 변화 없음).

회사 원장 무결성과 CI 연결에 한정된 완료 증거다. 상품·특약·판매본 분모, 실제 공시 확보·불변 보관, 트윈·소비자 화면, P01/P02 전체와 첫 출시 완료는 증명하지 않는다.
