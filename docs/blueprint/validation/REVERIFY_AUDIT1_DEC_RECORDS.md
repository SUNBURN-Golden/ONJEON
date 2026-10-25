# Audit 1: DEC 결정 게이트 기록 등록 검증

검증일: 2026-10-26. 대상: `audit1-blueprint-register-dec-records`.
연결: A1·A2·A4, L1·L2, I6·I14·I17, M1~M3의 결정 추적. 제품 목적 대응표 09의 P03(원본 보존·이력), P06(지식 검수)에 필요한 결정 근거를 찾을 수 있게 하는 문서 정합성 수정이다.

## 수정과 상태 해석

- [BLUEPRINT §0.1](../../BLUEPRINT.md#01-문서-위계)에 `DEC-*.md`를 결정 게이트 기록으로 정의하고 결정 원장 §3에 연결했다. 설계도 변경 경로인 ADR과 구분한다.
- [결정 원장 §3.1](../DECISIONS.md#31-결정-게이트-기록-dec-)에 아래 세 기록을 상대 링크·상태·결정 범위·남은 조건과 함께 등록했다.

| 근거 기록 | 원장에 반영한 상태와 경계 |
|---|---|
| [DEC-D-02](../../decisions/DEC-D-02.md) | 위임·가역 결정이며 사용자 확정 아님. 이종 계열 검수 구성과 정책 소유자를 정했으나 비-claude 접근 증거를 담지 않는다. 접근 확인 뒤 등록 또는 별도 실데이터 게이트 추가가 필요하고 T-OP-03 실측 전 접근·월 한도 확인 조건이 남는다 |
| [DEC-D-04](../../decisions/DEC-D-04.md) | 소유자 직접 결정: 대화 노출 토큰을 폐기하지 않는다. O13의 폐기 요구에 대한 최신 결정임을 표시했다. 토큰 재사용·R2 접근 제한 해제의 승인이 아니며 D16~D18·O14·O17과 접근 자격 조건은 유지한다 |
| [DEC-CANON-T-CT-02](../../decisions/DEC-CANON-T-CT-02.md) | 위임에 따른 조건부 정본 변경 승인. 어휘 정본과 생성 문서의 추가 전용 변경으로 한정하며 병합은 미승인이다. 검사·독립 리뷰·사용자 병합 지시와 별도 데몬 등록·봉투 설정 조건을 유지한다 |

문서 색인 등록은 데몬 `decisions_recorded` 등록, 실데이터 접근 허용, 정본 변경 적용, 병합 또는 관문 통과의 증거가 아니다. 원본 DEC 기록과 과제·데몬 설정을 변경하지 않았다. 이 작업에는 새 비용·법률·자격 증명·운영 결정을 내릴 필요가 없다.

09의 P01~P19 출시 완료 증거를 생성하거나 닫은 작업이 아니다. 원본 보존·실제 제공자 검수·화면·출시의 완료는 해당 표의 실제 증거 기준으로 별도 판정한다.

## 회귀 시험

[test_decision_records.py](../../../tools/tests/test_decision_records.py)는 기존 CI의 `tools/tests` 자동 탐색으로 실행된다. BLUEPRINT의 ADR 변경 경로·DEC 정의·원장 연결, 세 기록의 링크·상태·조건, 운영 게이트와 색인 등록의 구분을 검사한다.

문서 수정 전에 6개 시험을 실행해 정의·세 기록 누락으로 실패하는 것을 확인했다(실패 8건: 세 기록 대조의 subTest 실패 포함). 문서 수정 후 6개 모두 통과했다. 결과 로그에는 실행 명령과 종료 코드를 남겼다.

## 최초 수정의 프로젝트 검사

실행 결과는 [evidence/audit1_blueprint_register_dec_records/](evidence/audit1_blueprint_register_dec_records/)에 기록한다.

| 명령 | 결과 | 로그 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p test_decision_records.py -v` | 6개 통과 | [decision-records.log](evidence/audit1_blueprint_register_dec_records/decision-records.log) |
| `python3 -m unittest discover -s tools/tests` | 811개 실행, 실패 0, 건너뜀 6 | [python-tests.log](evidence/audit1_blueprint_register_dec_records/python-tests.log) |
| `python3 tools/vocab_check.py` | 49축·269값 통과 | [vocabulary.log](evidence/audit1_blueprint_register_dec_records/vocabulary.log) |
| `python3 tools/validation_check.py` | 표본 14·조항 142·필드 74·가격 관측 15·화면 모델 2·부족분 26의 내부 일관성 통과 | [validation.log](evidence/audit1_blueprint_register_dec_records/validation.log) |
| `python3 tools/validation_check.py --selftest` | 변조 38종을 의도한 이유로 모두 검출 | [validation-selftest.log](evidence/audit1_blueprint_register_dec_records/validation-selftest.log) |
| `cargo test --all` | 문서 시험 포함 통과 402, 실패 0, 무시 1 | [rust-tests.log](evidence/audit1_blueprint_register_dec_records/rust-tests.log) |
| `cargo fmt --all -- --check` | 통과 | [rust-format.log](evidence/audit1_blueprint_register_dec_records/rust-format.log) |
| `cargo clippy --all-targets -- -D warnings` | 통과 | [rust-clippy.log](evidence/audit1_blueprint_register_dec_records/rust-clippy.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 44/44·존재 검사 72/72 통과 | [design-specs.log](evidence/audit1_blueprint_register_dec_records/design-specs.log) |
| `cargo build --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir target/audit1-ontology` | 통과 | [ontology-build.log](evidence/audit1_blueprint_register_dec_records/ontology-build.log) |
| `python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py target/audit1-ontology/debug/ontology-case-runner` | 질문 11/11·제약 자체 시험 15/15·릴리스 및 문서 모델 시험 25/25 통과 | [ontology-check.log](evidence/audit1_blueprint_register_dec_records/ontology-check.log) |
| README 색인 시험·`git diff --check`·금지 경로 diff·변경/미추적 파일 경로 검사·문서 링크 대상 검사 | 색인 5개 통과, 모든 변경이 허용 범위이며 금지 경로 변경 없음, 링크 대상 존재 | [final-checks.log](evidence/audit1_blueprint_register_dec_records/final-checks.log) |

Python 건너뜀은 비공개 원본 보관본이 필요한 시험 5개와 설치된 botocore가 조건부 쓰기를 지원해 해당하지 않는 구버전 거부 시험 1개다. 기존 CSV 읽기 코드의 `ResourceWarning`이 출력됐으며 실패는 없었다. Rust의 무시 1개는 기존 ABox 픽스처 재생성 시험(`regenerate_declared_abox_fixture`)이다. 이 노드의 회귀 시험에는 건너뜀이 없다.

## Fix round 1: 부분 색인의 범위 명시

리뷰의 차단 지적은 §0.1이 모든 `DEC-*.md`의 원장 등록을 선언하지만 §3.1에는 세 기록만 있다는 점이다. 모든 기록의 상태를 새로 요약하는 대신, §0.1에서 §3.1은 일부 기록을 색인한다고 범위를 좁혔다. §3.1에도 전체 목록이 아님을 명시하고 전체 기록의 위치인 `docs/decisions/DEC-*.md`를 안내했다. 세 기록의 상태·조건과 ADR 변경 경로는 그대로다.

`test_hierarchy_and_ledger_explicitly_describe_a_partial_index`가 두 문서의 부분 색인 명시와 전체 기록 위치 안내를 검사한다. 수정 전 HEAD의 BLUEPRINT와 DECISIONS 본문을 각각 시험 입력으로 복원하고 다른 문서는 수정 상태로 두었을 때, 새 시험은 두 경우 모두 실패했다. 실제 문서를 되돌리지 않고 메모리의 시험 입력만 바꿨다. 수정 후 결정 기록 시험 7개는 모두 통과했다.

재실행 증거는 [round1/](evidence/audit1_blueprint_register_dec_records/round1/)에 별도로 보존한다. 위 최초 수정의 로그와 구분한다.

| 명령·검사 | 결과 | 로그 |
|---|---|---|
| `python3 -m unittest tools.tests.test_decision_records -v` | 7개 통과 | [decision-records.log](evidence/audit1_blueprint_register_dec_records/round1/decision-records.log) |
| `python3 -m unittest discover -s tools/tests -v` | 812개 실행, 실패·오류 0, 건너뜀 6 | [python-checks.log](evidence/audit1_blueprint_register_dec_records/round1/python-checks.log) |
| 새 부분 색인 시험에 수정 전 HEAD 문서를 각각 대입 | BLUEPRINT·DECISIONS의 이전 문구를 각각 검출 | [regression.log](evidence/audit1_blueprint_register_dec_records/round1/regression.log) |
| `cargo fmt --all -- --check` → `cargo clippy --all-targets -- -D warnings` → `cargo test --all` | 모두 통과. Rust 문서 시험 포함 402개 통과, 실패 0, 무시 1 | [rust-checks.log](evidence/audit1_blueprint_register_dec_records/round1/rust-checks.log) |
| `python3 tools/vocab_check.py` → `python3 tools/validation_check.py` → `python3 tools/validation_check.py --selftest` → `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 모두 통과. 어휘 49축·269값, 변조 38종 검출, 명세 기계 검사 44/44·존재 검사 72/72 | [docs-checks.log](evidence/audit1_blueprint_register_dec_records/round1/docs-checks.log) |
| `git diff --check`·변경/미추적 파일 경로 검사 | 통과, 허용 범위 안의 변경이며 금지 경로 변경 없음 | [final-checks.log](evidence/audit1_blueprint_register_dec_records/round1/final-checks.log) |
