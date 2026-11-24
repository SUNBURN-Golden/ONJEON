# Audit 8 과제별 증거 작성 경로

기준 커밋 `b11d50d`에서는 66개 과제 중 63개가 자신의 증거 경로를
`allowed_paths`·`produces`·`conflict_paths`에 명시했다. 변경 뒤 66개 모두
명시한다. [작업 계약](../../../docs/blueprint/proposals/설계검토_결과/tasks.json)

- T-OP-08의 감리 보고서와 수락 실행 로그는 `docs/release-readiness/evidence/T-OP-08/`에 둔다. 공용 `readiness.json`은 T-OP-08이 관리한다.
- T-OP-00·T-OP-09의 검증 기록은 각각 `tools/evidence/T-OP-00/`·`tools/evidence/T-OP-09/`에 둔다. 최종 감리는 이 기록을 축 5 운영 기록에 사용한다.

[회귀 시험](../../tests/test_evidence_paths.py)은 모든 과제의 산출물 선언과
데몬 R-01의 파일·하위 로그 쓰기 판정, 과제 간 쓰기 격리, 최종 감리 잠금,
작업명세 표를 검증한다. 합성 파일을 임시 디렉터리에 두고 P01~P19와 기능
64개가 과제별 증거를 참조할 수 있는지, 참조 대상이 없어지면 해당 행이 다시
열리는지 검사한다.

신규 단언을 기준 작업 계약에 적용하면 누락된 세 과제에서 하위 사례 11건이
실패한다. 수정본의 메모리 사본에서 세 과제의 `produces` 증거 경로만
하나씩 제거한 변이도 모두 탐지했다. 실제 출시 판정기는 P01~P19 19개와
기능 64개 모두 미완료로 보고했다(종료 1).

## 실행 결과

| 명령 또는 검사 | 결과 |
|---|---|
| `python3 -m unittest tools.tests.test_evidence_paths tools.tests.test_product_purpose tools.tests.test_release_readiness tools.tests.test_purpose_progress -v` | 50개 통과. [실행 로그](regression.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,776개 실행, 1,770개 통과, 6개 건너뜀 |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과 |
| `python3 -m unittest discover -s tools/ci/tests -v` | 21개 통과 |
| `cargo test --all --locked --offline` | 537개 통과, 픽스처 재생성 시험 1개 무시 |
| 시나리오 API·온톨로지 실행기 각각 `cargo test --locked --offline` | 각 4개 통과 |
| `cargo fmt --all -- --check` · `cargo clippy --all-targets --locked --offline -- -D warnings` | 통과 |
| 설계 명세·제품 목적·부트스트랩 검사 | 명세 기계 47개·존재 72개 통과. 제품 목적 연결 통과. 부트스트랩은 기존 경로 권고 6건 |
| 데몬 모의 실행 `--scenario all --require-all --quiet` | 검사 695건 통과 |
| `python3 -I tools/release_readiness/check.py --json` | 예상 종료 1, 제품 목적 19/19 및 기능 64/64 미완료 |

Python 전체 시험은 boto3 1.43.100 가상 환경과 사전 빌드한 온톨로지 실행기를
사용했다. 보관 원본·로컬 보관소가 필요한 5개와 구형 botocore 전용 1개를
건너뛰었다. Rust 작업 공간에서 호출한 생성기 시험 중 Dart·TypeScript 도구가
필요한 2개는 건너뛰었다.

## Fix round 1 로컬 시험 환경

새 작업 트리에는 rustup 전역 기본값이 없어 Cargo가
`no default is configured`로 종료됐다(코드 변경 실패가 아니라 환경 설정 누락).
[README](../../../README.md)의 안내대로 `rustup override set --path "$PWD" 1.98.1`을
적용한 뒤 위 명령을 다시 실행해 모두 통과했다. 이 재정의는 작업 트리 로컬
rustup 설정이며 저장소 파일이 아니다. 전역 기본값을 만들지 않으므로
`test_ci_rust_toolchain.py`가 검사하는 CI 고정·디렉터리 재정의 동작은 그대로다.
