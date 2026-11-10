# Audit 5: 설계 묶음의 T-OP-00·T-OP-09·결정 기록 상태 동기화

- 노드: `audit5-design-bundle-status-stale`
- 기록일: 2026-11-10
- 유형: 문서 정합성(현재 상태 표기)
- 완료 증거: [evidence README](../../../tools/evidence/audit5-design-bundle-status-stale/README.md)

## 1. 감리 지적

설계 검토 묶음의 여러 문서가 T-OP-00을 아직 없는 과제로, 또는 필수 시험 ID
33개 중 16개만 구현된 상태로 적고 있었다. T-OP-09도 "없음"으로 남아 있었다.
또 `09_제품목적_대응표.md`의 P02·P03·P11·P14·P17·P19(그리고 가격 표시를
공유하는 P09)가 D-06·D-07·D-08·D-12·D-14·D-16·D-18·O04를 여전히 미해결
결정처럼 읽히게 했다.

확인된 현재 상태:

- T-OP-00 모의 코어는 병합됐다(#21, 후속 #97). `dry_run.py --scenario all
  --require-all`이 필수 시험 ID 33개를 모두 실행하고 실패 0건이다.
- T-OP-09 실제 실행기 검증은 병합됐다(#98). R1~R22는 PASS 17·PARTIAL 5·
  FAIL 0이며, PARTIAL(R6·R7·R9·R11·R21)과 명세 공백 G51~G57, G47 일부가
  남은 후속이다. 이는 실제 가동·출시 완료 증거가 아니다.
- D-06·D-07·D-08·D-12·D-14·D-16·D-18·O04는 각각 DEC 기록이 있다. 결정
  기록과 남은 실행·등록 조건(게이트 등록, 접근 확인, 플래그 적용, 실제
  시험 회차, 외부 검토 담당 지정)은 다른 사안이다.

## 2. 수정

| 문서 | 수정 |
|---|---|
| [묶음 README](../proposals/설계검토_결과/README.md) | 판 이력의 "수정판 6차"를 실제 7차로 바로잡고, T-OP-00·T-OP-09를 병합·검증 상태와 남은 후속으로 바꿨다. 구현/설계 구분에서 데몬을 "전부 설계"로 묶지 않는다 |
| [02 구현계약](../proposals/설계검토_결과/02_구현계약.md) | 데몬 상태 기계 행을 "규칙 파일만 있음"에서 모의 구현·검증 및 실제 실행기 일부 검증(PARTIAL)으로 바꿨다 |
| [05 VM 실행준비](../proposals/설계검토_결과/05_VM실행준비.md) | 존재하지 않는다고 적었던 `dry_run.py` 실행을 실제 명령·`--require-all`·증거 링크로 바꿨다 |
| [그록봇 인계 README](../proposals/설계검토_결과/그록봇_인계/README.md) | 2026-10-13 당시의 16/33·T-OP-09 없음 상태를 역사 기록으로 명시하고, 단계 2·3과 10.1 표를 완료·병합 상태로 갱신했다. 남은 PARTIAL·공백은 그대로 남겼다 |
| [09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md) | P02·P03·P09·P11·P14·P17·P19의 DEC 인용에 "결정 기록됨"을 표시하고, "남은 조건"을 별도로 적었다. 기존 가격 표시 관문 문구와 잔여 조건 문구는 유지했다 |

결정 내용, 관문, 승인 상태, 실제 시험 결과는 바꾸지 않았다. 문서가 현재
상태를 잘못 말하던 부분만 고쳤다.

## 3. 회귀 시험

[`test_audit5_design_bundle_status_stale.py`](../../../tools/tests/test_audit5_design_bundle_status_stale.py)가
다음을 고정한다.

- 네 문서에 "T-OP-00·T-OP-09 없음", "규칙 파일만 있음", "16개만 구현",
  "이 도구는 아직 없다" 같은 낡은 현재상태 문구가 다시 들어오지 않는다.
- T-OP-00 33/33 실행, T-OP-09 PASS 17·PARTIAL 5·FAIL 0, 남은 후속이
  문서에 함께 적힌다.
- 09의 해당 행은 `결정 기록됨`과 `남은 조건`을 모두 가지며, DEC 파일이
  존재하고, P02·P09의 가격 표시 관문·O04 해결 문구가 유지된다.
- `dry_run.py --require-all`이 필수 시험 ID 33개를 실행하고 누락·목록 밖·
  중복이 0건임을 실제 실행으로 확인한다.

## 4. 증거

| 로그 | 내용 |
|---|---|
| [before.log](../../../tools/evidence/audit5-design-bundle-status-stale/before.log) | 수정 전 HEAD(d0cbde3)의 낡은 문구 |
| [focused.log](../../../tools/evidence/audit5-design-bundle-status-stale/focused.log) | 새 시험 + 기존 09·가격·데몬 시험 |
| [python-tests.log](../../../tools/evidence/audit5-design-bundle-status-stale/python-tests.log) | 전체 Python 시험 |
| [dry-run.log](../../../tools/evidence/audit5-design-bundle-status-stale/dry-run.log) | `--scenario all --require-all` 요약 |
| [status.log](../../../tools/evidence/audit5-design-bundle-status-stale/status.log) | `git diff --check`·`git status`·`spec_check.py` |

## 5. 범위와 한계

- 이 기록은 문서 정합성 finding의 완료 증거다. 실제 데몬 가동, 실제 벤더
  CLI 전체 확인, 공시 데이터 수집, 소비자 화면, 출시 완료 증거를 대신하지
  않는다.
- T-OP-09의 PARTIAL 5건과 G51~G57, G47 일부는 남은 후속이다. 해소된 것으로
  적지 않았다.
- `docs/PRINCIPLES.md`, `docs/data/`, `docs/design/CONSUMER_FLOW_SPEC.md`,
  `DECISION_REQUIRED.md`는 수정하지 않았다. commit·push·GitHub 호출·비밀값
  조회·외부 저장소 접근은 수행하지 않았다.
- `07_수정대응표.md`와 `재검토_요청_9554c96.md`의 "모의 코어·실제 실행기
  없음" 문구는 해당 판의 검토 대응 기록이므로 그 판 시점의 역사로 남겼다.
  현재 상태는 이 문서와 위 네 문서·09의 상태 기록을 따른다.
