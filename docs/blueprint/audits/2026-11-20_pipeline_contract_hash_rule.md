# Audit 7 동적 HTML 본문 해시 규칙

[BLUEPRINT §4](../../BLUEPRINT.md#4-시스템-계층)는 현재 규칙 `html-visible-text-v3`이 `DATA_PIPELINE_CONTRACT` §3·§3.1에 적용된다고 명시한다. 보호 대상 계약의 40·55행에는 v1 표기가 남아 있다. v3는 바이트가 달라진 HTML에 대해 같은 규칙으로 계산한 본문 해시를 비교한다. 본문이 같으면 `bytes_changed_content_same`으로 기록하며 원본 바이트는 별도로 보존한다.

[갱신 도구](../../../tools/rebaseline_html_samples.py)는 로컬 보관 사본에서 HTML 표본의 고정 SHA-256 키를 읽고 바이트 해시를 재검사한다. 표본의 출처 호스트를 적용해 현재 규칙으로 해시를 계산하고, 모든 HTML 원본이 확인됐을 때 `content_sha256`·`content_hash_rule`을 한 번에 저장한다. [실행 방법](../validation/README.md#html-본문-해시).

[회귀 시험](../../../tools/tests/test_rebaseline_html_samples.py) 5건은 호스트별 정규화, 해시와 버전의 동시 갱신, 다른 필드와 파일 권한 보존, 재실행, 누락·변조·저장 실패에 대한 기존 CSV 보존, 입력 형식, 상위 문서 정합성을 확인했다. 실제 CSV로 빈 로컬 보관소를 지정한 실행은 첫 원본 누락으로 종료 1이었으며, 실행 전후 CSV 바이트 SHA-256이 같았다.

원본 사본 제공은 [위임 결정](../../decisions/audit7-pipeline-contract-hash-rule.md)으로 기록했다. 승인된 담당자가 지정 실행 환경에서 고정 키 3건을 읽어 로컬 보관 사본을 제공하고, 도구가 바이트 SHA-256을 먼저 대조한 뒤 기준값을 갱신한다. 이 작업 트리에는 R2 자격 증명이 없어 보관소 요청을 보내지 않았으며, 사본 제공과 실제 갱신은 후속 작업이다. [추가 회귀 시험](../../../tools/tests/test_audit7_pipeline_contract_hash_rule.py) 4건은 결정의 조건, 보존된 v1 기준값과 고정 원본 키의 대조, 보호 계약 40·55행의 대기 중 정정과 설계도 우선, 검증 안내·감리·증거의 공개 상태를 확인한다.

Python 전체 1,762건 중 1,756건이 통과했고 6건은 건너뛰었다(보관 사본 필요 5건, 구버전 botocore 경로 1건). 이전 라운드 첫 실행은 작업 트리 안으로 설정한 임시 디렉터리 때문에 격리 시험 3건이 실패했고, 기본 임시 디렉터리에서 전체를 다시 실행해 통과했다. 이번 라운드 첫 전체 실행에서는 `test_blocked_redirect_is_reported_and_not_retried`가 실패했다. 원인은 재시도 로직이 아니라 전역 `time.sleep` 모의 창 안에서 `report()`의 pdftotext·tesseract 버전 확인 자식 프로세스가 만든 바쁜 대기 폴링(0.001→0.05 두 배 증가)이며, 공유 장비 부하에서 재현됐다. 다른 시험의 관례대로 `vs.tool_version`을 모의해 고친 뒤 전체를 다시 실행해 통과했다. 라운드 2에서 main(설계도 표류 갱신)과의 병합 충돌을 해소했다: 유일한 충돌은 그 시험의 주석이었고 양쪽이 같은 `vs.tool_version` 모의를 추가했으므로 main의 더 상세한 주석을 채택했으며, 해소 파일은 main과 바이트 일치다. 병합 뒤 노드 시험 9건과 전체 스위트를 재실행해 통과했다(main이 시험 2건을 추가해 1,760→1,762). Rust 워크스페이스 시험 537건 통과(무시 1건), 시나리오 API와 온톨로지 실행기 시험 각 4건 통과. 검증 자료 내부 일관성, 변조 시험 40건과 BLUEPRINT 수치·결정 색인 검사도 통과했다.

이 작업 트리에는 `klia_pub_cancer_compare`·`klia_pub_cancer_criteria`·`kb_caregiver_cost_html`의 2026-10-09 원본이 없다. `samples.csv`와 과거 관측의 v1 기준값은 보존했다. 세 원본의 승인된 로컬 사본으로 재계산하는 단계가 남았다([사본 제공 결정](../../decisions/audit7-pipeline-contract-hash-rule.md)). P02·P03의 실제 수집·보관 및 첫 출시의 완료 판정은 대응표의 증거를 따른다.
