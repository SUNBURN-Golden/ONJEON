# Audit 3: 위임 결정 상태 — fix round 1

2026-10-29. 검토 지적: O12의 잠정 상태·잔여 조건이 독립 메모에만 있고 정본 원장에는 구현 전 미정으로 남아 있었다.

BLUEPRINT §11·§12와 결정 원장 §3의 O12 행·§3.1 DEC-O12 색인을 갱신했다. DEC-D-02와 DEC-O12는 위임 결정·가역·사용자 확정 아님인 잠정 개발 기준이다. 소유자 확정 근거를 추가하거나 실제 게이트를 등록하지 않았다. D-02의 접근·월 한도·정책 소유자 확인 조건은 유지한다.

O12는 T-TW-04·T-TW-05의 release 게이트에만 해당한다. 설계·합성 시험·병합은 가능하며 M2 전체 개발을 막지 않는다. 게이트 등록과 연산별 S6(allow-list·스키마 거부, 경계/unknown/range 합성 시험, 변이 시험, T-KN-08 실제 표본, 바이트 동일 결정성, trace evidence_ref 사슬)는 별개다. S6 미충족 연산은 병합해도 capability-blocked로 유지한다.

`tools/tests/test_decision_records.py`에 O12 정본 상태·링크, tasks.json의 release 범위 대조, S6 잔여 조건, §11의 두 결정 상태 검증을 추가하고 기존 색인 검사에 DEC-O12를 포함했다. 정본 수정 전 실행은 24개 중 실패 2개·오류 3개로 누락을 검출했으며 수정 후 24개가 통과했다.

| 명령 | 결과 | 실행 기록 |
|---|---|---|
| `python3 -B -m unittest tools.tests.test_decision_records -v` | 24개 통과 | [decision-records.log](decision-records.log) |
| `python3 -B -m unittest discover -s tools/tests -v` | 1,295개 실행, OK (6개 skip) | [python-tests.log](python-tests.log) |
| `cargo test --all` | 475개 통과, 1개 ignored, 실패 0 | [cargo-tests.log](cargo-tests.log) |
| `python3 -I tools/blueprint_status.py` | ADR/DEC 37개 색인 일치 | [blueprint-status.log](blueprint-status.log) |
| `python3 -I tools/blueprint_counts.py` | 현재 등록 수 일치 | [blueprint-counts.log](blueprint-counts.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 45/45, 존재 검사 72/72 통과 | [spec-check.log](spec-check.log) |

모든 명령은 종료 코드 0이다. Python skip은 보관 원본 경로가 없는 2개, 로컬 원본·pdftotext가 필요한 재현 시험 3개, 설치된 botocore가 조건부 쓰기를 지원해 적용되지 않는 구버전 시험 1개다. Rust ignored는 `regenerate_declared_abox_fixture`다. `git diff --check`도 통과했다.

이 증거는 문서 정합성·저장소 회귀 검증이며 실제 약관 검증, 사용자 확정, production 승인, S6 충족 또는 제품 출시 완료 증거가 아니다.
