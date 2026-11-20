# Audit 7 설계도 현황·결정·README 대조

2026-11-20 UTC · `audit7-blueprint-drift-refresh` · 기준 `afbb708e1c94273d8fce4142a13cf8bdded48680`

| 점검 | 근거와 조치 |
|---|---|
| BLUEPRINT §6·§11 등록 수 | 시작본의 생성 표는 실제 목록과 일치했다. Cargo 목록에서 엔진 단위·통합 시험 270개와 doctest 3개, `packages/fixtures/rules/real/`에서 `fixture_only` 규칙 7건, 검증기의 `mutations()`에서 40종, `vocabulary.json`의 `axes`에서 50개를 확인했다. 42건은 2026-10-09 당시의 실행 기록이다. [당시 재실행](../validation/REVERIFY_87a19c5.md#2-실제-실행-범위) · [현재 표](../../BLUEPRINT.md#11-현재-위치) |
| 엔진 버전 | §11 생성 표에 평가 결과와 릴리스 매니페스트가 쓰는 `ENGINE_VERSION`을 추가했다. 현재 `0.2.0+snapshot-json-1`이며 Cargo 패키지 버전 및 규칙 DSL 판과 별도로 관리한다. §9.2의 M0에서 현재 식별자를 §11로 안내한다. [엔진 골든 시험](../../../packages/rules-engine/tests/snapshot_hash.rs) |
| BLUEPRINT §12 | D-02·03·06·12·14·17·18과 O14·O17을 원문과 대조했다. 새 절 제목은 기록된 결정도 포함한다. §12.1은 앱의 원문 표시 허용(D-12)과 공개 저장소의 새 발췌 조건(O16), 외부 검토 담당 지정 요건(D-18)과 담당 미지정을 각각 명시한다. O03의 담당·관문 기록과 내용 미정은 §12.2에서 확인할 수 있다. [§12](../../BLUEPRINT.md#12-결정-상태와-남은-조건) · [결정 원장](../DECISIONS.md#3-결정-상태와-남은-차단-조건) |
| README | 시작본에 ADR 0001~0021과 §0.1 링크가 있었다. 소개에서 충돌 시 설계도가 항상 앞서는 것으로 읽힐 수 있는 문구를 걷어내고, README와 원장 §2의 위계 근거를 §0.1로 연결했다. README ADR·DEC 행에서 원문 색인으로 이동할 수 있다. [README](../../../README.md) · [§0.1](../../BLUEPRINT.md#01-문서-위계) |

생성 검사에서 시작본의 빌드 행 누락을 확인했다. 실제 Cargo·정본에서 읽은 값으로 문서 변이를 검사했다. 엔진 시험 `42`·`122`, doctest `42`, 규칙 `8`, 변조 `28`·`38`, 축 `31`·`33`, 빌드 `v0.1`을 모두 거부했다. D-02의 두 행을 포함해 지적된 DEC 9건의 10개 행을 하나씩 §12.2로 옮기는 변이도 모두 검출했다. README 회귀 시험은 ADR 0011에서 목록을 자르거나 옛 위계 및 무조건적 설계도 우선 문구를 되살리는 변이를 검출한다. [인벤토리 시험](../../../tools/tests/test_blueprint_counts.py) · [결정 회귀 시험](../../../tools/tests/test_blueprint_s12_sync_decisions.py) · [README 회귀 시험](../../../tools/tests/test_readme_index.py)

## 로컬 실행 결과

[검증 로그](../../../tools/evidence/audit7-blueprint-drift-refresh/verification.log)에 생성 검사, 변이 대조, 집중 시험과 출시 판정 출력을 기록했다.

| 명령 | 결과 |
|---|---|
| `python3 -I tools/blueprint_counts.py`, `python3 -I tools/blueprint_status.py` | 현재 값 6개와 ADR·DEC 43개 대조 통과 |
| `python3 -I tools/vocab_check.py`, `python3 -I tools/validation_check.py`, `python3 -I tools/validation_check.py --selftest` | 어휘 축 50개, 표본 14건 내부 일관성 통과, 변조 40종을 모두 지정한 이유로 검출 |
| BLUEPRINT·결정 기록·README 집중 회귀 시험 | 164건 통과, 건너뜀 없음 |
| `python3 -m unittest discover -s tools/tests -v` | 1,748건 중 1,742건 통과, 기존 건너뜀 6건 |
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 537건 통과(문서 시험 3건 포함), 실패 0, 기존 픽스처 재생성 시험 1건 ignored |
| `cargo fmt --all -- --check`, `cargo clippy --locked --offline --all-targets -- -D warnings` | 통과 |
| `cargo test --manifest-path services/scenario-api/Cargo.toml --locked --offline`, `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 각각 4건 통과 |
| `python3 -I -m unittest discover -s packages/schemas/codegen/tests -v` | 138건 중 136건 통과, TypeScript·Dart 도구가 필요한 호환성 시험 2건 건너뜀 |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py`, `python3 -I tools/ci/check_product_purpose.py` | 기계 검사 47건과 존재 검사 72건 통과, P01~P19 작업·시험 ID 연결 정합 |
| `python3 -I tools/release_readiness/check.py` | 종료 1(미완료). P행 19개 및 기능 64개 열림, 닫힘·제외 각 0 |

Rust `1.98.1`, Python `3.13.5`로 이 작업 트리의 별도 Cargo 타깃에서 실행했다. Python 시험에는 같은 작업 트리에서 빌드한 `ONJEON_ONTOLOGY_RUNNER`를 사용했다. 전체 시험에서 기존 D-12 행과 위임 상태 문구를 검사하는 두 곳의 실패를 확인하고, 행 참조를 갱신하고 위임 상태 문구를 복원한 뒤 재실행했다. 건너뜀 6건은 보관 원본 미설정 2건, 로컬 보관본·`pdftotext`가 필요한 시험 3건, 설치된 botocore가 조건부 쓰기를 지원해 해당하지 않는 구버전 시험 1건이다.

Audit 7의 수락 증거는 문서 정합성과 회귀 검증 범위다. 실제 수집·트윈·화면·출시 완료 판정에는 09의 증거를 적용한다. [09_제품목적_대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)
