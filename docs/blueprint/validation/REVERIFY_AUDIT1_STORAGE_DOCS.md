# Audit 1: V1 보관소 문구 수정 검증

검증일: 2026-10-25. 대상: `audit1-blueprint-v1-row-s3-stale`, fix round 4.
연결: A1·A2·A4, L1·L2, I6, V1.

## 수정

- `docs/BLUEPRINT.md` §9.2 V1 행(253행): ADR-0016의 Cloudflare R2 결정과 2026-10-09 보존·다운로드 대조 완료를 반영했다. 남은 조건은 파생 6건의 재생성 도구와 재현 검증, 다른 계열 AI 검수, 화면 열린 항목(S1·S6)이다. V1 관문은 여전히 미통과다.
- 같은 문서 §11 코드 행(318행): R2 보존·대조 도구와 비용 한도 장치를 적고, AWS S3 정의는 대안으로 남긴 미배포 정의임을 명시했다.
- `GAP_REPORT.md` 21행은 이미 R2 결정·보존 결과와 완전 재현 8건·미검증 6건을 정확히 적고 있어 유지했다. 테스트에서 BLUEPRINT와 함께 근거 기록에 대조한다.
- `tools/tests/test_storage_provider_docs.py`의 `expectedFailure`를 제거했다. 이전 문구 부재, V1 남은 조건, 코드 목록, R2 기록의 수치·개별 해시 일치를 검사한다. §11 대조 완료 검사도 해당 절 안에서 수행한다.

이번 작업에는 BLUEPRINT 수정이 명시적으로 허용됐다. 수정·검증 기록은 허용 경로인 이 문서에 둔다.

3차 검토의 차단 사유는 허용 경로 밖의 `docs/review/2026-10-22_audit1_blueprint_s3_stale.md` 추가였다. 이전 검증은 HEAD와만 비교해 노드의 기존 커밋 `84666b5`에 포함된 추가를 놓쳤다. 해당 파일을 제거해 노드 시작 전 기준(`d6c849b`)으로 복원했다. `git diff d6c849b -- docs/review/2026-10-22_audit1_blueprint_s3_stale.md` 결과는 비어 있다. 노드 전체 변경은 이 기준과 비교하며, 기존 GAP_REPORT 수정도 허용 경로 안에 있다.

4차 검토에서 지적한 허용 경로 밖 미추적 파일 `DECISION_REQUIRED.md.resolved-1023`도 제거했다. 해당 파일은 BLUEPRINT 수정 허용 전의 차단 기록으로, 현재 작업에는 해당하지 않는다. `DECISION_REQUIRED.md`는 변경하지 않았다.

기준 대비 변경 경로와 새 검증 기록은 총 5개이며 모두 허용 범위다: `docs/BLUEPRINT.md`, `docs/blueprint/validation/GAP_REPORT.md`, `docs/blueprint/validation/README.md`, 이 문서, `tools/tests/test_storage_provider_docs.py`. 금지된 네 경로의 기준 대비 diff도 비어 있다. 경로 확인에는 기준 대비 추적 파일 diff와 `git ls-files --others --exclude-standard`의 미추적 파일을 함께 포함한다.

## 근거

기존 [source_checks/](source_checks/)의 2026-10-09 실행 기록을 읽어 확인했다.

| 기록 | 확인한 결과 |
|---|---|
| `2026-10-09_r2_listing_raw.json` | 원본 58/58키 바이트 일치, 추가 키 없음 |
| `2026-10-09_r2_listing_derived_v2.json` | 파생 v2 61/61키 바이트 일치, 추가 키 없음 |
| `2026-10-09_r2_verify_samples.json` | 표본 14/14건 원본 해시 일치 |
| `2026-10-09_r2_reproduce_ocr.json` | 원본 해시·인용 위치 14/14 일치, 완전 재현 8건, 파생 미검증 6건 |

이번 검증은 저장소에 고정된 기록과 문서의 일치 확인이다. R2 접속·업로드·원본 재다운로드는 실행하지 않았다.

## 재실행 결과

아래 명령은 4차 검토에서 다시 실행했다. 이번 회귀 시험은 수정된 문서와 기존 R2 실행 기록을 대조한다.

| 명령 | 결과 |
|---|---|
| `python3 -m unittest discover -s tools/tests -p test_storage_provider_docs.py -v` | 10개 모두 통과. 예상 실패 없음 |
| `python3 -m unittest discover -s tools/tests` | 558개 실행, 실패 0, 건너뜀 6 |
| `python3 tools/validation_check.py` | 내부 일관성 통과: 표본 14, 조항 142, 필드 74, 가격 관측 15, 화면 모델 2, 부족분 26 |
| `python3 tools/validation_check.py --selftest` | 변조 38종을 의도한 이유로 모두 검출 |
| `python3 tools/vocab_check.py` | 45축·228값 통과 |
| `cargo test --all` | 통과 388, 실패 0, 무시 1(문서 테스트 포함) |
| `cargo fmt --all -- --check` | 통과 |
| `cargo clippy --all-targets -- -D warnings` | 통과 |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 44/44, 존재 검사 72/72 통과 |
| `cargo build --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir target/audit1-ontology` | 통과 |
| `python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py target/audit1-ontology/debug/ontology-case-runner` | 질문 11/11, 제약 자체 시험 15/15, 릴리스·문서 모델 시험 25/25 통과 |
| `git diff d6c849b --exit-code -- docs/review/2026-10-22_audit1_blueprint_s3_stale.md` | 통과: 노드의 허용 경로 밖 추가를 되돌림 |
| `git diff d6c849b --exit-code -- docs/PRINCIPLES.md docs/data/ docs/design/CONSUMER_FLOW_SPEC.md DECISION_REQUIRED.md` | 통과: 금지 경로 변경 없음 |
| 기준 대비 diff와 미추적 파일을 합친 허용 경로 검사 | 통과: 5개 경로 모두 허용 범위, 금지 경로 변경 없음 |
| `test ! -e DECISION_REQUIRED.md.resolved-1023` | 통과: 4차 검토의 허용 경로 밖 파일 없음 |
| `git diff --check` | 통과 |

Python 건너뜀은 비공개 원본 보관본이 필요한 시험 5개와 현재 botocore가 조건부 쓰기를 지원해 해당하지 않는 구버전 거부 시험 1개다. 기존 CSV 읽기의 `ResourceWarning`이 출력됐으며 실패는 없었다.
