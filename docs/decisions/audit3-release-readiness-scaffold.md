# Decision: release-readiness evidence scaffold

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-10-30 11:21 KST); reversible.

**Decision:** 지금 docs/release-readiness/evidence/와 tools/release_readiness/check.py를 만든다. P01–P19별 open/closed/excluded와 미완료 사유·집계를 보고하고, 증거나 작업 상태가 없으면 open으로 처리한다. 기반 구현을 T-OP-08 완료나 출시 승인으로 간주하지 않는다.

**Why:** BLUEPRINT §9.5, 09 §6, tasks.json의 T-OP-08이 이미 해당 경로와 검사 계약을 요구한다. 기존 정적 검사는 작업 연결·시험 등록을 확인하지만 제품 완료를 검증하지 않는다. tasks.json에는 실행 상태 필드가 없고 evidence는 요구사항 설명이므로, 관측한 post_merge 상태와 실행 증거를 별도로 연결한다.

**Fix round 1:** [검사기와 입력 계약](../../tools/release_readiness/README.md), [수락 시험](../../tools/tests/test_release_readiness.py)을 구현했다. 두 명세 명령은 이제 실행되며 P01–P19 **open=19, closed=0, excluded=0**, feature_registry **open=64, closed=0, excluded=0**, 종료 코드 **1**을 보고한다. 빈 증거·누락 로그·미완료 과제·근거 없는 제외를 거부하는 시험과 실행 로그는 [검증 기록](../../tools/evidence/audit3-release-readiness-scaffold/README.md)에 있다. T-OP-08의 다섯 축 감리·출시 승인을 완료했다는 뜻은 아니다.

**Fix round 2:** 체크포인트 재시도 시험이 주입한 쓰기 실패에 도달하기 전에 실제 실행 시간 131초로 admission 제한 120초에 걸린 실패를 수정했다. 해당 시험에서만 `r2_budget`의 단조 시계를 고정하며 실제 HTTP 요청·계량·실패 후 복구 검증은 유지한다. 별도 회귀 시험은 120초 경계 허용과 121초에서 요청 전 거부·잠금 해제를 검증한다. 운영 코드와 비용·시간 제한은 변경하지 않았다. 재실행 결과는 [2차 검증 기록](../../tools/evidence/audit3-release-readiness-scaffold/fix-round2/README.md)에 기록한다.

**남은 경로 제약:** 이 노드의 사용자 허용 목록에는 `tools/**`가 있으나 `docs/release-readiness/**`가 없다. 해당 디렉터리의 생성은 경로 예외 답변을 기다린다. 빈 manifest와 안내 문서를 추가하는 [검토 가능한 패치](../../tools/evidence/audit3-release-readiness-scaffold/evidence-scaffold.patch)를 준비했고 적용 가능 여부만 검사했다. 따라서 검사기 부재는 해결했으나 요구된 두 경로의 생성이라는 전체 지적은 아직 완전히 해결되지 않았다. 권한 답변 없이 패치를 적용하거나 수락 완료를 주장하지 않는다.

**Options:** ['지금 증거 등록 구조와 미완료를 거부하는 검사기를 구현한다 — 채택', 'T-OP-08 최종 감리까지 미룬다 — 진행 상황의 증거 공백이 지속됨', '기존 check_product_purpose.py로 대체한다 — 작업 연결·시험 ID 등록만 검사하므로 불충분']

**Revisit if:** 정본의 완료 범위·증거 기준이 변경되거나 실행 상태·증거 저장 계약이 확정되면 입력 구조를 조정한다. 부분 축소나 결정 대기 문구만으로 행 전체를 제외하지 않는다.
