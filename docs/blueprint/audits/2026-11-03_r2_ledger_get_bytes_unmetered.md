# Audit 4 — 원장 GET 바이트 계량 재검증

노드: `audit4-r2-ledger-get-bytes-unmetered`. 기준: `2c8e586` + 이 작업 트리 변경.
BLUEPRINT A1·Q7·L1~L2·M1, ADR-0017, [09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md) P02·P03에 연결한다.

## 발견 판정과 변경

감리에서 지적한 원장 GET 바이트 누락은 작업 시작 시점에
[Audit 2 수정](2026-10-27_ledger_uncharged_reads.md)으로 이미 해결돼 있었다.
`start()`가 `ACTIVE`를 설정하기 전에 원장 저장소를 생성하지만,
`Session.open()`은 첫 원장 접근 전에 `st.meter = self.meter`와 요청 이벤트 훅을
명시적으로 연결한다. 기본 생성·주입 S3 원장 모두 같은 경로를 거친다.
`S3Store.get()`은 이 미터로 실제 반환된 본문 바이트를 집계하며,
`finish()`가 `ACTIVE`를 비운 뒤 정산 꼬리를 읽을 때도 연결이 유지된다.

기존 구현을 유지하고 연결 순서의 이유를 주석에 명시했다.
[회귀 시험](../../../tools/tests/test_r2_budget.py)은 다음 경계를 보강한다.

- `test_ledger_get_exhausts_admission_before_reservation`: 기본·주입 저장소 × 원장·체크포인트
  네 조합에서 입장 한도 1바이트를 적용한다. 첫 GET의 경계 확인 바이트까지 `get_bytes=2`로
  집계하고 새 예약 없이 중단한다. 입장 기록 유지·잠금 해제·입장 한도 유지와 서버가 받은
  Class A/B 요청·업로드 바이트의 일치도 검사한다.
- `test_settlement_get_exhausts_remaining_bytes_after_active_is_cleared`: 기본·주입 저장소의
  예약 후 남은 다운로드 허용량을 소진시킨다. `finish()`의 정산 꼬리 GET이 추가 1바이트를
  집계하고 실패하면 정산 기록 없이 예약 전액이 유지되고 잠금이 해제되는지 검사한다.
- 기존 정상 경로는 예약 전 원장·체크포인트, 보관 객체, 정산 꼬리 GET의 본문 크기 합계를
  정산·요약의 `get_bytes`와 정확히 대조한다.

## 직접 실행한 검증

실제 botocore와 임시 로컬 원장·루프백 S3 스텁을 사용했다.
설치 버전은 boto3 `1.43.100`, botocore `1.43.114`다.

