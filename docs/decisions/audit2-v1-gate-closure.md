# Decision: Audit 2 — V1 종료 경로와 증거 관문

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-10-28 07:12 KST); reversible.

**Decision:** V1 미통과를 유지하고 다음 증거 순서로 종료한다. ① 구현 담당자는 tools/verify_sources.py에 누락된 재생성 경로를 추가한다: pdfplumber 선택 페이지 추출 2건(fss_std_terms_byl15, kb_driver_terms), HTML 표·본문 직렬화 3건(klia_pub_cancer_compare, klia_pub_cancer_criteria, kb_caregiver_cost_html), OCR 전체본 조립 1건(kyobo_1995_cancer_scanned). 도구 버전·페이지·옵션·출력 형식을 고정하고 원본에서 재생성한다. ② 승인된 비공개 보관본으로 reproduce --ocr를 실행하여 전체 14건 reproduced, 미검증·불일치·명세 오류 0, 종료 코드 0인 보고서를 남긴다. --allow-unverified나 출력 삭제로 통과시키지 않는다. 기존 결과를 재현할 수 없어 새 파생 판을 만들면 이전 판을 보존하고 변경 이유·새 명세 해시·재검수 증거를 기록한다. ③ T-KN-06에서 ReviewDecision 생성·감사 연결을 구현하고 단일 계열 거부, 불일치·반례 hold, test 결정의 서비스 릴리스 유입 거부를 시험한다. 감독자는 DEC-D-02의 접근·월 한도 확인 증거가 확보된 뒤 게이트를 등록하고 실제 이종 계열 검수를 배정한다. 전체 V1 인코딩·규칙·화면 연결에 대해 작성 계열 밖 검토와 코드 검사·레드팀 결과를 기록하고, ReviewDecision을 대상 해시·실제 모델 계열·프롬프트 판·실행 로그·environment에 연결한다. 개발 PR 리뷰를 지식 검수로 대체하지 않는다. ④ S1의 조건 확인 라벨 집중 문제와 S6의 가격 조건 부족을 화면 사례·회귀 검사·설계 결정으로 닫는다. 가격 보간이나 출시 범위 축소로 해결하지 않는다. ⑤ 재현·검수·화면 증거를 validation/README.md와 BLUEPRINT §9.2에 연결한 뒤 V1을 판정한다. 첫 출시 완료는 별도로 09_제품목적_대응표의 모든 완료 증거와 T-OP-08을 충족해야 한다.

**Why:** 저장된 source_checks/2026-10-09_r2_reproduce_ocr.json은 reproduced 8, derived_unverified 6이며, 현재 Regenerator에도 해당 경로가 없다. DEC-D-02는 업체·모델 ID를 확정하지 않았고 services/ai-review도 없다. 최초 결정 시 읽기 전용 점검에서 재현 판정표 단위시험 1개(10개 판정 사례)와 validation_check.py가 통과했다. 이는 내부 일관성·판정 로직 증거이며 실제 14/14 재현이나 이종 계열 검수 완료 증거가 아니다. 따라서 finding은 아직 해결 완료로 표시할 수 없다. 이 결정은 구현·검증 순서를 정하며 지출·자격 증명 발급·실서비스 호출·배포를 승인하지 않는다.

**Options:** ['채택: 누락 재생성기 구현 → 14/14 재현 → 실제 이종 계열 ReviewDecision → S1·S6 해결의 증거 기반 종료.', '기각: 원본 해시 14/14와 DEC-D-02 기록만으로 종료. 파생 재현과 실제 검수 증거가 빠진다.', '기각: 같은 계열 리뷰·모의 ReviewDecision·개발 PR 승인으로 실제 지식 검수를 대체.', '기각: 제공자 확보까지 모든 개발 중단. 재생성기와 모의 검수·거부 경로 구현은 먼저 진행 가능하다.']

**Revisit if:** 기존 파생물을 동일 버전으로 재현할 수 없어 새 판이 필요하거나, 검수 대상의 작성 계열 변경으로 독립 검토자가 부적격해지거나, 제공자 접근 조건을 충족하지 못하거나, 교차 검수에서 설계 변경이 필요한 오류가 발견되거나, S1·S6 해결이 정본·출시 범위 변경을 요구할 때 재검토한다.


## 실행 인계와 종료 증거 (fix round 1, 2026-10-28)

이 노드는 종료 경로를 정하는 결정이다. **V1 관문은 미통과**이며 실제 재생성·검수 완료를 선언하지 않는다. 아래 순서의 담당은 역할 배정이며 제공자 접근·지출 승인이 아니다.

