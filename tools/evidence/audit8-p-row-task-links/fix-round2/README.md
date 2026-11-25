# Fix round 2: main 병합 충돌 해소

`origin/main`(d1b7833, M1 공유 계약 소유권)과 이 노드의 P행 연결 변경
(fa7930f)이 만나는 지점에서 병합 충돌이 났다. 충돌 파일은
[09 제품목적 대응표](../../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md)
하나였고, 양쪽 의도를 모두 남겨 해소했다. 병합 기준은
`1945f7afcd504a36f186c6fbba4544e3236afa02`다.

| 위치 | 이 노드 의도(유지) | main 의도(유지) | 해소 |
|---|---|---|---|
| P02 | `T-DT-04`·`T-AP-04`가 인용 시험을 소유 | `T-CT-10`이 M1 공유 계약을 소유 | 과제 목록에 두 세트 모두 등록 |
| P03 | `T-WB-01`과 `npm test -- releases` 릴리스 렌더링 증거 | `T-CT-10` M1 계약 소유 | 두 과제를 함께 등록하고 더 구체적인 릴리스 렌더링 증거 문구 유지 |
| P08 | `T-MB-04`와 `what_if_boundary_days` 모바일 경계일 증거 | `T-CT-10`과 `ParameterTable 공시값` 입력 단계 서술 | 두 과제를 함께 등록하고 모바일 증거 유지, 입력 단계는 `ParameterTable 공시값`으로 구체화 |
| §7 | Audit 8 P행 시험 연결 검증 기록 | Audit 8 M1 계약 소유권 검증 기록 | 두 불릿을 모두 보존 |

`test_m1_contract_ownership.py`의 P02·P03·P05·P08 T-CT-10 연결 기대와
`check_product_purpose.py`의 P02·P03·P08 담당 과제 기대, 그리고 P03·P08의
릴리스·모바일 시험 기대를 함께 만족한다. 병합은 문서와 시험만 바꾸며
P01~P20의 실제 완료 증거를 만들지 않는다.

## 재실행 결과

| 실행 | 결과 |
|---|---|
| `python3 -m unittest discover -s tools/tests -v` | 1,792개 중 1,786개 통과, 기존 환경 조건으로 6개 건너뜀, 종료 0: [python-tests.log](python-tests.log) |
| `cargo test --all --locked --offline` | 실패 0, 종료 0: [cargo-tests.log](cargo-tests.log) |
| `python3 -I tools/ci/check_product_purpose.py` | 통과(종료 0) |
| `python3 -I tools/ci/check_pr_body_traceability.py --selftest` | 통과 |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 47/47, 존재 72/72 통과 |
| `python3 -I tools/release_readiness/progress.py` | P20 포함 0/20 행 닫힘, 20/67 과제 병합 |
| `python3 -I tools/release_readiness/check.py --json` | 미완료이므로 예상 종료 1 |

정적 검사 전체 기록은 [static-checks.log](static-checks.log)에 있다. 실제
동의·삭제·복원·누출·롤백 실행 기록은 P20의 출시 증거로 별도 수집해야 한다.
