# Audit 3: BLUEPRINT 현황·규칙 수·보관소 이력 재검증

검증일: 2026-10-28(UTC). 대상: `audit3-blueprint-s11-refresh`.

단일 기준 BLUEPRINT의 A1·A2·A5, Q1·Q2·Q5·Q7, L6, I1~I5·I18과
09_제품목적_대응표 P08·P14의 엔진 기반 현황 추적에 연결되는 문서 감리 후속이다.
선행 수정이 이미 반영된 항목은 현재 트리에서 재검증하고, 남아 있던 ADR-0014의
실제 조항 규칙 8건을 7건으로 정정했다. 결정 자체와 관문 판정은 바꾸지 않았다.
§11의 상태·운영 관문을 검토하고 `tools/blueprint_status.py --write`로
기준일·ADR/DEC 36개 색인·내용 해시를 갱신했다.

| 발견 항목 | 현재 대조 결과·재발 방지 |
|---|---|
| §11의 Rust 42건과 소스 시험 수 불일치 | 2026-10-09의 39 + doctest 3 = 42건은 당시 재실행 로그가 있는 역사적 수치다. 현재 값은 별도 자동 생성 표에서 Cargo 등록 목록과 대조한다. 이번 트리는 단위·통합 207개, doctest 3개다. 감리 시점의 소스 62개를 현재 값으로 고정하지 않는다 |
| 실제 조항 규칙 8건 | §11 자동 생성 표는 이미 7건. ADR-0014 결과도 사례 파일을 제외한 실제 규칙 7건으로 정정하고 정정일을 남겼다. 새 CI 회귀 시험은 ADR 결과의 수와 실제 파일 목록을 대조한다 |
| 변조 시험 28건 | 현재 §11과 validation/README는 모두 38종이다. `mutations()`와 README 표기를 대조하는 CI 시험을 추가했다 |
| `tools/daemon` 누락 | §11 개발 도구 행에 T-OP-00 모의 코어·T-OP-09 실행기 검증이 이미 기록되어 있다. 기존 `test_blueprint_status.Repository`가 도구·가동 승인 경계·09 완료 증거 참조를 검사한다 |
| §6의 31축과 정본 불일치 | §6은 이미 고정 수 대신 정본·생성 문서를 참조한다. 현재 정본은 49축·270값. 기존 `test_blueprint_axis_count`가 생성 문서·정본과의 일치 및 수기 축 수 제거를 검사한다 |
| §9.2 V1의 S3 및 §7.3의 대체 이력 누락 | 현재 §9.2는 R2와 ADR-0016, §7.3은 ADR-0015의 제공자·S3 고유 설정만 대체하고 보존 규칙은 유지함을 명시한다. 기존 `test_storage_provider_docs`가 이력·V1 남은 조건·관문 미통과 및 2026-10-09 보존 기록을 대조한다 |

추가한 두 시험은 기존 CI의 `python3 -m unittest discover -s tools/tests -v`에
포함된다. [수정 전 실행](../../../tools/evidence/audit3-blueprint-s11-refresh/before.log)은
19건 중 ADR 수 불일치 1건을 검출했고, [수정 후 실행](../../../tools/evidence/audit3-blueprint-s11-refresh/counts-tests.log)은
19건 모두 통과했다. 기존 자동 집계 검사에는 수치 변조(42·8·28·31), 원천 추가,
깨진 Cargo 목록·마커와 읽기 전용/명시적 갱신 검사가 포함된다.

| 로컬 실행 | 결과 | 증거 |
|---|---|---|
| 현재 등록 수 대조 | 엔진 207 + doctest 3, 실제 조항 7, 변조 38, 어휘 49 일치 | [counts.log](../../../tools/evidence/audit3-blueprint-s11-refresh/counts.log), [engine-list.log](../../../tools/evidence/audit3-blueprint-s11-refresh/engine-list.log) |
| Rust 전체 시험 | 단위·통합 469건 + doctest 3건 통과, 실패 0, 기존 무시 1건 | [rust-tests.log](../../../tools/evidence/audit3-blueprint-s11-refresh/rust-tests.log) |
| Python 전체 시험 | 1,273건: 1,267건 통과·기존 조건부 건너뜀 6건, 실패·오류 0 | [python-tests.log](../../../tools/evidence/audit3-blueprint-s11-refresh/python-tests.log) |
| 어휘·내부 일관성·변조 자체 시험 | 49축·270값, 14표본·142조항, 변조 38종 통과 | [vocabulary.log](../../../tools/evidence/audit3-blueprint-s11-refresh/vocabulary.log), [validation.log](../../../tools/evidence/audit3-blueprint-s11-refresh/validation.log), [tamper-tests.log](../../../tools/evidence/audit3-blueprint-s11-refresh/tamper-tests.log) |
| 결정 색인 | ADR·DEC 36개 일치 | [status.log](../../../tools/evidence/audit3-blueprint-s11-refresh/status.log) |
| 제품 목적 연결·설계 명세 | P01~P19 작업 연결·필수 시험 등록, 기계 검사 45/45·존재 검사 72/72 통과 | [product-purpose.log](../../../tools/evidence/audit3-blueprint-s11-refresh/product-purpose.log), [spec-check.log](../../../tools/evidence/audit3-blueprint-s11-refresh/spec-check.log) |

Python 시험 전에 온톨로지 실행기를 빌드했다([ontology-build.log](../../../tools/evidence/audit3-blueprint-s11-refresh/ontology-build.log)).
건너뜀은 비공개 원본 미설정 2건, 로컬 보관본·`pdftotext` 조건 미충족 3건,
설치된 botocore가 조건부 쓰기를 지원해 해당하지 않는 구버전 시험 1건이다.
추가한 시험에는 건너뜀이 없다. 로그는 명령·출력·종료 코드를 기록하고 행 끝
공백과 파일 끝 빈 줄만 정리했다. 수정 전 로그는 의도한 실패 출력이다.
허용 경로·보호 문서 불변·로컬 링크·공백 검사 결과는 [scope.log](../../../tools/evidence/audit3-blueprint-s11-refresh/scope.log)에 있다.

Rust 등록 수는 무시된 시험도 포함할 수 있으므로 실행 통과 수와 구분한다.
원본 58키·파생 v2 61키의 R2 대조는 2026-10-09 관측 기록이다. 이번에는
실제 R2·제공자·프로덕션·GitHub에 접근하거나 커밋·푸시하지 않았다.

이 기록은 문서 현황·회귀 검증 증거다. P01~P19의 실제 원문 확보·상품 릴리스·
소비자 화면·사용자 이해 시험 완료 증거나 T-OP-08 출시 판정을 대신하지 않는다.
