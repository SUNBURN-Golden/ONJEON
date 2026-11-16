# audit6-blueprint-s11-current-state 수정 1차 실행 증거

노드: `audit6-blueprint-s11-current-state`.
기록일: 2026-11-16 KST(대조 기준일 2026-11-16 UTC).
대상: [BLUEPRINT §11 데이터 행](../../../../docs/BLUEPRINT.md),
[감리 기록 수정 1차](../../../../docs/blueprint/audits/2026-11-16_blueprint_s11_current_state.md).

검토 finding: §11이 `근거 66`을 보고하지만 `data/registry/sources.csv`는
2026-11-10 감독당국 재조회 9건을 포함해 75건이다. 초회 회귀 시험 7개는
이 불일치를 검출하지 못했다.

## 정정 내용

- §11 데이터 행: `근거 66` → `근거 75(2026-10-09 1차 조사 66건 +
  2026-11-10 감독당국 재조회 9건, data/registry/sources.csv)`.
  내역은 `sources.csv`의 `retrieved_at` 실측(66 + 9 = 75)이다.
- 회귀 시험 2개 추가(`tools/tests/test_blueprint_current_state.py`):
  네 목록 수(보험사·공제 등·제외/과거·근거)를 각 CSV 행 수와 대조,
  근거 총합·관측일별 내역을 `sources.csv`와 대조.
- `python3 -I tools/blueprint_status.py --write`로 §11 기준일·결정 색인
  대조일을 2026-11-16(UTC)으로 갱신, 상단 갱신일도 일치시킴.
  ADR·DEC 내용 해시 불변.
- 감리 기록에 수정 1차 절 추가, 초회 검증 표는 역사 기록으로 보존.

## 명령과 결과

저장소 루트에서 실행했다. 로그는 로컬 실행의 표준 출력·오류이며 수락 결과는
명령의 종료 코드와 함께 아래에 기록한다.

| 명령 | 결과 | 로그 |
|---|---|---|
| `python3 -I -m unittest discover -s tools/tests -p test_blueprint_current_state.py -v` (문서 수정 전) | 의도된 실패: `66 != 75`(sources CSV 대조)·관측일 내역 부재 검출, 종료 1 | [before.log](before.log) |
| 같은 명령 (수정 후) | 9개 통과, 종료 0 | [focused.log](focused.log) |
| `python3 -I -m unittest discover -s tools/tests -p 'test_blueprint*.py' -v` | 73개 통과, 종료 0 | [blueprint-tests.log](blueprint-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` (README 명령) | 1,665개, 실패·오류 0, 기존 건너뜀 6개, 종료 0 | [python-tests.log](python-tests.log) |
| `cargo test --all --locked --offline` (작업 트리 전용 target) | 532개 통과, 기존 무시 1개, 실패 0, 종료 0 | [rust-tests.log](rust-tests.log) |
| `cargo build --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml` (같은 target) | 빌드 성공, 종료 0 | [ontology-build.log](ontology-build.log) |
| `cargo test --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml` (같은 target) | 4개 통과, 종료 0 | [ontology-tests.log](ontology-tests.log) |
| `python3 -I tools/blueprint_counts.py` | 엔진 등록 266 + doctest 3, 실제 조항 7, 변조 40, 어휘 49 일치, 종료 0 | [counts.log](counts.log) |
| `python3 -I tools/blueprint_status.py` | ADR·DEC 37개 색인 일치, 종료 0 | [status.log](status.log) |
| `python3 -I tools/vocab_check.py` | 종료 0 | [vocabulary.log](vocabulary.log) |
| `python3 -I tools/validation_check.py` | 종료 0 | [validation.log](validation.log) |
| `python3 -I tools/validation_check.py --selftest` | 변조 40종 통과, 종료 0 | [tamper-tests.log](tamper-tests.log) |
| `python3 -I tools/registry_check.py` | 종료 0 | [registry-check.log](registry-check.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 46/46·존재 72/72 통과, 종료 0 | [spec-check.log](spec-check.log) |
| `python3 -I tools/release_readiness/check.py --json` | P행 19·기능 64 모두 open, closed/excluded=0. **종료 1(제품 미완료)** | [readiness.json](readiness.json), [종료 코드](readiness-exit.log) |
| 허용 경로·보호 파일·링크·공백 검사 | 허용 경로만 변경, 보호 파일 불변, 링크·공백 정상 | [scope.log](scope.log) |

## 해석과 범위

`before.log`는 문서 수정 전 새 검사가 finding의 불일치(`66 != 75`)를
검출하는지 확인한 실패 기록이다. 건너뜀 6개는 초회와 같은 조건부
건너뜀(비공개 원본 미설정 2, 로컬 보관본·추출기 조건 미충족 3, 구버전
SDK 분기 1)이며 새 회귀 검사에는 건너뜀이 없다.

Rust 로그에 대해: 환경의 공용 `CARGO_TARGET_DIR`(`/workspace/onjeon-run/shared-target`)을
다른 작업 트리(`audit6-blueprint-s12-decisions-sync`)의 동시 실행이 덮어써,
그 작업 트리 경로가 박힌 바이너리가 이 작업 트리에서 실행되며 `api-types`·
`contracts` 시험이 NotFound로 실패했다(코드 변경과 무관). 해당 크레이트
clean으로도 동시 재빌드와 경합이 계속돼, 최종 Rust·온톨로지 실행은
`CARGO_TARGET_DIR="$PWD/target"`(작업 트리 전용)으로 재빌드·재실행했다.
명령 자체는 README와 같으며 결과는 초회와 동일(532 통과·무시 1, 실행기 4)하다.

`설계통합안_검토본.md`·`인계_설계책임/README.md`의 `근거 66`은 2026-10-12
작성 당시로 고정된 검토본·인계 기록이라 정정하지 않았다. 현재 현황 주장인
§11과 `data/registry/README.md`는 둘 다 75건으로 일치한다.

출시 판정기 결과의 종료 1은 정본 등록부의 완료 증거가 없다는 관측이며
이 문서 finding의 실패가 아니다. 실제 공시·상품/계약 트윈·소비자 화면·
P01~P19 전체·T-OP-08 완료·출시 승인을 선언하지 않는다.
보호 파일 변경·commit·push·GitHub 호출·비밀값 조회·실제 R2/AI 제공자/
프로덕션 접근은 수행하지 않았다. 로그는 행 끝 공백과 파일 끝 빈 줄만 정리했다.
