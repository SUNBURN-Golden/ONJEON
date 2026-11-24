# Audit 8 S1 선행 조건 검증

기준 커밋 `92eada7`의 작업 계약에서 T-OP-02의 직접 선행은 T-MB-02·T-KN-07이었다. 부트스트랩 도구의 `keep_set`으로 전이적 선행을 계산했을 때 T-DT-01·T-DT-02·T-KN-03·T-KN-05·T-KN-06이 모두 빠져 있었다. 변경 뒤 같은 계산에서 누락은 0개다.

- T-OP-10은 모의 관통 검증이다. 기존 작업 ID 형식에 맞춰 새 번호를 썼고, T-KN-06의 모의 구현이 병합된 뒤 시작할 수 있다. D-02 등록 없이 모의 경로를 병합할 수 있다.
- T-OP-02는 실제 관문 ID를 유지한다. T-KN-06의 선행을 통해 T-KN-05·T-KN-03·T-DT-02·T-DT-01이 연결된다. 실제 관문은 T-OP-10 병합, D-02 등록, 실제 상품의 R2 원본·이종 계열 검수·화면 근거 사슬의 감리를 요구한다.
- 회귀 시험에서 모의 관문의 병합과 D-02 등록 뒤에도 T-DT-03·T-KN-08·T-PS-01은 실제 관문 병합을 기다렸다. 실제 관문을 병합한 뒤 T-DT-03이 대기열에 들어갔고, T-DT-03 완료 뒤 나머지 두 작업이 대기열에 들어갔다. [회귀 시험](../../tests/test_s1_prerequisites.py)

이 검증에서 사용한 선행 상태·결정 등록·감리·병합 관측은 합성이다. `tools/gate/s1_mock.sh`와 `tools/gate/s1.sh`는 각각 해당 관문 작업의 산출물이다. 실제 관통 실행과 증거 감리는 T-OP-02에서 수행한다. 09 출시 판정은 P01~P19 모두 `open`이며 완료 0건이다. [작업 계약](../../../docs/blueprint/proposals/설계검토_결과/tasks.json) · [09 제품목적 대응표](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md)

## 실행 결과

