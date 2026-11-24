# Fix round 3: 완료 범위·결정 기록 정합화

> 4차 수정에서 이 라운드가 편집한 `docs/release-readiness/evidence/README.md`는
> 허용 경로 밖이어서 기준 상태로 되돌려졌다. [fix-round4](../fix-round4/README.md)를 따른다.

Audit 8 3차 리뷰의 차단 finding은 P20을 추가한 뒤에도 살아 있는 문서가
19행 분모를 말하고, 완료 범위 변경을 기록한 대체 ADR·원장 항목이 없다는
것이었다. 비차단 finding은 출시 증거 안내문의 옛 시험 수치와 CI 안내문의
시험 ID 개수였다.

| finding | 수정 |
|---|---|
| 차단 1: `docs/release-readiness/evidence/README.md`가 P01–P19를 분모로 설명 | P01–P20으로 고치고 `tools/tests/test_audit8_completion_scope.py`가 판정기·진척 도구·안내문의 20행 분모를 대조 |
| 차단 2: ADR-0019·ADR-0020·결정 원장이 P01~P19를 완료 범위로 유지 | [ADR-0022](../../../../docs/decisions/ADR-0022-제품-완료-범위-P20-확장.md)를 추가하고 두 ADR의 완료 행 수만 대체. 결정 원장에 BP-D-23을 추가하고 BLUEPRINT §7·§9.5·§13과 결정 색인을 동기화 |
| 비차단 3: 본문 증거 README의 시험 수치가 첨부 로그와 불일치 | 최종 실행(fix-round3)을 가리키도록 표를 갱신하고 1·2차 수치를 당시 기록으로 명시 |
| 비차단 4: `tools/ci/README.md`의 "nine product-purpose test IDs" | 11개 ID에 맞게 "eleven"으로 수정 |

## 재실행 결과

명령과 전체 출력은 [static-checks.log](static-checks.log),
[python-tests.log](python-tests.log), [cargo-tests.log](cargo-tests.log)에 있다.

| 실행 | 결과 |
|---|---|
| `python3 -I tools/ci/check_product_purpose.py` | 통과, 09 P01..P20 연결 |
| `python3 -I tools/ci/check_pr_body_traceability.py --selftest` | 6개 위반·8개 정상 사례 통과 |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 47/47, 존재 72/72 |
| `python3 -I tools/blueprint_status.py` | ADR/DEC 44개 색인 최신 |
| `python3 -I tools/ci/check_deps.py` | 위반 없음 |
| `python3 -I tools/ci/check_leak.py` 및 `--selftest` | 위반 없음, selftest 29개 위반 검출 |
| `python3 -I tools/ci/check_skeleton.py` | 플래그 off, 노출 없음(정적) |
| `python3 -I tools/release_readiness/progress.py` | 0/20 행 닫힘, 20/67 과제 병합 |
| `python3 -I tools/release_readiness/check.py --json` | 예상 종료 1, 행 open 20·기능 open 64 |
| `python3 -m unittest discover -s tools/tests -v` | 1,800개 중 1,729개 통과, 71개 건너뜀, 실패·오류 0, 종료 0 |
| `cargo test --all --locked --offline` | 537개 통과, 1개 무시, 실패 0, 종료 0 |
| `python -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과, 종료 0 |
| 시나리오 API의 `cargo test --locked --offline` | 4개 통과, 종료 0 |
| 온톨로지 실행기의 `cargo test --locked --offline` | 4개 통과, 종료 0 |

새 회귀 시험은 20행 분모와 P20의 요구·과제 연결을 확인하고, 살아 있는
문서를 P01~P19로 되돌린 변이를 거부한다. 이 기록은 문서·도구 정합성
증거이며 실제 동의·삭제·복원·누출·롤백 실행 기록이나 P20 완료 증거가
아니다.
