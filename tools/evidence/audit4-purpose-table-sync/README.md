# Audit 4 — 09 "축소·후속" 셀 동기화 검증 증거

검증일: 2026-11-03. 노드: `audit4-purpose-table-sync`.
변경 범위와 한계는 [감리 기록](../../../docs/blueprint/audits/2026-11-03_purpose_table_sync.md)을 따른다.

저장소 루트에서 아래 명령을 실행했다. 새 문서 회귀 검사는 기존 CI의 Python 전체 발견 단계에서 자동 실행된다.

| 명령 | 결과 | 로그 |
|---|---|---|
| `python3 -m unittest tools.tests.test_purpose_table_decision_sync -v` (문서 수정 전) | 8개 실행, 하위 사례 실패 93·오류 1. 오래된 결정 대기·초안 전용 문구, 누락된 결정·잔여 조건·증거 연결 검출 | [수정 전](before.log) |
| `python3 -m unittest tools.tests.test_purpose_table_decision_sync tools.tests.test_product_purpose tools.tests.test_decisions_ledger_sync tools.tests.test_decision_records -v` | 56개 통과 | [집중 시험](focused.log) |
| `env -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -v` | 1,361개 실행·1,355개 통과·기존 건너뜀 6, 실패·오류 0 | [Python 전체](python-tests.log) |
| `cargo test --all --locked --offline` | 495개 통과·기존 무시 1, 실패 0. 내장 Python 39개·129개도 통과 | [Rust 전체](rust-tests.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4개 통과 | [온톨로지 실행기](ontology-runner-tests.log) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업 연결·9개 필수 시험 ID의 담당 과제 등록 일치 | [대응표 검사](product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 45/45·존재 검사 72/72 통과 | [명세 검사](spec-check.log) |
| `python3 -I tools/blueprint_status.py` | ADR/DEC 37개 파일 색인·내용 해시 일치 | [상태 검사](blueprint-status.log) |
| `python3 -I tools/blueprint_counts.py` | 현재 등록 수 일치 | [수치 검사](blueprint-counts.log) |
| HEAD 대비 P 행의 셀별 변경 대조·문서 상대 링크 검사·`git diff --check` | 여섯 축소·후속 셀만 변경, 모든 구현 작업·완료 증거 열 유지, 로컬 파일 링크 유효·공백 오류 없음 | [무결성 검사](integrity-check.log) |

새 회귀 검사 8개는 P03·P06·P11·P14·P17·P19 셀의 실질 결정 내용·위임/소유자 구분·잔여 조건, 직접 연결된 DEC 파일과 작업 게이트의 대응, 실제 완료 증거 요구와 문서 정합성 증거의 구분을 확인한다. 수정 전 오류 1개는 아직 없던 §7의 이 finding 증거 연결을 찾지 못한 결과다.

결정 기록을 게이트 등록이나 구현·실제 시험 완료로 바꾸지 않았다. 완료 증거 열은 유지한다. 이 증거는 문서 정합성 finding에만 해당하며, 실제 수집·검수·트윈·화면·이해도 시험·첫 출시 완료를 주장하지 않는다.
