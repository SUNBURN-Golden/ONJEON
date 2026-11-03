# Audit 4 결정 원장 동기화 검증 증거

검증일: 2026-11-03. 노드: `audit4-decisions-ledger-sync`.
변경과 검증의 한계는 [감리 기록](../../../docs/blueprint/audits/2026-11-03_decisions_ledger_sync.md)을 따른다.

저장소 루트에서 실행했다. 새 회귀 검사를 먼저 실행해 누락을 검출한 뒤 문서를 수정했다. 최종 전체 Python 재실행에는 09 증거 연결·인계 직접 링크 검사도 포함했다.

| 명령 | 결과 | 로그 |
|---|---|---|
| `python3 -m unittest tools.tests.test_decision_records tools.tests.test_decisions_ledger_sync -v` (문서 수정 전) | 30개 실행, 실패 20·오류 2(부분 사례 포함): 누락된 원장 행·색인 파일·해결 상태·인계 경로 검출 | [수정 전](before.log) |
| `python3 -m unittest tools.tests.test_decision_records tools.tests.test_decisions_ledger_sync tools.tests.test_price_display_scope tools.tests.test_storage_provider_docs -v` (최종 수정 후) | 58개 통과, 실패·오류 0 | [집중 시험](focused.log) |
| `env -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -v` | 1,353개 실행·1,347개 통과·기존 건너뜀 6, 실패·오류 0 | [Python 전체](python-tests.log) |
| `cargo test --all --locked --offline` | 495개 통과·기존 무시 1, 실패 0. 내장 Python 39개·129개도 통과 | [Rust 전체](rust-tests.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4개 통과 | [온톨로지 실행기](ontology-runner-tests.log) |
| `python3 -I tools/blueprint_status.py` | ADR/DEC 37개 파일 색인·내용 해시 일치 | [상태 검사](blueprint-status.log) |
| `python3 -I tools/blueprint_counts.py` | 현재 등록 수 일치 | [수치 검사](blueprint-counts.log) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업 연결·9개 필수 시험 ID 담당 과제 등록 일치 | [목적 대응표 검사](product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 45/45·존재 검사 72/72 통과 | [설계 명세 검사](spec-check.log) |

첫 전체 Python 실행은 1,352개 중 기존 클라우드 행의 M3 표기를 요구하는 문서 검사 1개가 실패했다([첫 실행](python-tests-first.log)). M3와 세부 관문을 함께 표기하도록 보완한 뒤 최종 집중 검사와 전체 Python을 재실행해 통과했다.

검증 범위는 DEC 전체 집합과 두 색인의 일대일 대응, 기존 결정 내용·위임 상태·실행 조건, O01·O04·O12 결정 질문 해결, D-02 구성·정책 소유자, 인계 직접 링크와 로컬 문서 링크다. BLUEPRINT §11의 기준일을 갱신하고 결정·관문 상태를 검토했다. 원본 DEC·작업 게이트·데몬 등록·실제 R2·제공자·개인자료에는 변경이나 접근이 없다.

이 로그는 문서 정합성 finding의 완료 증거다. 09 P01~P19의 실제 수집·검수·트윈·소비자 화면·이해도 시험·첫 출시 완료 증거를 대신하지 않는다.
