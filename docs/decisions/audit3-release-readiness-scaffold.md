# Decision: `docs/release-readiness/evidence/` and `tools/release_readiness/check.py` don't exist. Should they b

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-10-30 11:21 KST); reversible.

**Decision:** 지금 docs/release-readiness/evidence/와 tools/release_readiness/check.py를 만든다. P01–P19별 open/closed/excluded와 미완료 사유·집계를 보고하고, 증거나 작업 상태가 없으면 open으로 처리한다. 기반 구현을 T-OP-08 완료나 출시 승인으로 간주하지 않는다.

**Why:** BLUEPRINT §9.5, 09 §6, tasks.json의 T-OP-08이 이미 해당 경로와 검사 계약을 요구한다. 읽기 전용 검증에서 두 경로 부재, P01–P19의 정확한 19개 행, 필수 시험 2개 등록을 확인했다. 기존 정적 검사도 종료 코드 0으로 통과했지만 제품 완료를 검증하지 않는다. tasks.json에는 실행 상태 필드가 없고 evidence는 요구사항 설명이므로, 실제 post_merge 상태와 실행 증거를 별도로 연결해야 한다. 수락 시험은 빈 증거에서 19개 미완료 보고, 증거·실행 로그 삭제 또는 작업 미완료 시 해당 행과 종료 코드 1, 근거 없는 제외 거부를 포함해야 한다. 이번 응답은 결정이며 읽기 전용 환경에서 파일 생성·신규 검사기 시험은 수행하지 않았다. 구현 지적은 아직 미해결이다.

**Options:** ['지금 증거 등록 구조와 미완료를 거부하는 검사기를 구현한다 — 채택', 'T-OP-08 최종 감리까지 미룬다 — 진행 상황의 증거 공백이 지속됨', '기존 check_product_purpose.py로 대체한다 — 작업 연결·시험 ID 등록만 검사하므로 불충분']

**Revisit if:** 정본의 완료 범위·증거 기준이 변경되거나 실행 상태·증거 저장 계약이 확정되면 입력 구조를 조정한다. 부분 축소나 결정 대기 문구만으로 행 전체를 제외하지 않는다.
