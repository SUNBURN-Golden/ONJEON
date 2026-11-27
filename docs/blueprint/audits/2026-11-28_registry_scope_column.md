# Audit 8 기관 분모의 ADR-0018 범위

`audit8-registry-scope-column` · 2026-11-28 · BLUEPRINT §7.1·V0 · 09 P01

우체국보험(`public-epost`)의 메모에는 포함 결정이 이미 기록돼 있었다. 협회 보험사 목록 53행만 읽으면 우체국보험이 빠지는 문제가 남아 있었다. 두 기관 목록에 `in_denominator`와 `scope_adr`를 추가하고 [ADR-0018](../../decisions/ADR-0018-보험-데이터-지식-기반의-정체성과-범위.md)을 기록했다.

| 원장 | `true` | `false` |
|---|---:|---:|
| [`insurers.csv`](../../../data/registry/insurers.csv) | 53 | 0 |
| [`cooperatives_and_others.csv`](../../../data/registry/cooperatives_and_others.csv) | 1 (우체국보험) | 15 (공제 13곳, 농협 구 공제 시드, 한국무역보험공사) |

기존 CSV 셀과 행 순서는 보존했다. 우체국보험은 `sector=other`와 `in_current_assoc_list=false`를 유지한다. 재보험 전업사와 서울보증보험은 기관을 추적하며, 대상 상품이 0이면 별도 근거를 기록한다. 54개 기관의 상품·특약·판매본은 미열거 상태다.

분모를 적재할 T-DT-04의 작업 계약과 작업명세에도 두 CSV와 `in_denominator=true` 선별을 명시했다. [과제 계약](../proposals/설계검토_결과/tasks.json).

## 재현과 결과

```sh
python3 -I tools/registry_check.py
python3 -I tools/registry_check.py --denominator
python3 -m unittest discover -s tools/tests -p 'test_registry*.py' -v
```

- 기본 CI 검사 명령은 새 열의 누락, 빈 값·잘못된 대소문자, ADR 참조 불일치, 우체국보험 행 누락과 포함·제외 값의 역전을 거부한다.
- `--denominator`는 두 CSV를 검증하고 포함 기관 ID 54개를 출력했다. 우체국보험은 정확히 한 번 포함되며, 임시 CSV에서 제외로 바꾸면 종료 코드 1과 오류를 반환하고 기관 ID 출력은 비운다. 두 실행에서 입력 CSV의 바이트는 동일했다.
- 원장 시험 93개가 통과했다. 정규화 후 두 CSV가 바이트 단위로 동일하며, 우체국보험의 상품 목록 상태는 `unqueried`, 공시 진입점 사유는 `disclosure_entry_missing`임을 확인했다. 작업 계약의 두 원장 참조와 우체국보험 포함 조건도 검사한다.

신규 원장 검사와 함께 어휘 검사, 표본 변이 자체 검사, 작업 계약 검사(기계 47/47·존재 72/72), 온톨로지 검사도 통과했다. Rust 워크스페이스 시험 566개가 통과했고 선언된 ABox 픽스처 재생성 시험 1개는 기본 설정대로 건너뛰었다. 삽입 순서 2개, 시나리오 API 4개, 온톨로지 실행기 4개, 실행기 검증(Python) 81개, CI 검사기 21개도 통과했다.

`tools/tests` 전체 탐색은 1,816개 중 1,810개 통과, 6개 건너뜀으로 끝났다. 건너뛴 시험은 실제 보관본이 필요한 5개와 이전 botocore가 필요한 1개다. 전체 탐색 시작 뒤 추가한 T-DT-04 작업 계약 시험은 위 원장 회귀 93개에 포함해 실행했다.

이 검증은 V0 기관 분모에 대한 기록이다. P01·P02 완료에는 실제 상품·특약·판매본 열거, 확보율 측정과 [09 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 완료 증거가 필요하다.
