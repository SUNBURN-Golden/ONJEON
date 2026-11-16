# audit6-blueprint-s11-current-state 실행 증거

노드: `audit6-blueprint-s11-current-state`.
기록일: 2026-11-16 KST(대조 기준일 2026-11-15 UTC).
대상: [BLUEPRINT §9.2·§11](../../../docs/BLUEPRINT.md),
[감리 기록](../../../docs/blueprint/audits/2026-11-16_blueprint_s11_current_state.md).

## 명령과 결과

저장소 루트에서 실행했다. 로그는 로컬 실행의 표준 출력·오류이며 수락 결과는
명령의 종료 코드와 함께 아래에 기록한다.

| 명령 | 결과 | 로그 |
|---|---|---|
| `python3 -I -m unittest discover -s tools/tests -p test_blueprint_current_state.py -v` (문서 수정 전) | 의도된 실패: 현재 판정 열·구현/출시 증거 행·감리 링크 누락 검출 | [before.log](before.log) |
| 같은 명령 (수정 후) | 7개 통과, 종료 0 | [focused.log](focused.log) |
| `python3 -I -m unittest discover -s tools/tests -p 'test_blueprint*.py' -v` | 71개 통과, 종료 0 | [blueprint-tests.log](blueprint-tests.log) |
| `python3 -I tools/blueprint_counts.py` | 엔진 등록 266 + doctest 3, 실제 조항 7, 변조 40, 어휘 49 일치, 종료 0 | [counts.log](counts.log) |
| `python3 -I tools/blueprint_status.py` | ADR·DEC 37개 색인 일치, 종료 0 | [status.log](status.log) |
| `python3 -I tools/vocab_check.py` | 종료 0 | [vocabulary.log](vocabulary.log) |
| `python3 -I tools/validation_check.py` | 종료 0 | [validation.log](validation.log) |
| `python3 -I tools/validation_check.py --selftest` | 변조 40종 통과, 종료 0 | [tamper-tests.log](tamper-tests.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 46/46·존재 72/72 통과, 종료 0 | [spec-check.log](spec-check.log) |
| `python3 -I tools/release_readiness/check.py --json` | P행 19·기능 64 모두 open, closed/excluded=0. **종료 1(제품 미완료)** | [readiness.json](readiness.json) |
| `cargo build --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml` | 빌드 성공, 종료 0 | [ontology-build.log](ontology-build.log) |
| `cargo test --all --locked --offline` | 532개 통과, 기존 무시 1개, 실패 0, 종료 0 | [rust-tests.log](rust-tests.log) |
| `cargo test --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml` | 4개 통과, 종료 0 | [ontology-tests.log](ontology-tests.log) |

추가 전체 검증:

| 명령 | 결과 | 로그 |
|---|---|---|
| `python3 -I -m unittest discover -s tools/tests -v` (첫 실행) | 1,646개 중 날짜 일치 검사 1개 실패, 건너뜀 72개. 상단을 UTC 기준일에 맞춰 수정 | [python-tests-initial-date.log](python-tests-initial-date.log) |
| 같은 명령 (날짜 수정 후) | 1,646개, 실패·오류 0, 건너뜀 72개, 종료 0 | [python-tests-isolated.log](python-tests-isolated.log) |

격리 실행의 건너뜀에는 `-I`가 사용자 설치 boto3를 읽지 못해 생긴 항목이
포함된다. README의 일반 실행 명령으로 다시 검증했다.

| 명령 | 결과 | 로그 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -v` | 1,646개 중 1,640개 통과·기존 건너뜀 6개, 실패·오류 0, 종료 0 | [python-tests.log](python-tests.log) |
| 허용 경로·보호 파일·로컬 링크·공백 검사 | 허용 경로만 변경, 보호 파일 불변, 링크·공백 정상 | [scope.log](scope.log) |

최종 건너뜀 6개는 비공개 원본 미설정 2개, 로컬 보관본·추출기 조건 미충족
3개, 설치된 botocore가 조건부 쓰기를 지원해 적용되지 않는 구버전 시험 1개다.
추가한 회귀 시험의 건너뜀은 없다. 로그는 행 끝 공백과 파일 끝 빈 줄만 정리했다.

## 해석과 범위

`before.log`는 문서 수정 전 새 검사가 누락을 검출하는지 확인한 실패 기록이다.
현재 등록 수와 전체 Rust 실행 통과 수는 다른 분모다. DB 구현 범위는 기존
`infra/db/` 코드·시험 기록과 대조했으며 이번 노드의 DB 재실행·운영 적용
증거가 아니다. Flutter가 설치되지 않아 모바일 시험은 이번에 재실행하지
않았다. 기능 화면·전 화면 상태 카탈로그·사용자 이해 시험은 미완료다.

출시 판정기 결과의 종료 1은 정본 등록부의 완료 증거가 없다는 관측이며
이 문서 finding의 실패가 아니다. 실제 공시·상품/계약 트윈·소비자 화면·
P01~P19 전체·T-OP-08 완료·출시 승인을 선언하지 않는다.
보호 파일 변경·commit·push·GitHub 호출·비밀값 조회·실제 R2/AI 제공자/
프로덕션 접근은 수행하지 않았다.