| 순서 | 담당·작업 | 다음 단계로 넘길 증거 |
|---|---|---|
| 1 | 재현 도구 구현 담당: `tools/verify_sources.py`의 누락 재생성기를 구현하고 합성 입력으로 시험 | 선택 페이지·표/본문 직렬화·OCR 전체본의 결정적 바이트 출력, 도구 판 불일치와 출력 누락/변조 실패 시험. 실제 보관 명세에서 페이지·옵션·구분자·정렬·개행을 확인하고 추측하지 않음 |
| 2 | 승인된 보관본 접근 담당: 고정 명세의 전체 14개 표본을 `reproduce --ocr`로 재현 | 새 `docs/blueprint/validation/source_checks/` 보고서: `reproduced=14`, 나머지 상태 0, 종료 0, 도구 판·원본/명세 해시. 2026-10-09 보고서는 역사 기록으로 보존 |
| 3 | T-KN-06 구현 담당과 감독자: 모의 검수 경로 구현·시험 후 [DEC-D-02](DEC-D-02.md)의 접근 증거·월 한도 확인 및 게이트 등록 | 단일 계열 거부·불일치/반례 hold·test 결정 릴리스 유입 거부 시험과 실제 접근 확인 기록. DEC-D-02 문서 존재만으로 등록하지 않음 |
| 4 | 작성 계열 밖 검수 담당: V1 인코딩·규칙·화면 연결 전체를 실제 검수 | 대상 해시별 ReviewDecision과 작성/검토 계열·모델 식별·프롬프트 판·실행 로그·environment·코드 검사·레드팀 결과의 연결. 미검수/불일치/반례가 남으면 hold. 개발 PR 리뷰는 이 증거가 아님 |
| 5 | 화면 구현/검증 담당: [SCREEN_BINDING의 S1·S6](../blueprint/validation/SCREEN_BINDING.md) 해결 | S1 라벨 집중과 S6 가격 조건 부족의 화면 사례, 회귀 검사, 설계 결정. 자료가 없는 가격을 보간하거나 출시 범위를 줄이지 않음 |
| 6 | 감독자: 위 증거의 범위·해시·판을 대조하고 V1 판정 | validation README 및 BLUEPRINT §9.2에 모든 증거를 연결한 판정 기록. 누락 시 미통과 유지. 첫 출시 판정은 09 대응표·T-OP-08로 별도 수행 |

누락 경로의 정확한 분모는 [기존 R2 재현 보고서](../blueprint/validation/source_checks/2026-10-09_r2_reproduce_ocr.json)의 `derived_unverified` 6개 표본이며, 각 표본에 아래 미재생성 출력이 하나씩 있다.

| 표본 | 도구 식별자 | 출력 |
|---|---|---|
| `fss_std_terms_byl15` | `pdfplumber@0.11.10-x1.5-y3-selected-pages` | `byl15.plumber_selected.txt` |
| `kb_driver_terms` | `pdfplumber@0.11.10-x1.5-y3-selected-pages` | `terms.plumber_selected.txt` |
| `klia_pub_cancer_compare` | `html-table-serializer@v1-session` | `list.tables.txt` |
| `klia_pub_cancer_criteria` | `html-table-serializer@v1-session` | `info_popup.tables.txt` |
| `kb_caregiver_cost_html` | `html-text@v1-session` | `page.text.txt` |
| `kyobo_1995_cancer_scanned` | `tesseract@5.3.4-kor-psm3-300dpi-gray` | `ocr_all.txt` |

이 수정의 로컬 시험 실패는 `CARGO_TARGET_DIR`로 빌드 위치가 바뀌는데 Python 시험은 고정 경로를 실행한 데서 발생했다. fallback 빌드의 `--target-dir`를 실행 경로와 일치시키고 빈 `ONJEON_ONTOLOGY_RUNNER`도 fallback으로 처리했다. 기존 prebuilt 경로와 빌드 실패 전파는 유지한다. [회귀 시험·프로젝트 검사 증거](../../tools/evidence/audit2-v1-gate-closure/README.md)는 실행 환경 수정의 증거다. 비공개 원본 재현이나 ReviewDecision 증거를 대신하지 않는다.

## main 병합 정합성 (fix round 2, 2026-10-28)

main의 동일 시험 수정과 병합하면서 고정 `--target-dir` 방식은 Cargo의 `compiler-artifact.executable`을 사용하는 방식으로 대체했다. 빌드와 실행 경로 일치라는 기존 의도를 유지하면서 target 디렉터리·target 설정도 존중한다. 미지정/빈 `ONJEON_ONTOLOGY_RUNNER`의 fallback, prebuilt 우선, 빌드 실패 전파를 유지하고 main의 120초 제한·잠금 진단·실행 파일 보고 누락 실패도 보존한다. 회귀 시험은 미지정/빈 override 각각에서 기본·변경·target별 실행 경로를 확인한다. [병합 후 시험 증거](../../tools/evidence/audit2-v1-gate-closure/fix-round2/README.md)는 이 실행 환경 정합성만 검증한다. V1의 실제 14/14 재현·이종 계열 ReviewDecision·S1/S6 관문은 여전히 미완료다.
