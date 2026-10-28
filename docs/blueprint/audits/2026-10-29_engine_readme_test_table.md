# Audit 3: 엔진 시험 표와 fixture_only 정의 정합성

기록일: 2026-10-29. 노드: `audit3-engine-readme-test-table`.
연결: BLUEPRINT A1·A2·A5, Q7, L6, I6, M1 기반, [09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md) P08·P14.

## 발견과 수정

작업 시작 시 엔진 README에는 이미 `real_clauses`·`vocabulary` 행과 `tests/*.rs`를 양방향 대조하는 시험이 있었다([Audit 2 증거](2026-10-27_readme_adr_list.md)). 두 행을 각각 삭제하거나 이름을 바꿨을 때 누락·낡은 이름을 검출하는 음성 대조를 보강하고, 각 행에 현재 검증 범위를 반영했다.

남아 있던 불일치는 어휘 정본의 `publication_state` 축 설명과 `fixture_only` 정의, README의 “모두 합성 규칙” 문구였다. 실제 조항 규칙 7개도 `fixture_only`이므로 이 상태는 원문 출처가 아니라 **시험·설계 검증 전용이며 서비스 데이터가 아님**을 나타낸다고 정정했다. 합성 규칙과 실제 조항 기반 검증 규칙을 모두 포함한다. 근거·릴리스 없이 로드할 수 있다는 기존 조건은 유지한다.

`vocabulary.json`을 수정한 뒤 `tools/vocab_check.py --write`와 `packages/schemas/codegen/gen.py --write`로 문서·JSON Schema·Rust·TypeScript·Dart 생성물을 갱신했다. 기존 동작을 설명하는 문구 정정으로 어휘 버전 1.8.0은 유지하고 갱신일을 변경했다. 저장 코드·화면 문구·로더·계산·공유 픽스처·고정 해시는 변경하지 않았다. 새 회귀 시험 2개에 맞춰 BLUEPRINT §11 등록 수를 생성기로 207 → 209로 갱신했다.

## 회귀 검증

- `readme_test_table`: 표와 모든 통합 시험 파일의 일치, 두 감사 대상 행의 삭제·개명 검출, README의 시험 전용 범위 설명과 잘못된 합성 전용 문구의 부재를 검사한다.
- `vocabulary`: 정본 정의에 합성·실제 조항 기반 검증과 서비스 데이터 제외가 명시되는지 검사한다. 합성 규칙 1개와 실제 조항 규칙 7개를 실제 로드해 모두 `fixture_only`인지 대조한다.
- 기존 `real_clauses`: 105개 사례와 규칙별 사례 보유, 실제 조항 검증 표식·시험 전용 상태 검사를 다시 실행한다.

직접 실행한 명령·종료 코드·출력은 [증거 디렉터리](../../../packages/rules-engine/evidence/audit3-engine-readme-test-table/)에 보관한다. `before.log`는 새 두 시험이 수정 전 README·어휘에서 각각 실패한 기록이다. 첫 명령은 README 시험 실패 시 멈추므로 어휘 시험을 별도 명령으로 실행했다.

| 명령 | 결과·로그 |
|---|---|
| `cargo test -p onjeon-rules-engine --offline --test readme_test_table --test vocabulary`, `cargo test -p onjeon-rules-engine --offline --test vocabulary fixture_only_definition` (문서 수정 전) | 각각 종료 코드 101. README 설명 누락과 기존 어휘 정의를 검출: [before.log](../../../packages/rules-engine/evidence/audit3-engine-readme-test-table/before.log) |
| `cargo test -p onjeon-rules-engine --locked --offline --test readme_test_table --test vocabulary --test real_clauses` | 종료 코드 0, 25개 통과: [focused.log](../../../packages/rules-engine/evidence/audit3-engine-readme-test-table/focused.log) |
| `cargo test --all --locked --offline` | 종료 코드 0, Rust 단위·통합·문서 시험 474개 통과·실패 0·기존 ignored 1개. 내부 Python 시험 39개·129개 통과: [workspace.log](../../../packages/rules-engine/evidence/audit3-engine-readme-test-table/workspace.log) |
| `ONJEON_ONTOLOGY_RUNNER=<target>/debug/ontology-case-runner python3 -I -m unittest discover -s tools/tests -v` | 종료 코드 0, 1,277개 실행·실패 0·환경 의존 skip 36개: [python-tests.log](../../../packages/rules-engine/evidence/audit3-engine-readme-test-table/python-tests.log) |
| `cargo fmt --all -- --check`, `cargo clippy --all-targets --locked --offline -- -D warnings` | 모두 종료 코드 0: [fmt.log](../../../packages/rules-engine/evidence/audit3-engine-readme-test-table/fmt.log)·[clippy.log](../../../packages/rules-engine/evidence/audit3-engine-readme-test-table/clippy.log) |
| 어휘·생성물 최신성·BLUEPRINT 수치/결정 색인·제품 목적·명세·검증 자료 검사, `git diff --check` | 모두 종료 코드 0. 어휘 검사 Python 시험 27개, 검증 자료 변조 시험 38개 통과. 명세 기계 검사 45/45·존재 검사 72/72: [consistency.log](../../../packages/rules-engine/evidence/audit3-engine-readme-test-table/consistency.log) |

Python 건너뜀은 boto3/botocore 미설치·구버전 31개, `ONJEON_ARCHIVE_RAW` 미설정 2개, 로컬 원본 보관소·pdftotext 필요 3개다. TypeScript·Dart는 생성물 최신성만 검사했고 별도 언어 빌드는 실행하지 않았다.

## 제품 목적과 한계

시험 규칙을 서비스용 실제 상품 규칙으로 오인하지 않도록 문서·어휘·실제 픽스처의 범위를 맞춘 정정이다. P08·P14의 엔진 기반 검증 증거이며 실제 릴리스 상품·전 상품 수집·소비자 화면·첫 출시 완료 증거를 대체하지 않는다.