| 명령 | 결과 |
|---|---|
| `python3 -m unittest tools.tests.test_s1_prerequisites -v` | 3개 통과. [실행 로그](regression.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,770개 중 1,764개 통과. 실제 원본 보관 자료가 필요한 5개와 구형 botocore 전용 1개 건너뜀 |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과 |
| `cargo test --all --locked --offline` | 537개 통과, 픽스처 재생성 시험 1개 건너뜀 |
| `cargo test --manifest-path services/scenario-api/Cargo.toml --locked --offline --target-dir target/scenario-api` | 4개 통과 |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4개 통과 |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 47/47, 존재 검사 72/72 통과 |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업·수락 시험 연결 검사 통과 |
| `python3 -I tools/ci/check_bootstrap.py` | 통과, 기준 커밋과 같은 경로 안내 6건 |
| 데몬 모의 실행 `--scenario all --require-all --quiet` | 695개 검사 통과 |
| 출시 판정기 `--purpose` | 예상대로 종료 코드 1, P행 19개와 기능 64개가 미완료 |

## Fix round 1 병합 검증

작업 브랜치 `1ca6c44`와 main `8c75844`의 공통 조상을 기준으로 병합된 작업 계약을 대조했다. 고유 과제 66개와 레지스트리 필드 모두 각 변경을 반영한 부모와 일치했다. T-OP-08은 실제 S1 관문(T-OP-02)과 잔여 어휘 과제(T-CT-09)를 선행으로 가진다. T-CT-09는 T-OP-10·T-OP-02의 선행 집합에서 제외된다. [병합 회귀 시험](../../tests/test_s1_prerequisites.py) · [어휘 범위 시험](../../tests/test_vocabulary_task_scope.py)

회귀 시험은 메모리 사본에서 T-CT-09를 모의·실제 S1 관문의 선행에 각각 추가하거나 최종 관문의 선행에서 제거한 세 경우를 모두 탐지했다.

| 병합 트리 재실행 | 결과 |
|---|---|
| `python3 -m unittest tools.tests.test_s1_prerequisites tools.tests.test_vocabulary_task_scope -v` | 9개 통과 |
| `python3 -m unittest discover -s tools/tests -v` | 1,776개 중 1,770개 통과. 원본 보관 자료가 필요한 5개와 구형 botocore 전용 1개 건너뜀. boto3 1.43.100을 설치한 작업 트리 가상 환경과 시스템 임시 디렉터리 사용 |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과 |
| `cargo test --all --locked --offline` | 537개 통과, 픽스처 재생성 시험 1개 무시. 내부 Python 생성기 시험 138개 중 Dart·TypeScript 도구가 필요한 2개 건너뜀 |
| 시나리오 API·온톨로지 실행기 독립 Cargo 시험 | 각각 4개 통과. 온톨로지 검증기도 통과 |
| CI 도구 시험·작업 명세·제품 목적·부트스트랩 검사 | CI 도구 21개, 명세 기계 검사 47개와 존재 검사 72개 통과. 제품 목적 링크 통과, 부트스트랩 기존 경로 권고 6건 |
| 어휘·생성물 검사와 계약 호환성 자체 시험 | 50축·271값, 생성물 30개 일치. 필드 삭제 자체 시험 통과. 이전 `contracts-*` 태그가 없어 출시 판 비교 생략 |
| 등록부·검증 자료·데몬 모의 실행 및 출시 판정기 `--purpose` | 등록부·검증 자료 검사 통과, 합성 변경 40개 탐지, 데몬 모의 검사 695개 통과. 출시 판정기는 예상대로 종료 코드 1, P행 19개와 기능 64개가 미완료 |

## Fix round 2 로컬 시험

빈 Cargo 캐시에서 실행기 빌드는 `serde_json`을 찾지 못해 종료 코드 101을
반환했다. 같은 의존성 오류가 잠금 회귀 시험에서도 대상 잠금에 도달하기 전에
발생했다. 실행기 시험 설정은 이제 Cargo 진단과 캐시 준비 명령을 표시한다.
잠금 회귀 시험은 의존성 없는 임시 크레이트와 빈 캐시로 실제 Cargo의 잠금 대기와
시간 제한을 검증한다. [실행기 회귀 시험](../../tests/test_ontology_runner_io_error.py)

별도의 빈 `CARGO_HOME`에서 실행기 디렉터리의 `cargo fetch --locked`를
실행한 뒤, 같은 캐시와 `ONJEON_ONTOLOGY_RUNNER` 미설정 상태에서 실행기
Python 시험 15개가 모두 통과했다. 전체 Python 재실행에는 작업 트리 안의 준비된
Cargo 캐시와 boto3 1.43.100이 설치된 가상 환경을 사용했다.

```sh
CARGO_HOME="$PWD/target/audit8-merge-tests/cargo" RUSTUP_TOOLCHAIN=1.98.1 \
  env -u ONJEON_ONTOLOGY_RUNNER target/audit8-merge-tests/venv/bin/python \
  -m unittest discover -s tools/tests -v
```

S1 회귀 시험은 모의·실제 관문 모두에 T-DT-01·T-DT-02·T-KN-03·T-KN-05·T-KN-06
선행이 연결되고 T-DT-03·T-KN-08·T-PS-01이 실제 관문 병합 후에만 진행함을
확인했다. 실제 S1 관통 실행과 감리는 T-OP-02의 수락 항목으로 남아 있다.

| 재실행 | 결과 |
|---|---|
| 전체 Python 시험 | 1,776개 중 1,770개 통과. 원본 보관 자료가 필요한 5개와 구형 botocore 전용 1개 건너뜀 |
| S1 선행 조건·어휘 범위 회귀, 실행기 검증 도구, CI 도구 | 각각 9개, 81개, 21개 통과 |
| 잠금 회귀를 포함한 실행기 설정 시험 | 6개 통과. 실제 잠금 대기는 빈 Cargo 캐시에서도 5초 제한으로 종료 |
| Rust 작업 공간, 시나리오 API, 온톨로지 실행기 | 각각 537개, 4개, 4개 통과. Rust 작업 공간의 픽스처 재생성 시험 1개 무시 |
| 작업 명세·제품 목적·부트스트랩·온톨로지 검사 | 명세 기계 검사 47개와 존재 검사 72개 통과. 제품 목적·부트스트랩·온톨로지 검사 통과. 기존 부트스트랩 경로 권고 6건 |
| 데몬 모의 실행 | 695개 검사 통과 |
| 출시 증거 검사 | 예상대로 종료 코드 1. 제품 목적 19개와 기능 64개가 모두 미완료 |

## Fix round 3 빈 Cargo 캐시에서의 시험

기본 Python 시험 탐색에서 `cargo build --locked`가 온톨로지 실행기를 빌드한다.
사전 `cargo fetch` 없이 빈 `CARGO_HOME`과 빈 빌드 디렉터리에서 시작해 잠금 파일의
의존성을 받아 실제 실행기 시험 9개와 설정 시험 6개를 모두 통과했다. 실행기 경로와
Rust 버전은 환경 변수로 지정하지 않았다. Python 환경에는 CI와 같은 boto3 1.43.100을
설치했다. [실행기 회귀 시험](../../tests/test_ontology_runner_io_error.py) · [로컬 시험 안내](../../../README.md#로컬-시험)

```sh
env -u ONJEON_ONTOLOGY_RUNNER -u CARGO_NET_OFFLINE -u RUSTUP_TOOLCHAIN \
  CARGO_HOME="$PWD/target/audit8-round3/cold-cargo" \
  CARGO_TARGET_DIR="$PWD/target/audit8-round3/cold-ontology-target" \
  target/audit8-merge-tests/venv/bin/python -m unittest discover -s tools/tests -v
```

`CARGO_NET_OFFLINE=true`를 지정한 빈 캐시에서는 Cargo의 `serde_json` 오류와 준비
안내가 표시됐다. 준비된 캐시의 오프라인 실행과 `ONJEON_ONTOLOGY_RUNNER`로
사전 빌드한 실행기를 지정한 실행에서는 각각 15개가 통과했다.

| 재실행 | 결과 |
|---|---|
| 전체 Python 시험 | 1,776개 실행, 1,770개 통과. 원본 보관 자료가 필요한 5개와 구형 botocore 전용 1개 건너뜀 |
| S1 선행 조건·어휘 범위 회귀, 실행기 검증 도구, CI 도구 | 각각 9개, 81개, 21개 통과 |
| Rust 작업 공간, 시나리오 API, 온톨로지 실행기 | 각각 537개, 4개, 4개 통과. Rust 작업 공간의 픽스처 재생성 시험 1개 무시 |
| 작업 명세·제품 목적·부트스트랩·온톨로지 검사 | 명세 기계 검사 47개와 존재 검사 72개 통과. 제품 목적·부트스트랩·온톨로지 검사 통과. 기존 부트스트랩 경로 권고 6건 |
| 등록부·검증 자료·어휘·생성물과 데몬 모의 실행 | 통과. 검증 자료 변조 40개 탐지, 생성물 30개 일치, 데몬 모의 검사 695개 통과 |
| 출시 증거 검사 | 예상대로 종료 코드 1. 제품 목적 19개와 기능 64개가 모두 미완료 |

## Fix round 4 작업 트리의 Rust 도구 체인

Python 시험 뒤의 Cargo 실패를 저장소 루트에서 `cargo --version`으로 재현했다.
설치된 Rust 1.98.1을 이 작업 트리에 등록한 뒤, `RUSTUP_TOOLCHAIN`이 없는
새 셸에서 `cargo --version`이 1.98.1을 출력했다. 부모 디렉터리에서는 전역
기본값이 없음을 확인했다. 새 작업 트리에는 해당 경로로 재정의를 등록한다.
[로컬 시험 안내](../../../README.md#로컬-시험)

```sh
rustup override set --path "$PWD" 1.98.1
env -u RUSTUP_TOOLCHAIN cargo --version
```

회귀 시험은 CI·온톨로지 실행기·README의 버전 일치와 rustup 재정의의 경로 범위를
검증한다. 메모리에서 README의 설치 명령과 재정의 명령의 버전을 각각 바꿨을 때
두 경우 모두 시험이 실패했다. S1 시험은 모의 관문 병합 뒤에도 세 후속 작업이
실제 관문 병합을 기다림을 확인했다.
[Rust 설정 시험](../../tests/test_ci_rust_toolchain.py) · [S1 선행 시험](../../tests/test_s1_prerequisites.py)

| 재실행 | 결과 |
|---|---|
| `python3 -m unittest discover -s tools/tests -v` | 1,776개 실행, 1,770개 통과. 보관 자료가 필요한 5개와 구형 botocore 전용 1개 건너뜀 |
| Rust 설정·S1 선행 조건·어휘 범위 회귀 | 13개 통과 |
| 실행기 검증 도구·CI 도구 | 각각 81개, 21개 통과 |
| `cargo test --all --locked --offline` | 537개 통과, 픽스처 재생성 시험 1개 무시. 내부 Python 생성기 시험 중 Dart·TypeScript 도구가 필요한 2개 건너뜀 |
| 시나리오 API·온톨로지 실행기 독립 Cargo 시험 | 각각 4개 통과 |
| Rust 형식·Clippy·설계도 집계 | 통과 |
| 작업 명세·제품 목적·부트스트랩·데몬 모의 실행 | 작업 명세 119개와 데몬 모의 검사 695개 통과. 제품 목적·부트스트랩 검사 통과, 기존 부트스트랩 경로 권고 6건 |
| 온톨로지·등록부·검증 자료·생성물·계약 호환성 | 통과. 검증 자료 변조 40개 탐지. 이전 `contracts-*` 태그 부재로 출시 판 비교 대신 호환성 자체 시험 실행 |

Python은 boto3 1.43.100 가상 환경을 사용했다. Cargo는 작업 트리 안의 준비된
의존성 캐시를 사용했고, Rust 시험은 `RUSTUP_TOOLCHAIN` 없이 실행했다.
