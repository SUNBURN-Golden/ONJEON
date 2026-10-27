# Audit 2: BLUEPRINT §11 수치와 구현 목록 대조

검증일: 2026-10-27. 대상: `audit2-blueprint-11-counts`.

BLUEPRINT A1·A2·A5, Q1·Q2·Q5·Q7, L6, I5와 단일 기준의 현황 추적에
연결되는 감리 후속이다. §11의 실제 조항 규칙 8건 표기를 제거하고 현재
규칙·시험·어휘 정본에서 자동 생성한 등록 수 표를 추가했다. I5와 코드 목록에는
#40 로드 단계 타입 검사를, 수집·검증 목록에는 R2 보존·재현·비용 통제 도구와
인프라 초안의 범위를 명시했다. §11 기준일·결정 색인 날짜도 갱신했다.

감리 발견 당시의 실제 수 60개·33축을 현재 값으로 고정하지 않았다.
선행 변경이 반영된 이 작업 트리에서 직접 센 값은 다음과 같다.

| 대상 | 현재 등록 수 | 계산 근거 |
|---|---:|---|
| 엔진 단위·통합 시험 | 182 | `cargo test -p onjeon-rules-engine -- --list`의 `Running` 구간 합계 |
| 엔진 doctest | 3 | 같은 명령의 `Doc-tests` 구간 |
| 실제 조항 규칙 | 7 | `packages/fixtures/rules/real/*.json`, `*.cases.json` 제외, 고유 rule_id·fixture_only 확인 |
| 변조 시험 | 38 | `tools/validation_check.py`의 `mutations()` |
| 어휘 축 | 49 | `packages/schemas/vocabulary.json`의 `axes` |

등록 수에는 무시된 시험도 포함할 수 있다. 통과 수·실제 상품 정확도·출시 완료를
뜻하지 않는다. BLUEPRINT의 2026-10-09 **39 + doctest 3 = 42건**은
기존 재실행 증거로 검증되는 역사적 수치이므로 날짜·근거와 함께 유지했다.
§6은 선행 Audit 1에서 수치를 직접 적는 대신 정본 생성 문서를 참조하도록
이미 수정되어 있었다. 현재 축 수는 생성 문서와 새 §11 표가 함께 대조한다.

`tools/blueprint_counts.py`는 수치를 코드·정본에서 계산해 §11의 마커 안 표와
비교한다. 기본 실행은 읽기 전용이고 불일치는 종료 코드 1이다. Cargo 실행 실패,
잘린 목록·요약 불일치, 원천 누락·중복 규칙 ID, 표 마커 누락·중복·위치 오류는
실패로 처리한다. `--write`는 표만 갱신하며 상태·결정·관문을 승인하지 않는다.
`.github/workflows/ci.yml`의 Rust 시험 다음 단계에서 실행하고,
새 Python 회귀 시험은 기존 전체 시험 검색에 포함된다.

실행 증거는 [tools/evidence/audit2-blueprint-11-counts/](../../../tools/evidence/audit2-blueprint-11-counts/)
아래에 보관했다. 명령과 종료 코드가 있는 로컬 실행 기록이며 원격 CI 실행을
주장하지 않는다. 실행 로그의 행 끝 공백과 파일 끝 빈 줄만 정리했다.

| 검사 | 결과 | 로그 |
|---|---|---|
| 현재 등록 수 대조 | 182 + doctest 3, 규칙 7, 변조 38, 어휘 49 일치 | [counts.log](../../../tools/evidence/audit2-blueprint-11-counts/counts.log), [engine-list.log](../../../tools/evidence/audit2-blueprint-11-counts/engine-list.log) |
| 새 회귀 시험 | 17건 통과. 원천 추가·규칙 중복·빈 원천·깨진 Cargo 목록·수치 변조·마커 오류·CLI 읽기/쓰기·발견 실패 시 문서 보존·CI 연결 검사 | [counts-tests.log](../../../tools/evidence/audit2-blueprint-11-counts/counts-tests.log) |
| Python 전체 시험(실행 파일 준비 후) | 1,116건 실행: 1,110건 통과·기존 건너뜀 6건, 실패·오류 0 | [python-tests-final.log](../../../tools/evidence/audit2-blueprint-11-counts/python-tests-final.log) |
| 음성 대조 | 변경 전 문서와 60·8·28·33으로 변조한 표 모두 거부, 현재 문서는 통과 | [drift.log](../../../tools/evidence/audit2-blueprint-11-counts/drift.log) |
| Rust 전체 시험 | 단위·통합 444건 + doctest 3건 통과, 실패 0, 기존 무시 1건. `static_types` 10건 포함 | [rust-tests.log](../../../tools/evidence/audit2-blueprint-11-counts/rust-tests.log) |
| Rust 포맷·Clippy | 모두 통과 | [rust-format.log](../../../tools/evidence/audit2-blueprint-11-counts/rust-format.log), [rust-clippy.log](../../../tools/evidence/audit2-blueprint-11-counts/rust-clippy.log) |
| 어휘·검증 자료 내부 일관성·변조 자체 시험 | 49축·269값, 14표본·142조항, 변조 38종 모두 통과 | [vocabulary.log](../../../tools/evidence/audit2-blueprint-11-counts/vocabulary.log), [validation.log](../../../tools/evidence/audit2-blueprint-11-counts/validation.log), [tamper-tests.log](../../../tools/evidence/audit2-blueprint-11-counts/tamper-tests.log) |
| §11 결정 색인 | ADR·DEC 36개 일치 | [status.log](../../../tools/evidence/audit2-blueprint-11-counts/status.log) |
| 제품 목적 등록·설계 명세 | P01~P19 작업 연결·필수 시험 9종 등록, 기계 검사 44/44·존재 검사 72/72 통과 | [product-purpose.log](../../../tools/evidence/audit2-blueprint-11-counts/product-purpose.log), [spec-check.log](../../../tools/evidence/audit2-blueprint-11-counts/spec-check.log) |

Python 전체 시험의 첫 실행은 1,116건 중 기존 온톨로지 시험 2건에서
실행 파일을 찾지 못했다([python-tests.log](../../../tools/evidence/audit2-blueprint-11-counts/python-tests.log)).
환경의 공유 Cargo 산출 경로와 시험의 고정 경로가 달랐다. 시험이 기대하는
작업 트리 내부 경로에 `ontology-case-runner`를 명시적으로 빌드했다
([ontology-build.log](../../../tools/evidence/audit2-blueprint-11-counts/ontology-build.log)).
그 뒤 전체 시험이 통과했다. 건너뜀 6건은 비공개 원본 미설정 2건,
로컬 보관본·`pdftotext` 조건 미충족 3건, 설치된 botocore가 이미 조건부 쓰기를
지원해 적용되지 않는 구버전 시험 1건이다. 새 시험 17건에는 건너뜀이 없다.
허용 경로·금지 문서 불변·로컬 링크·공백 검사는
[scope.log](../../../tools/evidence/audit2-blueprint-11-counts/scope.log)에 남긴다.

09_제품목적_대응표의 P08·P14에 필요한 엔진 기반의 현황·회귀 검사 증거다.
P01~P19의 실제 원문 수집·상품 릴리스·화면·사용자 이해 시험 완료 증거를
대체하지 않는다. R2 관측 수는 기존 역사적 기록으로 유지하며 실제 R2·제공자·
프로덕션·GitHub에 접근하거나 커밋·푸시하지 않았다.
