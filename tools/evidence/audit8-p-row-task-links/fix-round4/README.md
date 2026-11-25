# Fix round 4: 허용 경로 밖 출시 증거 안내문 편집 되돌림

4차 리뷰의 차단 finding은 3차 수정이 이 노드의 허용 경로 밖에 있는
`docs/release-readiness/evidence/README.md`를 편집한 것이었다. 3차 수정은
그 파일의 `All P01–P19 rows` 문구를 `P01–P20`으로 바꿨지만, 이 노드의
allowed_paths에 `docs/release-readiness/**`가 없으므로 그 변경은 범위를
벗어난다.

| finding | 수정 |
|---|---|
| 차단 1: `docs/release-readiness/evidence/README.md`가 허용 경로 밖인데 편집됨 | 파일을 기준 커밋 상태로 되돌려 `P01–P19` 문구를 복원했다. 이 노드는 그 파일을 더 이상 수정하지 않는다 |
| 같은 finding의 회귀 시험 의존 | `tools/tests/test_audit8_completion_scope.py`에서 출시 증거 안내문 읽기·검사를 제거했다. 회귀 변이 검사는 허용 경로 안의 `docs/decisions/README.md`를 사용한다 |
| 후속 소유 명시 | [ADR-0022](../../../../docs/decisions/ADR-0022-제품-완료-범위-P20-확장.md) 결정 6과 본문 증거 README에 안내문 동기화를 안내문 소유자의 후속 항목으로 적었다 |

허용 경로 안의 완료 범위는 계속 P01~P20이다. 09 대응표, `tasks.json`,
판정기·진척 도구, 결정 원장 BP-D-23, BLUEPRINT §7·§9.5·§13,
ADR-0019·ADR-0020, CI 안내문의 시험 ID 수는 3차 수정 그대로 유지한다.
`docs/release-readiness/evidence/README.md`의 19행 문구는 이 노드가 고칠 수
없는 남은 후속 항목이며, 그 파일은 기준 커밋과 동일하다.

## 재실행 결과

명령과 전체 출력은 [static-checks.log](static-checks.log),
[python-tests.log](python-tests.log), [cargo-tests.log](cargo-tests.log),
[runner-verify-tests.log](runner-verify-tests.log),
[scenario-api-tests.log](scenario-api-tests.log),
[ontology-runner-tests.log](ontology-runner-tests.log)에 있다.

| 실행 | 결과 |
|---|---|
| `python3 -I tools/ci/check_product_purpose.py` | 통과, 09 P01..P20 연결 |
| `python3 -I tools/ci/check_product_purpose.py --selftest` | 5개 위반 검출·1개 정상 사례 통과 |
| `python3 -I tools/ci/check_pr_body_traceability.py --selftest` | 6개 위반 검출·8개 정상 사례 통과 |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 47/47, 존재 72/72, 전체 통과 |
| `python3 -I tools/blueprint_status.py` | ADR/DEC 44개 색인 최신 |
| `python3 -I tools/ci/check_deps.py` | 위반 없음 |
| `python3 -I tools/ci/check_leak.py` 및 `--selftest` | 위반 없음, selftest 통과 |
| `python3 -I tools/ci/check_skeleton.py` | 플래그 off, 노출 없음(정적) |
| `python3 -I tools/release_readiness/progress.py` | 0/20 행 닫힘, 20/67 과제 병합 |
| `python3 -I tools/release_readiness/check.py --json` | 예상 종료 1, 행 open 20·기능 open 64 |
| `python3 -m unittest discover -s tools/tests -v` | 1,799개 중 1,728개 통과, 71개 건너뜀, 실패·오류 0, 종료 0 |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과, 종료 0 |
| `cargo test --all --locked --offline` | 537개 통과, 1개 무시, 실패 0, 종료 0 |
| 시나리오 API의 `cargo test --locked --offline` | 4개 통과, 종료 0 |
| 온톨로지 실행기의 `cargo test --locked --offline` | 4개 통과, 종료 0 |

새 회귀 시험은 허용 경로 안의 문서·도구에서 20행 분모와 P20의 요구·과제
연결을 확인하고, 살아 있는 문서를 P01~P19로 되돌린 변이를 거부한다. 이
기록은 문서·도구 정합성 증거이며 실제 동의·삭제·복원·누출·롤백 실행
기록이나 P20 완료 증거가 아니다.
