# Audit 4: 온톨로지 원본 규칙의 Cargo 검증과 내용 해시 고정

대상: `audit4-ontology-rules-in-cargo`. A1·A2·A5, Q1·Q2·Q5·Q7, L6, I1·I2·I18, M0/V1 회귀 보강. 제품 목적 대응표 P08·P14의 기반 검증이다.

`docs/blueprint/proposals/온톨로지/규칙/*.json`의 두 원본을 `packages/rules-engine/tests/ontology_rules.rs`에서 직접 읽는다. `packages/fixtures/ontology`나 다른 복사본을 시험하는 것으로 대체하지 않는다. 파일 이름과 해시 목록의 키를 두 개로 고정하여 규칙 추가·삭제·검사 누락도 실패시킨다.

내용 해시는 [rule_content_hashes.json](../proposals/온톨로지/rule_content_hashes.json)에 고정한다. 엔진의 `rule_content_hash` 계약(파싱한 JSON의 객체 키만 재귀 정렬, compact UTF-8 JSON, 최상위 `release_id` 제외, SHA-256)을 그대로 따른다. A-box 릴리스의 기존 `rule_files`는 파일 바이트 해시이므로 별개이며 변경하지 않았다. 의도한 규칙 변경 때만 로직·근거와 사례를 검토하고 내용 해시를 갱신한다. 시험은 실행 중 기대 해시를 재생성하지 않는다.

Cargo 시험은 90일 면책 전날/당일, 1년 감액 전날/당일, 홀수 금액의 감액 범위, 만기 당일/다음날, 기지급·제외, 하나 갱신 시작일, `null`·키 누락의 미확인 보존을 검증한다. 원본을 다시 읽어 전체 결과 바이트를 비교하고 결과의 버전·스키마·릴리스·근거·고정 해시를 대조한다. 버전은 유지한 채 금액 로직이나 근거만 바꾼 음성 대조는 고정 해시와 불일치한다.

이 작업을 시작할 때 runner의 `release_id`·`schema_version` 출력과 CI의 runner `cargo build --locked`는 이미 반영돼 있었다. runner Cargo 시험을 추가하여 두 원본 × 지급/비지급/판정불가 6행의 식별 필드·결과를 엔진과 대조한다. `release_id`는 키 존재와 명시적 `null`을 함께 확인한다. 기존 Python 시험은 두 DSL 버전, 릴리스 생략·null·문자열을 계속 검증한다. Python 대체 빌드에도 `--locked`를 추가하고, CI의 모든 Cargo 빌드·lint·시험 명령에 `--locked`가 있는지 회귀 검사한다.

실행 명령·결과·원본 로그는 [검증 증거](../../../tools/evidence/audit4-ontology-rules-in-cargo/README.md)에 기록한다. BLUEPRINT §11의 엔진 등록 수는 `blueprint_counts.py --write`로 갱신한다.

두 규칙의 `fixture_only`와 원본·A-box 릴리스 내용은 유지한다. 실제 약관 해석 검수·서비스 릴리스·소비자 화면·P08·P14 전체·첫 출시 완료 증거가 아니며, 온톨로지 제안의 정본 채택이나 관문 해제를 뜻하지 않는다.
