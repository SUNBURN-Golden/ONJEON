# V1 설계 검증 자료

**지위:** 설계 검증용 자료다. 인코딩·규칙·화면 값은 AI 1차 해석이며 검수하지 않았다. 서비스 데이터로 쓰지 않는다. 표본은 서비스 범위(전 보험사·전 상품·전 특약)를 줄이는 결정이 아니다(ADR-0013). 전체 대상의 수집 상태는 `data/registry/`가 추적한다.

| 파일 | 내용 |
|---|---|
| `samples.csv` | 표본 14개 파일: 출처 URL, 수집 시각, sha256, 형식, 다루는 구조 |
| `acquisition_log.md` | 수집 경로, 접속 결과, 확보하지 못한 것과 이유, 추출 품질 관찰 |
| `extracts/*.md` | 조항 원문 발췌(추출 텍스트 그대로, PDF 물리 쪽 표기) |
| `encoded/*.json` | 표본을 ClauseOccurrence·FieldAssertion·관계·규칙·PremiumObservation으로 넣은 결과(V1-b) |
| `GAP_REPORT.md` | 표현력 판정과 부족분 등록부(G01~G26), 설계 반영 내역, rule-0.2 후보 |
| `screen/*.json`, `SCREEN_BINDING.md` | 같은 자료를 내 설계 탭과 담보 상세 시트에 연결한 결과(V1-c) |
| `source_checks/*.json` | 보관본 재현 검사·현재 출처 변경 감지·다운로드 해시 대조 실행 기록 |
| `REVERIFY_87a19c5.md`, `REVERIFY_839ecdb.md` | 검사 보강의 재검증 결과와 그때 찾은 결함·수정·회귀 시험 |

실제 조항에서 만든 규칙은 `packages/fixtures/rules/real/`에 있고 `publication_state=fixture_only`로 고정된다.

## 검사

세 종류를 섞지 않는다.

| 검사 | 무엇을 보나 | 어디서 실행되나 |
|---|---|---|
| 내부 일관성 | 조항 인용이 지정한 문서·페이지의 인용 구간에 있는지, 필드 원문값·가격 금액이 근거 조항 구간 안에 있는지, 화면 금액이 선언한 출처와 같은지, 화면의 퍼센트·기간 숫자가 근거 문구에 있는지, 지급액 문구가 엔진 결과에서 생성된 것과 같은지, 가격 조건의 일치·불일치·원문 미기재 구분, 상태값·참조, 교차 검수 없는 `accepted` 금지. 해시는 적힌 문자열끼리만 비교 | CI 매 푸시 (`validation_check.py`, `--selftest` 38종, `cargo test --test real_clauses` 변조 5종 포함, Python 단위 시험) |
| 보관본 재현 | 보존한 원본의 바이트 SHA-256, 인용 페이지 재추출, 스캔본 OCR 재실행, `samples.csv`에 고정한 파생 명세(해시·원본 연결·출력 파일 존재와 해시·명세 밖 출력 없음), 명세 출력 전부의 재생성 바이트 일치. 기록이 깨지면 `derived_record_invalid`, 재생성이 다르면 `derived_mismatch`(둘 다 실패), 비교 못 한 것이 있으면 `derived_unverified`(미검증) | 수동: `tools/verify_sources.py reproduce`. CI 아님(판정 로직의 단위 시험만 CI) |
| 현재 출처 변경 감지 | 원 URL의 현재 문서가 마지막 관측과 같은가. 바뀌면 새 원본으로 보존하고 검수 대기 | 수동: `tools/verify_sources.py detect`. CI 아님. GitHub `sources` 워크플로는 main에 들어간 뒤에만 실행 가능(아직 한 번도 실행되지 않음) |

```bash
python3 tools/validation_check.py              # 내부 일관성
python3 tools/validation_check.py --selftest   # 변조마다 의도한 오류가 나는지
python3 -m unittest discover -s tools/tests    # 본문 해시 규칙, 보관 쓰기 충돌, 재현 판정 시험
cargo test --manifest-path packages/rules-engine/Cargo.toml --test real_clauses
python3 -I tools/verify_sources.py reproduce --raw file:///…/raw --derived file:///…/derived --ocr --report r.json
python3 -I tools/verify_sources.py detect --out NEW_DIR --raw file:///…/raw --archive-new --report d.json
```

원본은 공개 저장소에 넣지 않는다. 보관소는 S3 비공개 버킷이다(ADR-0015, `infra/s3/`). 2026-10-09 현재 S3 자격 증명이 없어, 원본은 같은 키 배치의 임시 보관본과 사용자에게 비공개로 전달한 묶음으로만 남아 있다. `samples.csv`의 `cache_path`는 캐시 기준 상대 경로이고, 보관소 키는 `sha256`에서 정해진다.

동적 HTML은 받을 때마다 세션 ID 등으로 바이트가 달라진다. 받은 바이트는 매번 새 원본으로 보존한다. `content_sha256`(규칙 `content_hash_rule` = `html-visible-text-v1`)은 변경 감지의 보조 지표이고, 같아도 결과는 `bytes_changed_content_same`이지 바이트 일치가 아니다.

검사 기록 `source_checks/` (2026-10-09):

| 파일 | 검사 | 결과 |
|---|---|---|
| `2026-10-09_reproduce_local_archive_ocr.json` | 보관본 재현(임시 보관본, 파생 v2, OCR 29쪽 재실행) | reproduced 8, derived_unverified 6, derived_mismatch 0. 원본 해시·인용 위치는 14건 모두 맞음. 미검증은 재생성 도구가 저장소에 없는 파생물 때문([REVERIFY_839ecdb.md](REVERIFY_839ecdb.md)) |
| `2026-10-09_reproduce_s3_emulator.json` | 보관본 재현(S3 에뮬레이터 사본, OCR 미실행) | reproduced 8, derived_unverified 5, ocr_not_rerun 1 |
| `2026-10-09_archive_download_verify_s3_emulator.json` | 에뮬레이터에서 다시 받아 SHA-256 대조 | 14/14 바이트 일치 |
| `2026-10-09_archive_download_verify_bundle.json` | 비공개 전달 묶음을 풀어 SHA-256 대조 | 14/14 바이트 일치 |
| `2026-10-09_detect_current_sources.json` | 현재 출처 변경 감지(11:07Z) | unchanged_bytes 13, bytes_changed_content_same 1(KB 간병인 지원비용: 세션 ID·서버 표시만 다름) |

실제 AWS S3에 올리고 다시 받아 대조한 기록은 아직 없다.
