# Audit 1: 내 설계 보조문 충돌 해소

기록일: 2026-10-26. 노드: `audit1-screen-spec-helper-text`.

적용 문구: **예산 안에서 보장과 조건을 비교하세요**.
근거는 [CONSUMER_FLOW_SPEC §2](../../design/CONSUMER_FLOW_SPEC.md#2-내-설계-화면-위에서-아래로)와 BLUEPRINT §10 규칙 5(부록은 상위 명세를 따름)다. 새 제품 결정이 아니라 기존 명세의 적용이다.

[BLUEPRINT §3](../../BLUEPRINT.md#3-소비자-질문-화면-데이터)에 확정 문구를 적고 부록 `화면_조작_설계서.md` §10 보조문 행(감사 시 385행)과 §13 보조문 열린 항목을 명시적으로 대체했다. §12 미정 목록에서도 보조문만 제거했다. [결정 원장 §2](../DECISIONS.md#2-충돌-해소표)에 해결을 기록하고, [화면 연결 예시](../validation/SCREEN_BINDING.md#1-내-설계-탭-보완안-선택)의 제목 아래 문구도 맞췄다. 색 토큰·C2~C4·C7 등 다른 시안 검토 항목은 남아 있다.

이번 노드의 허용 경로에 `docs/design/화면_조작_설계서.md`가 포함되지 않아 부록 원문은 수정하지 않았다. 원문의 구 문구와 P0 대기 표기는 이 정정으로 대체되며 구현 기준이 아니다. 보호된 CONSUMER_FLOW_SPEC 원문도 그대로다.

## 검증

[회귀 시험](../../../tools/tests/test_screen_spec_helper_text.py)은 상위 명세에서 보조문을 읽어 BLUEPRINT의 적용 문구와 화면 예시를 대조하고, 부록 두 항목의 대체 명시·열린 결정 제거·결정 원장의 해결 기록을 검사한다. 기존 CI의 `tools/tests` 탐색에 자동 포함된다.

| 명령 | 실행 결과·증거 |
|---|---|
| `python3 -m unittest discover -s tools/tests -p test_screen_spec_helper_text.py -v` | 수정 전 4개 실패([before.log](../../../tools/evidence/audit1-screen-spec-helper-text/before.log)), 수정 후 4개 통과([focused.log](../../../tools/evidence/audit1-screen-spec-helper-text/focused.log)) |
| `python3 -m unittest discover -s tools/tests -v` | 830개 실행·실패 0·skip 6([python-tests.log](../../../tools/evidence/audit1-screen-spec-helper-text/python-tests.log)) |
| `python3 tools/vocab_check.py` | 통과: 49축·269값 |
| `python3 tools/validation_check.py` / `--selftest` | 내부 정합성 및 변조 시험 38종 통과. 원본 재검증 아님 |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 44/44·존재 검사 72/72 통과 |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업 연결·필수 시험 ID 9개 등록 정합성 통과(정적 검사) |
| `cargo test --all --offline` | 402개 통과·실패 0·ignored 1([rust-tests.log](../../../tools/evidence/audit1-screen-spec-helper-text/rust-tests.log)) |

문서 검사 실행 명령과 종료 코드는 [doc-checks.log](../../../tools/evidence/audit1-screen-spec-helper-text/doc-checks.log)에 있다. 전체 Python 시험의 skip 6개는 로컬 원본 부재 5개와 설치된 botocore가 조건부 쓰기를 지원해 적용되지 않는 구버전 거부 시험 1개다. 새 회귀 시험은 skip하지 않았다. 모두 로컬 실행 결과이며 원격 CI 실행을 주장하지 않는다.

[경로 검사](../../../tools/evidence/audit1-screen-spec-helper-text/scope-check.log)로 변경 경로가 허용 목록 안에 있고 보호 파일과 `docs/design/` 전체가 HEAD와 동일함을 확인했다. `git diff --check`도 통과했다. commit·push·GitHub 호출은 수행하지 않았다.

## 증명 범위

이 기록은 감사 지적의 문서 정합성을 검증한다. [09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P15·P19(화면의 정보 우선순위·일관성)와 연결되지만, 실제 화면 캡처나 참가자 이해 시험을 대체하지 않는다. 해당 제품 목적 행의 완료, 앱 구현 완료, 출시 준비 완료를 주장하지 않는다.
