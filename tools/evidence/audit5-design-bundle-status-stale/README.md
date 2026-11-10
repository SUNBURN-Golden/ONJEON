# audit5-design-bundle-status-stale evidence

기록일: 2026-11-10. 노드: `audit5-design-bundle-status-stale`.
감리 지적: 설계 묶음의 여러 문서가 T-OP-00을 아직 없는 과제로, 또는
필수 시험 ID 33개 중 16개만 구현된 상태로 적었고, T-OP-09도 "없음"으로
남아 있었다. `09_제품목적_대응표.md`의 P02·P03·P11·P14·P17·P19(가격
표시를 공유하는 P09 포함)는 D-06·D-07·D-08·D-12·D-14·D-16·D-18·O04에
DEC 기록이 있는데도 미해결 결정처럼 읽혔다.

수정: 네 문서의 T-OP-00·T-OP-09 상태를 병합·검증 결과와 남은 PARTIAL·
명세 공백으로 갱신하고, 09의 해당 행에 "결정 기록됨"과 "남은 조건"을
분리해 적었다. 결정 내용·관문·승인 상태·실제 시험 결과는 바꾸지 않았다.
감리 기록: [2026-11-10_design_bundle_status_stale.md](../../../docs/blueprint/audits/2026-11-10_design_bundle_status_stale.md).

## 로그

| 파일 | 명령 | 결과 |
|---|---|---|
| [before.log](before.log) | 수정 전 HEAD(d0cbde3) 문서에서 낡은 문구 확인 | 4개 문서에서 낡은 현재상태 문구 확인, 09에는 "결정 기록됨" 표기 없음 |
| [focused.log](focused.log) | `test_audit5_design_bundle_status_stale` + 기존 09·가격·데몬 시험 | 모두 통과 |
| [python-tests.log](python-tests.log) | `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools/tests -v` | 1,485건 실행, 실패·오류 0, 건너뜀 6 |
| [dry-run.log](dry-run.log) | `python3 -I tools/daemon/dry_run.py ... --scenario all --require-all --quiet` | 종료 코드 0, 필수 시험 ID 33/33, 누락·목록 밖·중복 0 |
| [status.log](status.log) | `spec_check.py`·`git diff --check`·`git status` | 통과·공백 오류 없음 |

`before.log`는 수정 전 문서를 `git show HEAD:`로 읽어 보존한 것이다.
새 시험은 수정된 작업 트리를 읽으므로, before 로그는 grep으로 낡은 문구의
존재를 기록하고 focused 로그는 그 문구가 사라진 현재 상태를 검증한다.

## 범위

문서 정합성 수정이며 실제 데몬 가동·벤더 CLI 전체 확인·공시 데이터 수집·
소비자 화면·출시 완료 증거가 아니다. T-OP-09의 PARTIAL 5건(R6·R7·R9·
R11·R21)과 명세 공백 G51~G57, G47 일부는 남은 후속이다. Cargo·온톨로지
코드는 변경하지 않았으므로 Rust 시험은 실행하지 않았다.
`docs/PRINCIPLES.md`, `docs/data/`, `docs/design/CONSUMER_FLOW_SPEC.md`,
`DECISION_REQUIRED.md`는 수정하지 않았다. commit·push·GitHub 호출·비밀값
조회·외부 저장소 접근은 수행하지 않았다.