| 명령 | 결과·증거 |
|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_r2*.py' -v` | 125개 통과, 건너뜀 0: [budget-tests.log](../../../tools/evidence/audit4-r2-ledger-get-bytes-unmetered/budget-tests.log) |
| `python3 tools/evidence/audit4-r2-ledger-get-bytes-unmetered/mutation_check.py` | 미터 연결 한 줄만 제거한 변이를 두 시험 모두 검출, 하위 사례 실패 6개·오류/건너뜀 0, 검증기 종료 0: [mutation-check.log](../../../tools/evidence/audit4-r2-ledger-get-bytes-unmetered/mutation-check.log) |
| `RUSTUP_TOOLCHAIN=1.98.1 cargo build --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline --target-dir "$PWD/target/audit4-ontology"` | 작업 트리 내부에 온톨로지 실행기 빌드 성공: [runner-build.log](../../../tools/evidence/audit4-r2-ledger-get-bytes-unmetered/runner-build.log) |
| `env -u CARGO_TARGET_DIR RUSTUP_TOOLCHAIN=1.98.1 ONJEON_ONTOLOGY_RUNNER="$PWD/target/audit4-ontology/debug/ontology-case-runner" python3 -m unittest discover -s tools/tests -v` | 1,320개 실행·1,314개 통과·6개 건너뜀·실패/오류 0, 종료 0: [python-tests.log](../../../tools/evidence/audit4-r2-ledger-get-bytes-unmetered/python-tests.log) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 연결 검사 통과: [product-purpose.log](../../../tools/evidence/audit4-r2-ledger-get-bytes-unmetered/product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 설계 명세 검사 통과: [spec-check.log](../../../tools/evidence/audit4-r2-ledger-get-bytes-unmetered/spec-check.log) |

[변이 검증기](../../../tools/evidence/audit4-r2-ledger-get-bytes-unmetered/mutation_check.py)는
별도 프로세스의 메모리에서 `Session.open()`의 본문 계량 연결만 제거한다.
요청 훅은 유지하며 저장소 구현 파일은 바꾸지 않는다. 정상 회귀 시험의 실패가 아니라
과거 결함을 복원한 음성 대조의 기대 실패다.

최초 전체 Python 실행은 Rust 기본 도구 체인이 지정되지 않아 온톨로지 실행기 준비에서
오류 2개로 끝났다(1,311개 실행·건너뜀 6개).
[초기 로그](../../../tools/evidence/audit4-r2-ledger-get-bytes-unmetered/python-tests-initial.log)를
보존하고, 설치된 `1.98.1`을 명령 환경에만 지정해 위 실행기를 빌드했다.
전역 Rust 설정은 바꾸지 않았다.
재실행에서 온톨로지 준비·실행 시험도 모두 통과했다. 건너뜀은 비공개 로컬 원본이 필요한
기존 시험 5개와 설치된 botocore에는 해당하지 않는 구버전 시험 1개이며, 보강한 R2 시험은
모두 실행했다.

[변경 경로·링크·Python 컴파일·공백 검사](../../../tools/evidence/audit4-r2-ledger-get-bytes-unmetered/scope-check.log)도 통과했다.

## 수정 1차 — 기본 도구 체인 없는 로컬 검증

감독자의 기본 환경 재실행은 `ONJEON_ONTOLOGY_RUNNER`·`RUSTUP_TOOLCHAIN` 없이
실행돼 같은 Cargo 준비 오류 2개를 재현했다. 위 최초 재검증의 환경 지정만으로는
이 실행 경로를 고치지 못했다.

[실행기 rust-toolchain.toml](../proposals/온톨로지/검증/runner/rust-toolchain.toml)에
검증한 Rust `1.98.1`과 `minimal` 프로필을 고정했다. Python 준비 코드는 이미 실행기
디렉터리에서 Cargo를 호출하므로 전역 기본값이 없어도 이 파일을 사용한다.
CI의 실행기 빌드·시험도 같은 디렉터리에서 `--locked`로 실행해, Python의 오프라인
대체 빌드·잠금 시험 전에 해당 도구 체인과 의존성을 준비한다. 전역 Rust 설정은
변경하지 않았다. 오프라인 실행에는 고정 도구 체인 설치와 의존성 캐시가 필요하며,
실제 빌드 실패·잠금 시간 초과는 계속 시험 실패로 처리한다.

두 환경 변수와 `CARGO_TARGET_DIR`를 모두 해제한 재실행에서 기존 준비 오류 두 개가
해결됐다. 전체 Python 1,320개 실행·1,314개 통과·기존 건너뜀 6개·실패/오류 0,
R2 125개 및 실행기 Rust 3개도 통과했다.
[수정 1차 증거·명령](../../../tools/evidence/audit4-r2-ledger-get-bytes-unmetered/fix-round1/README.md)에
전체 Python 시험, R2 회귀, 실행기 Rust 시험과 변이 검증 결과를 기록한다.

## 수정 2차 — 작업 공간 루트의 Rust 선택

감독자의 다음 실행에서는 Python 전체 시험이 통과한 뒤 루트의 Cargo 명령이
전역 기본 도구 체인 부재로 실패했다. 실행기 디렉터리의 고정 파일은 루트에
적용되지 않는다. `ci.yml`의 작업 흐름 전체에 `RUSTUP_TOOLCHAIN=1.98.1`을
명시해 루트 포맷·린트·시험에도 같은 버전을 선택하고, README에 로컬 실행 명령과
오프라인 준비 조건을 기록했다. 루트 고정 파일은 이 노드의 허용 경로 밖이므로
추가하지 않았다. 전역 rustup 설정도 바꾸지 않았으며, 전역 기본값이 없는 로컬
루트 실행에는 문서화한 환경 지정이 필요하다.

새 회귀 시험은 기본값 없는 격리 rustup 홈에서 오류를 재현한 뒤 CI의 환경
지정으로 루트 Cargo 메타데이터 조회가 성공하는지 확인한다. CI와 실행기의
고정 버전 일치도 검사한다.

직접 재실행한 전체 Python 시험은 1,322개 실행·1,316개 통과·기존 건너뜀 6개,
실패/오류 0이다. R2 시험 125개와 새 회귀 2개도 모두 실행됐다.
루트 Rust 시험은 환경 지정 후 478개 통과·기존 무시 1개·실패 0,
별도 실행기 Rust 시험은 3개 통과했다. 본문 계량 연결만 제거한 변이 검증도
기대 실패 6개를 검출하고 종료 0으로 끝났다.
[수정 2차 증거·정확한 명령](../../../tools/evidence/audit4-r2-ledger-get-bytes-unmetered/fix-round2/README.md)에
전체 로그와 정합성 검사 결과를 기록한다.

## 수정 3차 — 감독자 실행 환경과 재검증

감독자의 재실행은 Python 전체 1,322개 통과 후 루트 Cargo의 기본 도구 체인
부재로 다시 실패했다. CI의 환경 변수는 별도로 시작한 감독자 프로세스에
전파되지 않는다. 루트 `rust-toolchain.toml`은 허용 경로 밖이므로 예외 승인을
요청했으며, 승인 없이 추가하거나 전역 rustup 설정을 바꾸지 않았다.
현재 허용 범위에서는 감독자가 자신의 Cargo 명령에 `+1.98.1` 또는
`RUSTUP_TOOLCHAIN=1.98.1`을 지정해야 한다. 기본 루트 명령 자체가 해결됐다고
주장하지 않는다.

직접 다시 실행한 전체 Python 시험은 1,322개 실행·1,316개 통과·기존 건너뜀
6개·실패/오류 0이다. R2 시험 125개와 본문 미터 연결 제거 변이 검증도
통과했다. Rust 버전을 명시한 루트 시험은 478개 통과·기존 무시 1개,
실행기 디렉터리의 Rust 시험은 환경 지정 없이 3개 통과했다.
[수정 3차 증거·명령·남은 환경 조건](../../../tools/evidence/audit4-r2-ledger-get-bytes-unmetered/fix-round3/README.md)에
전체 로그, 기본값 부재 재현과 명시적 도구 체인 선택 결과를 기록한다.

## 수정 4차 — 현재 작업 트리에 한정한 Rust 준비

감독자가 같은 기본 도구 체인 오류를 보고했다. 이번에는 설치된 `1.98.1`을
`rustup override set --path "$PWD" 1.98.1`로 현재 작업 트리 경로에 등록했다.
재정의는 rustup의 로컬 설정에 저장되며 전역 기본값이나 다른 작업 트리를
변경하지 않는다. 루트 고정 파일을 추가하지 않아 허용 경로 예외도 필요하지 않다.
이전 3차 기록의 미해결 루트 실행 조건은 현재 작업 트리에서 해소됐다.

환경 변수 없이 루트 `cargo test --all --locked --offline`를 직접 실행해
통과를 확인했다. README의 준비 명령도 같은 경로 재정의로 바꿨다.
새 회귀 시험은 격리 rustup 홈에서 전역 기본값 없이 재정의한 디렉터리의
일반 Cargo 호출이 성공하고, 별도 형제 디렉터리의 호출은 여전히 기본값
부재로 실패하는지 검사한다. 재정의는 Git에 포함되지 않으므로 새 작업 트리나
별도 감독자 환경에서는 README의 준비 명령을 실행해야 한다.

최종 전체 Python 시험은 1,323개 실행·1,317개 통과·기존 건너뜀 6개·실패/오류 0이다.
일반 루트 Cargo 시험은 478개 통과·기존 무시 1개, 별도 실행기 Rust 시험은 3개 통과했다.
R2 125개, 새 도구 체인 시험을 포함한 3개, 변이 검증, 포맷·Clippy·정합성 검사도 통과했다.

[수정 4차 증거·명령](../../../tools/evidence/audit4-r2-ledger-get-bytes-unmetered/fix-round4/README.md)에
전체 Python·Rust 시험, 원장 회귀, 변이 검증과 도구 체인 선택 결과를 기록한다.

## 증명 범위

실제 R2·외부 서비스·실제 자격 증명에 접근하지 않았다. 비용 정책·한도는 변경하지 않았다.
이 증거는 원본 보관 도구의 비용 통제 회귀에 한정한다. P02·P03의 실제 공시 확보율,
R2 관측 대조, 소비자 화면 또는 첫 출시 완료 증거를 대신하지 않는다.
