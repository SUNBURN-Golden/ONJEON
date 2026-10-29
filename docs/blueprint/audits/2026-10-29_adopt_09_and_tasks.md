# Audit 3: 09·tasks.json 정본 한정 채택 — Fix round 1

2026-10-29. 검증 대상은 기준 HEAD `1a583efae4ec68107845037fac4000eab56d44cb` 위의 이 작업 트리다. 커밋·푸시·GitHub 호출은 하지 않았다. 시험 대상 변경 파일은 [SHA-256 목록](../../../tools/evidence/audit3-adopt-09-and-tasks-as-canon/source-sha256.json)으로 고정한다(이 결과 문서와 실행 로그는 제외).

## 지적과 반영

차단 지적은 결정 메모만 있고 실제 채택이 없다는 것이었다. [ADR-0019](../../decisions/ADR-0019-제품-완료와-작업-계약-한정-채택.md)로 09의 제품 완료 증거 기준과 tasks.json의 데몬 작업 소스·개별 수락 계약을 BLUEPRINT 하위에 한정 채택했다. BLUEPRINT §0.1·§7·§9.5·§11·§13, 루트 README, DECISIONS BP-D-20·충돌 해소표, 두 계약의 상태, 묶음·인계 README와 daemon_rules.json 상태를 동기화했다. DEC-BUNDLE-STATUS의 과거 미채택 판단은 부분 대체 표시로 보존했다. §11의 자동 결정 색인도 갱신했다.

기존 경로를 유지했고 09 본문과 JSON의 `_status` 외 모든 필드는 기준 HEAD와 동일하다([대조 기록](../../../tools/evidence/audit3-adopt-09-and-tasks-as-canon/contract-preservation.log)). 작업·시험·관문·실제 완료 증거를 새로 만들거나 완화하지 않았다. 묶음 전체·온톨로지·daemon_rules.json·공통 PR 기준을 일괄 채택하지 않았고 `non_binding_until_adopted`는 그대로다.

## 회귀 검증

로그 디렉터리: `tools/evidence/audit3-adopt-09-and-tasks-as-canon/`. 다음 검사는 이 작업 트리에서 직접 실행했다.

| 명령·검사 | 결과 | 로그 |
|---|---|---|
| `python3 -I -m unittest discover -s tools/tests -p test_pr_policy.py -v` | 23 통과. 과거 미채택 강제를 제거하고 한정 채택·문서 위계·양쪽 계약 링크·README/원장 색인·실증 관문·공통 PR 기준 제외 검사 추가 | [policy-tests.log](../../../tools/evidence/audit3-adopt-09-and-tasks-as-canon/policy-tests.log) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업 연결·필수 시험 ID 9개 담당 작업 등록 통과 | [product-purpose.log](../../../tools/evidence/audit3-adopt-09-and-tasks-as-canon/product-purpose.log) |
| `python3 -I -m unittest discover -s tools/tests -p test_product_purpose.py -v` | 17 통과(필수 ID·담당 작업 누락·잘못된 연결 회귀 포함) | [purpose-tests.log](../../../tools/evidence/audit3-adopt-09-and-tasks-as-canon/purpose-tests.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 45/45, 존재 72/72 통과 | [spec-check.log](../../../tools/evidence/audit3-adopt-09-and-tasks-as-canon/spec-check.log) |
| `python3 -I tools/blueprint_status.py` · `tools/blueprint_counts.py` | 결정 색인 37파일·등록 수 최신성 통과 | [status](../../../tools/evidence/audit3-adopt-09-and-tasks-as-canon/blueprint-status.log), [counts](../../../tools/evidence/audit3-adopt-09-and-tasks-as-canon/blueprint-counts.log) |
| `cargo test --all` | 475 통과(문서 시험 포함), 실패 0 | [cargo-test.log](../../../tools/evidence/audit3-adopt-09-and-tasks-as-canon/cargo-test.log) |
| `cargo fmt --all -- --check` · `cargo clippy --all-targets -- -D warnings` | 둘 다 종료 코드 0 | [fmt](../../../tools/evidence/audit3-adopt-09-and-tasks-as-canon/cargo-fmt.log), [clippy](../../../tools/evidence/audit3-adopt-09-and-tasks-as-canon/cargo-clippy.log) |
| `python3 -I tools/vocab_check.py` | 49축·270값 통과 | [vocabulary.log](../../../tools/evidence/audit3-adopt-09-and-tasks-as-canon/vocabulary.log) |
| `python3 -I tools/validation_check.py` · `--selftest` | 자료 정합성·변조 38건 탐지 통과 | [validation](../../../tools/evidence/audit3-adopt-09-and-tasks-as-canon/validation.log), [selftest](../../../tools/evidence/audit3-adopt-09-and-tasks-as-canon/validation-selftest.log) |
| 온톨로지 runner 빌드 후 `ontology_check.py target/onto/debug/ontology-case-runner` | 질문 11/11·제약 15/15·릴리스/문서 25/25 통과 | [build](../../../tools/evidence/audit3-adopt-09-and-tasks-as-canon/ontology-build.log), [ontology](../../../tools/evidence/audit3-adopt-09-and-tasks-as-canon/ontology.log) |
| 데몬 `dry_run.py --scenario all --require-all --quiet` (현재 rules, mock_tasks) | 종료 코드 0, 필수 시험 ID 누락·미등록·중복 0 | [daemon-dry-run.log](../../../tools/evidence/audit3-adopt-09-and-tasks-as-canon/daemon-dry-run.log) |

전체 Python 회귀: 온톨로지 runner를 빌드하고 `ONJEON_ONTOLOGY_RUNNER="$PWD/target/onto/debug/ontology-case-runner" python3 -m unittest discover -s tools/tests -v` 실행. **1,284개 중 1,278 통과·6 건너뜀·실패 0**, 종료 코드 0([python-tests.log](../../../tools/evidence/audit3-adopt-09-and-tasks-as-canon/python-tests.log)). 건너뜀: 보관 원본 환경 변수 미설정 2건, 로컬 보관본·pdftotext 필요 3건, 설치된 botocore가 조건부 쓰기를 지원해 구형 버전 전용 시험 1건. 이 항목들은 통과로 세지 않았다.

마지막 확인: 변경 파일은 허용 경로 안에 있고 보호 경로 변경은 없다. 변경 Markdown의 로컬 링크가 존재하며 `git diff --check`도 통과했다.

## 증거의 한계

이 검증은 채택의 명시성·문서 및 작업 그래프 정합성·로컬 코드 회귀 증거다. 실제 데이터 확보·화면 사용성·출시 완료, D-04/O14/O17 등의 관문 해제, 데몬 운영 승인이나 독립 리뷰 PASS를 뜻하지 않는다. 데몬 모의 실행은 기존 G47·G51~G57 공백 8건도 그대로 보고한다. 제품 완료는 계속 09의 실제 증거와 T-OP-08 `purpose-rows-all-closed`로 판정한다.
