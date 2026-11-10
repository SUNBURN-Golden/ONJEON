# Audit 5 — BLUEPRINT §11 현황·수치·경로 재검증

기록일: 2026-11-10. 노드: `audit5-blueprint-s11-refresh`.
기준 커밋: `0d9e73c215889d9fe007c27ab5a8e5f5395c36ef` + 이 노드의 미커밋 변경.
연결: BLUEPRINT §11, [09 제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의
문서·수치 완료 증거 기반.

## 감리 지적과 현재 대조

감리 지적 중 자동 생성 표·어휘 축·원장 범위·R2 전환·개발 도구 항목은
선행 감리 수정이 이미 현재 트리에 반영돼 있었다. 이번 노드는 남아 있던
손으로 적은 역사적 수치의 현재값 오해, 상단 날짜, `BUDGET.md`의 불완전한
경로를 고치고, 감리 지적 전체를 회귀 시험으로 고정했다. 결정 내용과
관문 판정은 바꾸지 않았다.

| 감리 지적 | 현재 대조 결과·재발 방지 |
|---|---|
| Rust 시험 42건으로 표기 | 자동 생성 표는 2026-11-10 현재 단위·통합 248건 + doctest 3건이다. 코드 행의 42건은 2026-10-09 당시 39 + doctest 3의 역사적 값임을 명시하고 현재 등록 수는 아래 자동 생성 표에서 대조하도록 고쳤다. §13의 같은 설명도 현재 표와 재실행 증거를 구분한다 |
| 실제 조항 규칙 8건 | 자동 생성 표·ADR-0014·실제 픽스처 모두 7건이다. 손으로 적은 8건은 남아 있지 않다 |
| 자체 시험 28건 | 자동 생성 표는 `validation_check.mutations()` 기준 40건이다. 손으로 적은 28건은 남아 있지 않다 |
| `tools/daemon` 누락 | §11 개발 도구 행에 `tools/daemon/`과 `tools/daemon/runner_verify/`가 있고 가동 승인 경계를 밝힌다 |
| 어휘 31축 | 자동 생성 표·`vocabulary.json` 모두 49축이다. §11에 수기 축 수는 없다 |
| 원장이 O01~O12로 표기 | 결정 원장과 §12는 O17·O19까지 이어진다. `O01~O12` 문구는 남아 있지 않다 |
| `BUDGET.md §6` 경로 누락 | `infra/r2/BUDGET.md §6`으로 고쳤다. 파일도 존재한다 |
| V1·GAP_REPORT의 S3 잔여 조건 | V1 남은 조건은 파생 6건 재생성·재현, 다른 계열 AI 검수, S1·S6이며 보관소는 ADR-0016의 Cloudflare R2다. GAP_REPORT도 R2·ADR-0016을 명시한다. 선행 `test_storage_provider_docs`가 함께 검사한다 |
| 상단·§11 날짜가 2026-10-09 | 상단은 `2026-10-09 최초 작성·채택`과 `2026-11-10 현황 갱신(§11)`을 함께 적고, §11 제목은 2026-11-10이다 |

## 회귀 시험

[tools/tests/test_blueprint_s11_refresh.py](../../../tools/tests/test_blueprint_s11_refresh.py)는
감리 지적별로 실패하도록 작성했다. 검사 항목은 상단·§11 날짜 일치,
역사적 42건의 명시와 자동 생성 표 포인터, `31개 축`·`O01~O12`·이전 S3
잔여 문구 부재, 모든 `BUDGET.md` 참조의 `infra/r2/` 경로, §11 수기 축 수
부재, 원장·§12의 O17·O19, V1·GAP_REPORT의 R2 결정, 자동 생성 표의 실제
조항·변조·축 수와 현재 원천 일치, 개발 도구 행, 감리 기록 링크다.
Rust 등록 수는 Cargo 실행이 필요한 기존 `blueprint_counts.py` 검사에
맡기고 이 시험에서는 고정하지 않는다.

수정 전 실행은 [before.log](../../../tools/evidence/audit5-blueprint-s11-refresh/before.log)처럼
9건 중 5건이 실패해 지적된 문구·경로·날짜를 검출했다. 수정 후 집중
실행과 전체 Python 시험 결과는 [evidence README](../../../tools/evidence/audit5-blueprint-s11-refresh/README.md)에
명령·종료 코드와 함께 기록한다. 새 시험은 기존 CI의
`python3 -m unittest discover -s tools/tests -v`에 포함된다.

## 검증·범위

| 로컬 실행 | 결과 | 증거 |
|---|---|---|
| 현재 등록 수 대조 | Rust 248 + doctest 3, 실제 조항 7, 변조 40, 어휘 49 일치 | [counts.log](../../../tools/evidence/audit5-blueprint-s11-refresh/counts.log) |
| 결정 색인 | ADR·DEC 37개 일치, §11 2026-11-10 | [status.log](../../../tools/evidence/audit5-blueprint-s11-refresh/status.log) |
| 집중 회귀 시험 | 9건 통과 | [focused.log](../../../tools/evidence/audit5-blueprint-s11-refresh/focused.log) |
| Python 전체 시험 | 1,459건 중 실패·오류 0, 기존 조건부 건너뜀 60건 | [python-tests.log](../../../tools/evidence/audit5-blueprint-s11-refresh/python-tests.log) |
| Rust 전체 시험 | 513건 통과, 실패 0, 기존 무시 1건 | [rust-tests.log](../../../tools/evidence/audit5-blueprint-s11-refresh/rust-tests.log) |
| 온톨로지 실행기 시험 | 4건 통과 | [ontology-tests.log](../../../tools/evidence/audit5-blueprint-s11-refresh/ontology-tests.log) |
| 허용 경로·보호 문서 | 허용 경로만 변경, 보호 문서 불변 | [scope.log](../../../tools/evidence/audit5-blueprint-s11-refresh/scope.log) |

자동 생성 표의 Rust 수는 무시된 시험도 포함한 등록 수이므로 실행 통과
수와 구분한다. 원본 58키·파생 v2 61키의 R2 대조는 2026-10-09 관측
기록이며 이번 갱신에서 R2에 접근하지 않았다. 실제 공시 데이터·소비자
화면·P01~P19 첫 출시 완료 증거나 T-OP-08 출시 판정을 대신하지 않는다.
commit·push·GitHub 호출·비밀값 조회·외부 저장소 접근은 수행하지 않았다.
