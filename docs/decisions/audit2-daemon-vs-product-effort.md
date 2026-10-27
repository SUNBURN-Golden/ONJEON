# Decision: freeze daemon expansion and prioritize V1 and M1

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-10-27 21:28 KST); reversible.

**Decision:** 데몬 신규 기능·리팩터링을 동결하고, 감사에서 지적된 버그 수정과 회귀검증만 허용한다. 개발 우선순위는 V1 미통과 조건 해소 → M1 잔여 검증·정합성 보완 → M2의 L1~L9 연결로 전환한다. 이미 존재하는 어휘 생성기·DB 스키마·앱 골격은 재사용한다.

**Why:** HEAD dc0fc10에서 감사 전제 일부는 오래됐다. packages/schemas에 Rust·Dart·TS 생성물, infra/db에 공개·개인 스키마, services/docproc에 복원 코드, apps/mobile에 Flutter 골격이 있다. 생성물·시험·픽스처·증거를 제외한 지정 소스 확장자의 물리 행 수는 tools/daemon 12,238행, packages/services/apps 18,188행으로, 이 집계에서는 3.5배가 재현되지 않는다. 코드량 자체도 투입 노력의 증거는 아니다. 그러나 BLUEPRINT §9의 V1은 미통과이고 서비스 API·실데이터·화면을 잇는 제품 경로는 미완료다. 09 §0·§5는 데몬을 출시 완성품에서 제외한다. 이번 검증에서 생성물 30개 최신성, SQL 어휘 20축 일치, 데몬의 제품 선행조건 방지 시험 6개, 계층 상태 시험 5개가 통과했다. 제품 목적 검사도 통과했지만 이는 등록 정합성 검사일 뿐 완료 증거가 아니다. DB 제약 166개 통과는 저장된 과거 로그이며 이번에 재실행하지 않았다. V1의 파생 6건 재현·다른 계열 AI 검수·S1/S6를 먼저 닫고, M1에서는 I7의 저장 요건과 일부 누락 가격을 허용하는 SQL의 차이를 정본에 맞춰 해소하며 I12 저장·권한 분리를 검증해야 한다. 이 결정은 가역적인 개발 우선순위 판단이며, 동결 정책의 저장소 반영이나 제품 완료를 주장하지 않는다.

**Options:** ['데몬 확장을 계속한다: 제품 완료 관문을 직접 해소하지 못하므로 기각.', '데몬을 삭제하거나 버그 수정까지 중단한다: 기존 작업 실행의 안정성을 해치므로 기각.', '데몬은 버그 수정으로 제한하고 제품 관문에 집중한다: 채택.']

**Revisit if:** 데몬 결함이 제품 작업의 손실·중복 실행·관문 우회를 실제로 유발하면 해당 결함의 최소 수정 범위를 재검토한다. 신규 데몬 기능은 특정 제품 관문을 막는다는 재현 증거와 직접 해결하는 것보다 유리하다는 근거가 있을 때만 재검토한다. 첫 출시 완료 판정은 계속 09의 P01~P19 실제 완료 증거와 T-OP-08을 따른다.

**Fix round 1 evidence:** 로컬 시험의 18개 오류는 `CARGO_TARGET_DIR`가 지정된 환경에서 Cargo 빌드가 성공해도 Python 시험이 `runner/target/debug/ontology-case-runner`를 고정 경로로 실행한 데서 발생했다. `tools/tests/test_ontology_runner_io_error.py`는 이제 Cargo의 `compiler-artifact.executable`을 사용한다. 기본·변경된 출력 경로, 별도 target 경로, 실행 파일 보고 누락, 빌드 실패, 미리 빌드한 실행 파일 지정에 대한 회귀 시험을 포함한다. 제품 개발 우선순위 결정은 유지하며, 이 변경은 검증 도구의 버그 수정이다. [재현 명령·재실행 결과와 한계](../../tools/evidence/audit2-daemon-vs-product-effort/fix-round1/README.md)를 참조한다. 시험 통과는 V1·M1 관문 통과나 제품 출시 완료를 뜻하지 않는다.

**Fix round 2 evidence:** 900초 제한 초과 보고 뒤 느린 데몬 시험을 분리 실행하고 Cargo 빌드 잠금으로 무한 대기할 수 있는 시험 준비 경로를 재현했다. fallback 빌드는 이제 120초 안에 끝나지 않으면 Cargo 진단을 보존한 오류로 실패한다. 실제 잠금 회귀 시험을 포함해 Python 1,161개(6개 건너뜀), Rust workspace 및 설계 검사를 재실행했다. 원래 시간 초과의 정확한 원인은 제공된 발췌만으로 확정하지 않는다. [명령별 시간·결과·한계](../../tools/evidence/audit2-daemon-vs-product-effort/fix-round2/README.md)를 참조한다. 데몬 확장 동결과 V1 → M1 우선순위, 미완료 제품 관문은 그대로다.
