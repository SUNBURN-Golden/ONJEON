# Audit 4 — registry cross-check stale 안내 정정 증거

실행일: 2026-11-04. [판정·변경 범위](../../../docs/blueprint/audits/2026-11-04_registry_crosscheck_stale.md).

레지스트리 README의 오래된 재검증 계획을 실제 미수행 상태로 정정했다. FSS/FISIS/파인에 새 요청을 보내거나 CSV 상태를 변경하지 않았다. 53곳의 상품 목록은 계속 `unqueried`이며 실제 분모·첫 출시 완료를 주장하지 않는다.

| 검증 명령·방법 | 결과 | 로그 |
|---|---|---|
| 현재 `test_registry_crosscheck_note`를 `git show HEAD:data/registry/README.md`로 복원한 임시 레지스트리에 실행 | 4개 중 문서 검사 3개에서 하위 사례 16개 실패, CSV 근거 검사 통과 | [수정 전](before.log) |
| `python3 -m unittest tools.tests.test_registry_crosscheck_note tools.tests.test_registry_denominator tools.tests.test_registry_scope tools.tests.test_registry_normalize -v` | 새 시험 4개 포함 44개 통과 | [레지스트리 시험](registry-tests.log) |
| `env -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -v` | 1,368개 실행, 1,362개 통과·기존 건너뜀 6개, 실패·오류 0 | [Python 전체](python-tests.log) |
| `cargo test --all --locked --offline` | 성공, 실패 0·기존 무시 1개. 내장 Python 시험 39개·129개도 통과 | [Rust 전체](rust-tests.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4개 통과 | [온톨로지 실행기](ontology-runner-tests.log) |
| `python3 tools/vocab_check.py` | 어휘 49축·270값 및 레지스트리 검사 통과 | [어휘 검사](vocabulary.log) |
| CSV 5개를 HEAD의 바이트와 비교·문서 상대 링크 존재 검사·`git diff --check` | CSV 바이트 보존·링크 유효·공백 오류 없음 | [무결성 검사](integrity-check.log) |

수정 전 검증은 임시 디렉터리에 `data/registry`를 복사하고 README만 HEAD 버전으로 교체한 뒤, 시험 모듈의 `REG`를 그 디렉터리로 지정해 실행했다. 작업 트리의 원장 파일은 수정하지 않았다. 정상 실행과 수정 전 실패를 함께 남겨 오래된 문구의 재등장을 검출함을 확인한다.

새 시험은 기존 CI의 Python 발견 단계에 포함된다. 미래의 실제 교차검증이나 상품 열거로 원장 증거가 바뀌면 이 날짜의 상태 설명과 회귀 기대값도 함께 갱신해야 한다.
