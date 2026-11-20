# Audit 7 HTML 표본 원본 사본 제공과 기준값 갱신 경로

2026-11-20, ONJEON 자동 개발 루프의 위임 결정·가역·사용자 확정 아님. `audit7-pipeline-contract-hash-rule` 작업 트리의 결정이며 [BLUEPRINT §4](../BLUEPRINT.md#4-시스템-계층)와 ADR-0011 문서 위계를 적용한다. [감리 기록](../blueprint/audits/2026-11-20_pipeline_contract_hash_rule.md) · [검증 증거](../../tools/evidence/audit7-pipeline-contract-hash-rule/README.md).

## 결정

질문: 승인된 R2 운영 담당자가 고정 키의 원본 3건을 지정 실행 환경에서 읽어, 이 작업에 사용할 로컬 보관 사본을 제공할 것인가.

결정: **제공 경로를 승인한다.** 실제 v3 기준값 갱신은 이 경로로만 하며, 아래 조건을 고정한다.

- 대상은 2026-10-09 비공개 R2 보관본 3건뿐이다. 객체 키는 [표본 CSV](../blueprint/validation/samples.csv)의 `sha256`과 [고정 원본 목록](../blueprint/validation/source_checks/archive_listing_raw.json)에 이미 고정돼 있다.
  - `klia_pub_cancer_compare`: `2d384476ec877db49fa7bb28488777c6040dc43e298f71703ec52f64bc598ff5`
  - `klia_pub_cancer_criteria`: `200da98f6bde03bc5ee5c4f38b0ff192ab4653fb037e26ac47d13593e9798b35`
  - `kb_caregiver_cost_html`: `6ade7ccbb07bfa9ae002ec686131167fa308e6a2d0b7730d85b34698b13ed0b2`
- 읽기는 승인된 담당자가 지정 실행 환경(`infra/r2/BUDGET.md` §6)에서 수행한다. 원장 확인·예약 전에는 보관소 요청을 보내지 않는 ADR-0017 비용 제한을 그대로 적용한다. 사본은 내부 검증용이며 외부 재배포 허가가 아니다.
- 로컬 사본은 `objects/sha256/<aa>/<bb>/<sha256>` 구조로 제공한다. [갱신 도구](../../tools/rebaseline_html_samples.py)가 각 행의 바이트 SHA-256을 먼저 대조한 뒤 `content_sha256`·`content_hash_rule`을 함께 갱신한다. 원본이 없거나 해시가 다르면 CSV를 쓰지 않고 중단한다.
- 현재 출처 재수집으로 대체하지 않는다. 동적 HTML은 받을 때마다 바이트가 달라지므로, 지금 받은 바이트는 2026-10-09 스냅샷의 기준값이 될 수 없다.

## 이 작업 트리에서 하지 않는 것

- 이 빌드 작업 트리에는 R2 자격 증명이 없다(DEC-D-04: 토큰은 ONJEON box secrets env에서만 읽는다). 이 노드는 보관소 요청을 보내지 않았으며, 사본 제공과 도구 실행은 승인된 담당자의 후속 작업이다.
- 사본이 준비되기 전까지 `samples.csv` 12~14행은 2026-10-09에 계산한 v1 기준값을 보존한다. 규칙 이름이 다르면 `detect`는 본문 해시를 비교하지 않고 `changed`로 보고하므로 이 3건의 변경 감지가 거칠어지는 열화는 [검증 안내](../blueprint/validation/README.md#html-본문-해시)에 공개한다. v1 기준값을 v3와 비교하거나, 원본 없이 v3 값을 만들지 않는다.
- 보호된 `docs/data/DATA_PIPELINE_CONTRACT.md` 40·55행의 v1→v3 직접 정정은 이 노드의 편집 범위가 아니다. 정정 전에는 BLUEPRINT §4의 v3 기준이 문서 위계(ADR-0011)로 우선한다. 두 행의 정정은 `docs/data/` 편집 권한이 있는 경로에 남기며, 정정 시 이 결정의 회귀 시험 고정도 같은 변경에서 갱신한다.

## 검증

[회귀 시험](../../tools/tests/test_audit7_pipeline_contract_hash_rule.py)은 이 결정의 조건(고정 키 3건, 지정 실행 환경, SHA-256 선대조)과 보존된 v1 기준값, 보호 계약의 대기 중 정정, 검증 안내·감리 기록의 공개 상태를 대조한다. [갱신 도구 회귀 시험](../../tools/tests/test_rebaseline_html_samples.py)은 합성 보관 사본으로 호스트별 정규화, 해시·버전 동시 갱신, 누락·변조 시 CSV 보존을 확인한다. 실행 명령·결과는 [검증 증거](../../tools/evidence/audit7-pipeline-contract-hash-rule/README.md)에 있다.

## 재검토 조건

원본 사본 3건이 준비되어 기준값을 실제로 갱신할 때, 보호 계약의 두 행이 정정될 때 이 결정과 시험 고정을 함께 갱신한다. 사본 제공 경로가 거부되거나 담당자가 지정되지 않으면 이 결정을 다시 검토한다.