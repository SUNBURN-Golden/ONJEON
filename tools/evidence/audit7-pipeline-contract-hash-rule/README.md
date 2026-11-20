# Audit 7 HTML 표본 기준값 갱신 경로 검증

2026-11-20, `audit7-pipeline-contract-hash-rule` 작업 트리에서 실행했다. [결정과 계약](../../../docs/decisions/audit7-pipeline-contract-hash-rule.md) · [감리 기록](../../../docs/blueprint/audits/2026-11-20_pipeline_contract_hash_rule.md).

| 실행 경로 | 확인한 동작 |
|---|---|
| [결정·보존 기준값 회귀 시험](../../tests/test_audit7_pipeline_contract_hash_rule.py) | 위임 결정이 고정 키 3건, 지정 실행 환경, SHA-256 선대조, 재수집 대체 금지를 기록한다. `samples.csv` 12~14행은 보존된 2026-10-09 v1 기준값이고 바이트 키는 고정 원본 목록과 일치한다. 보호 계약 40·55행은 정정 대기 상태이며 BLUEPRINT §4가 현행 v3를 선언한다. 검증 안내·감리·증거가 남은 작업을 공개하고 결정을 링크한다. |
| [갱신 도구 회귀 시험](../../tests/test_rebaseline_html_samples.py) | 합성 로컬 보관 사본으로 호스트별 정규화, `content_sha256`·`content_hash_rule` 동시 갱신, 다른 필드·파일 권한 보존, 재실행 멱등, 누락·변조·저장 실패 시 기존 CSV 보존, 입력 형식 거부, 상위 문서 정합성을 확인한다. |
| [변경 감지 회귀 시험](../../tests/test_verify_sources.py) | v1·v2 기준선은 v3와 비교하지 않고 `changed`로 보고한다(`test_baseline_under_an_older_rule_is_not_compared`). 현재 규칙 기준선에서만 `bytes_changed_content_same`이 나온다. |
| 실제 CSV + 빈 로컬 보관소 | `python3 -I tools/rebaseline_html_samples.py --raw-dir <빈 디렉터리>`는 첫 원본 누락(`klia_pub_cancer_compare`)으로 종료 1이며, 실행 전후 `samples.csv` 바이트 SHA-256이 같다. 이 작업 트리에는 2026-10-09 원본 3건의 바이트가 없어 실제 v3 기준값은 계산하지 않았다. |
| [수면 모의 오염 수정](../../tests/test_verify_sources.py) | 첫 전체 실행에서 `test_blocked_redirect_is_reported_and_not_retried`가 공유 장비 부하 속 자식 프로세스 바쁜 대기 폴링(0.001→0.05)으로 실패했다. `report()`의 버전 확인 스포너(`vs.tool_version`)를 모의하는 관례를 적용해 고쳤고, 부하 상태에서 단일 시험 5회·클래스 전체·전체 스위트 재실행이 통과했다. |

전체 시험 명령·결과는 [검증 로그](verification.log)에 기록했다. 실제 v3 기준값 갱신은 승인된 담당자가 지정 실행 환경에서 원본 사본 3건을 제공한 뒤의 후속 작업이며, 보호 계약 40·55행의 직접 정정은 `docs/data/` 편집 권한이 있는 경로에 남는다.