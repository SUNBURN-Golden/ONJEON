# Audit 4: R2 README 원장 접두어 누락

검증일: 2026-11-04. 기준 커밋: `aa3b1f4fc2c2865ee88579de93db9031fa8c9f35` + 이 노드의 미커밋 변경.

[R2 README](../../../infra/r2/README.md)의 `onjeon-budget-ledger` 행에는 `ledger/v1/`만 있었다. [구현](../../r2_budget.py)의 `CONTROL_PREFIXES`와 원장 쓰기 경로를 확인하여 입장 `admission/v1/<월>/<작업>/<실행>.json`, 마감 `closed/v1/<월>/<작업 또는 _global>.json`, 체크포인트 `checkpoint/v1/<순번 10자리>.json`을 추가했다. 버킷 설명에도 입장·마감·체크포인트를 반영했다. 기존 예약·정산 경로는 유지한다.

[회귀 시험](../../tests/test_r2_readme.py)은 해당 버킷 행의 키 열만 읽고 접두어를 `CONTROL_PREFIXES`와 대조한다. 누락·오타·중복·불필요한 접두어를 검출하며 기존 CI의 Python 시험 발견 대상이다.

| 증거 | 직접 실행한 명령·결과 |
|---|---|
| [수정 전](before-tests.log) | 새 회귀 추가 후 README 수정 전 `python3 -m unittest tools.tests.test_r2_readme -v`: 1개 실패, 종료 1. 입장·마감·체크포인트 누락을 검출 |
| [수정 후](readme-tests.log) | 같은 명령: 1개 통과, 종료 0 |
| [변이 검사](mutation-tests.log) | `unittest.mock.patch.object(Path, 'read_text')`로 메모리의 버킷 행에서 네 접두어를 각각 `typo/v1/`로 바꿈. 현행 문서는 통과하고 변이 4개는 모두 AssertionError로 검출. 실제 파일이 바뀌지 않았음을 assert, 종료 0 |
| [R2 관련 시험](r2-tests.log) | `python3 -m unittest discover -s tools/tests -p 'test_r2*.py' -v`: 137개 통과, 종료 0 |
| [Python 전체](python-tests.log) | `python3 -m unittest discover -s tools/tests -v`: 1,364개 실행, 실패·오류 0, skip 6, 종료 0 |
| [Rust 전체](rust-tests.log) | `cargo test --all --locked --offline`: 문서 시험 포함 495개 통과, 실패 0, ignored 1, 종료 0 |
| [온톨로지 실행기](ontology-tests.log) | `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline`: 4개 통과, 종료 0 |

Python skip 6개는 원본 보관 경로 미설정 2개, 로컬 보관소·pdftotext가 필요한 재현 시험 3개, 설치된 botocore가 조건부 쓰기를 지원하여 해당하지 않는 구버전 거부 시험 1개다. Rust ignored 1개는 기존 `regenerate_declared_abox_fixture` 재생성 시험이다. 새 회귀에는 skip이 없다. `git diff --check`와 이 문서의 로컬 링크 존재 검사도 통과했다.

문서와 회귀 시험만 변경했다. 실제 R2 접근·설정 변경, 보호 경로 변경, 커밋·푸시·GitHub 호출은 하지 않았다. 이 증거는 문서 정합성 finding의 해결 근거이며 [09_제품목적_대응표](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md)의 전 상품 수집·트윈·소비자 화면·첫 출시 완료 증거를 대신하지 않는다.
