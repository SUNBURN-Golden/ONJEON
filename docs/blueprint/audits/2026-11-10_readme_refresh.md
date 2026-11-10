# Audit 5 — README ADR·DEC 색인과 문서 위계 재검증

기록일: 2026-11-10. 노드: `audit5-readme-refresh`.
기준 커밋: `ff15bc8` + 이 노드의 미커밋 변경.
연결: [BLUEPRINT](../../BLUEPRINT.md) §0.1·§11,
[결정 원장](../DECISIONS.md),
[09 제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의
문서 완료 증거 기반.

## 감리 지적과 현재 대조

감리 지적은 루트 [README](../../../README.md)의 ADR 목록이 0011까지만
있고, 폐기된 “불변 원칙 → 제2부 → 제3부 → 제1부” 우선순위 문구가 남아
있다는 것이다. 작업 트리에서 대조한 결과 두 지적 모두 선행
`audit4-readme-drift`(`1ee1dac`)에서 이미 해소돼 있었다.

| 감리 지적 | 현재 대조 결과 | 이번 조치 |
|---|---|---|
| ADR 목록이 0011까지만 | ADR 0001~0019를 모두 나열하며 `docs/decisions/ADR-*.md`와 양방향 대조된다 | 내용은 유지하고 중복·역순 검사를 추가 |
| DEC 기록 미안내 | `DEC-*.md`와 결정 게이트 기록을 같은 디렉터리로 안내한다. D/O/CANON 17개 기록이 존재한다 | 실제 계열 이름(`DEC-D-xx`·`DEC-Oxx`·`DEC-CANON-*`·`DEC-BUNDLE-STATUS`)을 명시하고 모든 `DEC-*.md`가 계열에 속하는지 시험 |
| 폐기된 문서 우선순위 | 우선순위는 [BLUEPRINT §0.1 문서 위계](../../BLUEPRINT.md#01-문서-위계) 링크를 따르며 옛 문구는 없다 | 기존 금지 시험을 유지하고 변이로 재검증 |

[결정 원장 §2 충돌 해소표](../DECISIONS.md#2-충돌-해소표)는 “제2부가 항상
제3부보다 우선”을 과거 기준으로 정정한다. README는 이 위계를 다시
정의하지 않고 §0.1로 위임하므로 충돌이 재발하지 않는다.

## 회귀 시험

[tools/tests/test_readme_index.py](../../../tools/tests/test_readme_index.py)의
`DecisionsRow`에 두 검사를 보강했다.

- `test_adr_numbers_are_listed_once_in_ascending_order`: ADR 번호가 문서
  순서대로 한 번씩만 나열되는지 확인한다. 기존 양방향 집합 대조가 놓치는
  중복·역순 색인을 검출한다.
- `test_dec_record_families_are_named_and_cover_every_record`: README 행이
  `DEC-D-xx`·`DEC-Oxx`·`DEC-CANON-*`·`DEC-BUNDLE-STATUS` 계열을 안내하고,
  디렉터리의 모든 `DEC-*.md`가 그 계열 중 하나에 속하는지 확인한다.

`DocumentHierarchy`의 기존 두 시험은 §0.1 링크의 존재와 옛 우선순위·제3부
§56 예외 문구의 부재를 계속 검사한다. README의 DEC 안내는 실제 계열
이름을 쓰도록 고쳤고, ADR 목록·DEC 계열을 시험이 대조한다는 문장도
현재 검사 범위와 일치시켰다.

감리 지적 상태를 메모리에서 재현하는
[readme_mutation.py](../../../tools/evidence/audit5-readme-refresh/readme_mutation.py)는
ADR 목록 절단, DEC 계열 안내 삭제, 옛 우선순위 복원, 링크 유지 상태의
옛 문구 재삽입을 각각 의도한 시험 실패로 검출한다. 실제 README 파일은
바꾸지 않는다.

## 검증·범위

| 로컬 실행 | 결과 | 증거 |
|---|---|---|
| 집중 회귀 시험 | README 시험 13건 통과 | [focused.log](../../../tools/evidence/audit5-readme-refresh/focused.log) |
| 변이 검증 | 변이 4종 모두 검출, README 불변 | [mutation.log](../../../tools/evidence/audit5-readme-refresh/mutation.log) |
| 결정 색인 | ADR·DEC 37개 일치 | [status.log](../../../tools/evidence/audit5-readme-refresh/status.log) |
| Python 전체 시험 | 1,468건 통과, 실패·오류 0, 기존 건너뜀 60건 | [python-tests.log](../../../tools/evidence/audit5-readme-refresh/python-tests.log) |
| Rust 전체 시험 | 513건 통과, 실패 0, 기존 무시 1건 | [rust-tests.log](../../../tools/evidence/audit5-readme-refresh/rust-tests.log) |
| 온톨로지 실행기 | 빌드 성공, 시험 4건 통과 | [ontology-build.log](../../../tools/evidence/audit5-readme-refresh/ontology-build.log) · [ontology-tests.log](../../../tools/evidence/audit5-readme-refresh/ontology-tests.log) |
| 허용 경로·보호 문서 | 허용 경로만 변경, 보호 문서 불변, `git diff --check` 통과 | [scope.log](../../../tools/evidence/audit5-readme-refresh/scope.log) |

이번 노드는 README 색인·문서 위계의 회귀 증거만 다룬다. 실제 공시
데이터·트윈 계산·소비자 화면·P01~P19 첫 출시 완료 증거나 T-OP-08 출시
판정을 대신하지 않는다. commit·push·GitHub 호출·비밀값 조회·외부
저장소 접근은 수행하지 않았다.
