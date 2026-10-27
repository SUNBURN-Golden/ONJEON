# Audit 2: 열린 결정과 최신 결정 기록의 불일치 정정

검증일: 2026-10-27. 노드: `audit2-blueprint-open-decisions-stale`.
연결: A1·A2, Q7, L0·L1·L4·L9, I6·I14, M2·M3. [09 제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P01·P03·P14·P18을 위한 결정·관문 문서 정합성 증거다.

## 수정과 유지 범위

- [BLUEPRINT §12·§13](../../BLUEPRINT.md)와 [결정 원장 §3](../DECISIONS.md)을 현재 기록과 대조했다. 감사가 지목한 줄 번호 대신 절·항목 ID로 추적한다.
- [DEC-D-02](../../decisions/DEC-D-02.md)의 위임 결정 내용을 §12와 원장 §3.1에 구체화했다. 공개 약관·공시 지식 검수의 작성=claude, 승인=비-claude X, 레드팀=별도 비-claude Y, 하한 2계열과 Y 미확보 시 degraded 기록을 반영했다. 업체·모델 ID는 아직 고정하지 않는다. 정책 소유자는 사용자 본인 1인이며 중단은 자동·누구나 가능하고 재개는 소유자만 한다. 임계값 수치는 O06·D-19로 남긴다. 위임 결정을 사용자 확정으로 승격하지 않았으며 비-claude 접근·월 한도 확인, 게이트 등록 조건과 T-OP-03 발송 제한을 유지했다. 모의 개발·시험·병합은 계속 가능하다.
- O01은 [ADR-0018](../../decisions/ADR-0018-보험-데이터-지식-기반의-정체성과-범위.md)의 2026-10-10 사용자 결정으로 해결됐다고 기록했다. 우체국보험 포함(보험사와 기관 유형 구분), 공제 제외(확보율 분모에서도 제외)다. O01 ID는 유지하며 전체 목록·분모 구현 완료와 구분했다.
- [DEC-D-04](../../decisions/DEC-D-04.md)의 R2 토큰 미폐기 결정은 작업 시작 시 이미 §12·O13에 반영돼 있었다. 해당 행을 유지하고 기존 `test_o13_ruling.py`로 재검증했다. 토큰 재사용·출력 금지, 실제 R2 접근 차단, D-04·O14·O17의 별도 관문은 그대로다.
- [DEC-D-12](../../decisions/DEC-D-12.md)의 2026-10-14 소유자 결정(선택 C)을 §12·O16·§3.1에 반영했다. 소비자 앱의 원문 이미지·발췌 표시는 허용됐고 기존 발췌·Git 이력은 유지한다. 외부 검토 없이 법적 위험을 감수한다는 소유자 결정의 범위를 그대로 기록했다. 공개 저장소에 새 발췌를 추가하는 승인으로 확대하지 않았으며, 표시 플래그의 실제 적용·게이트 등록은 별도다.
- §13의 `O01~O12` 고정 범위를 원장 §3의 전체 O 항목 참조로 교체했다. 현재 원장은 O19까지이며 이후 항목 추가에도 같은 참조가 적용된다.

결정 원문·`tasks.json`·실행 상태·플래그는 변경하지 않았다. R2·외부 AI에 접속하지 않았고 토큰·키를 사용하거나 출력하지 않았다. 이 정정은 새 비용·법률·운영 결정을 내리는 작업이 아니다. P01~P19 및 T-OP-08의 실제 데이터·트윈·소비자 화면·출시 완료 증거를 대체하지 않는다.

## 회귀 검사와 실행 증거

[test_decision_records.py](../../../tools/tests/test_decision_records.py)에 AI 구성·정책 소유자·O01 해결·D-12 범위·전체 O 항목 참조 검사 5개를 추가하고 DEC-D-12의 색인·링크 검사도 확장했다. 문서 수정 전 새 검사와 색인 검사가 실패한 [수정 전 로그](../../../tools/evidence/audit2-blueprint-open-decisions-stale/decisions-before.log)와 13개 모두 통과한 [수정 후 로그](../../../tools/evidence/audit2-blueprint-open-decisions-stale/decisions-after.log)를 남겼다. 기존 Python CI의 `tools/tests` 자동 발견으로 실행된다.

전체 실행 로그는 [tools/evidence/audit2-blueprint-open-decisions-stale/](../../../tools/evidence/audit2-blueprint-open-decisions-stale/)에 있다. 아래 결과는 로컬 시험이며 실데이터 접근 승인·실제 표시 플래그 활성화 증거가 아니다.

| 명령 | 결과 |
|---|---|
| `python3 -I -m unittest discover -s tools/tests -p test_decision_records.py -v` | 13개 통과 |
| `env -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -v` | 1,130개 실행, 통과 1,124·건너뜀 6·실패/오류 0. 기존 R2 결정·모의 관문 검사 포함 |
| `cargo test --all` | Rust 447개 통과, 실패 0, 무시 1(문서 시험 포함) |
| `python3 tools/vocab_check.py` | 통과 |
| `python3 tools/validation_check.py` / `--selftest` | 표본 내부 일관성 통과·변조 38종 검출 |
| `python3 -I tools/blueprint_status.py` / `tools/blueprint_counts.py` | 결정 색인·내용 해시 및 등록 수 일치 |
| `cargo fmt --all -- --check` / `cargo clippy --all-targets -- -D warnings` | 통과 |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 44/44·존재 72/72 통과 |
| `cargo build --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir target/audit2-ontology` 후 `python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py target/audit2-ontology/debug/ontology-case-runner` | 질문 11/11·제약 자체 시험 15/15·릴리스/문서 모델 25/25 통과 |

추가 CI 검사 `env -u CARGO_TARGET_DIR python3 -I -m unittest discover -s tools/ci/tests -v`는 20개 중 기존 의존성 위반으로 2개 실패했다([현재 로그](../../../tools/evidence/audit2-blueprint-open-decisions-stale/ci-tests.log)). `git archive HEAD`를 이 작업트리의 무시되는 `target/audit2-open-decisions-baseline/`에 풀어 같은 검사를 실행했고 같은 두 시험·세 위반이 재현됐다([HEAD 로그](../../../tools/evidence/audit2-blueprint-open-decisions-stale/baseline-ci-tests.log)). 위반은 `packages/ontology/Cargo.toml`의 knowledge→twin 의존성과 `packages/ontology/tests/common/mod.rs`·`fixture_origin/main.rs`의 해당 import다. 이 노드에서 해당 파일이나 의존성 정책을 바꾸지 않았다.
