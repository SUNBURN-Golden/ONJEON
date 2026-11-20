# Audit 8 S1 선행 조건 검증

기준 커밋 `92eada7`의 작업 계약에서 T-OP-02의 직접 선행은 T-MB-02·T-KN-07이었다. 부트스트랩 도구의 `keep_set`으로 전이적 선행을 계산했을 때 T-DT-01·T-DT-02·T-KN-03·T-KN-05·T-KN-06이 모두 빠져 있었다. 변경 뒤 같은 계산에서 누락은 0개다.

- T-OP-10은 모의 관통 검증이다. 기존 작업 ID 형식에 맞춰 새 번호를 썼고, T-KN-06의 모의 구현이 병합된 뒤 시작할 수 있다. D-02 등록 없이 모의 경로를 병합할 수 있다.
- T-OP-02는 실제 관문 ID를 유지한다. T-KN-06의 선행을 통해 T-KN-05·T-KN-03·T-DT-02·T-DT-01이 연결된다. 실제 관문은 T-OP-10 병합, D-02 등록, 실제 상품의 R2 원본·이종 계열 검수·화면 근거 사슬의 감리를 요구한다.
- 회귀 시험에서 모의 관문의 병합과 D-02 등록 뒤에도 T-DT-03·T-KN-08·T-PS-01은 실제 관문 병합을 기다렸다. 실제 관문을 병합한 뒤 T-DT-03이 대기열에 들어갔고, T-DT-03 완료 뒤 나머지 두 작업이 대기열에 들어갔다. [회귀 시험](../../tests/test_s1_prerequisites.py)

이 검증에서 사용한 선행 상태·결정 등록·감리·병합 관측은 합성이다. `tools/gate/s1_mock.sh`와 `tools/gate/s1.sh`는 각각 해당 관문 작업의 산출물이다. 실제 관통 실행과 증거 감리는 T-OP-02에서 수행한다. 09 출시 판정은 P01~P19 모두 `open`이며 완료 0건이다. [작업 계약](../../../docs/blueprint/proposals/설계검토_결과/tasks.json) · [09 제품목적 대응표](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md)

## 실행 결과

| 명령 | 결과 |
|---|---|
| `python3 -m unittest tools.tests.test_s1_prerequisites -v` | 3개 통과. [실행 로그](regression.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,770개 중 1,764개 통과. 실제 원본 보관 자료가 필요한 5개와 구형 botocore 전용 1개 건너뜀 |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과 |
| `cargo test --all --locked --offline` | 537개 통과, 픽스처 재생성 시험 1개 건너뜀 |
| `cargo test --manifest-path services/scenario-api/Cargo.toml --locked --offline --target-dir target/scenario-api` | 4개 통과 |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4개 통과 |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 47/47, 존재 검사 72/72 통과 |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업·수락 시험 연결 검사 통과 |
| `python3 -I tools/ci/check_bootstrap.py` | 통과, 기준 커밋과 같은 경로 안내 6건 |
| 데몬 모의 실행 `--scenario all --require-all --quiet` | 695개 검사 통과 |
| 출시 판정기 `--purpose` | 예상대로 종료 코드 1, P행 19개와 기능 64개가 미완료 |
