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

실제 조항에서 만든 규칙은 `packages/fixtures/rules/real/`에 있고 `publication_state=fixture_only`로 고정된다.

## 검사

두 종류를 구분한다.

| 검사 | 무엇을 보나 | 어디서 |
|---|---|---|
| 내부 일관성 | 인용이 지정한 문서·페이지의 인용 구간에 있는지, 필드 원문값·가격 금액이 근거 조항 구간 안에 있는지, 화면 금액이 선언한 출처와 같은지, 지급액 문구가 엔진 결과에서 생성된 것과 같은지, 상태값·참조. 해시는 적힌 문자열끼리만 비교 | CI(매 푸시) |
| 원본 재검증 | 원본 바이트 SHA-256, 인용 페이지 재추출 대조, 스캔본 OCR 재실행 | 수동: `tools/verify_sources.py`, GitHub `sources` 워크플로 |

```bash
python3 tools/validation_check.py              # 내부 일관성
python3 tools/validation_check.py --selftest   # 알려진 변조가 실패하는지
cargo test --manifest-path packages/rules-engine/Cargo.toml --test real_clauses
python3 -I tools/verify_sources.py --cache DIR --download [--ocr] --report out.json   # 원본 재검증
```

원본 파일은 저장소에 넣지 않았다. `samples.csv`의 `cache_path`는 보관 위치 기준 상대 경로다. 보관소가 정해지기 전에는 기록된 URL에서 다시 받는다. 내려받은 파일은 신뢰하지 않는 입력이며 해시와 추출에만 쓴다.

동적 HTML 공시 페이지는 요청마다 세션 ID와 서버 표시가 바뀌어 바이트 해시가 매번 다르다. 바이트 해시는 보관 식별용으로 두고, 변경 감지는 스크립트·제목을 뺀 본문 해시(`content_sha256`)로 한다. 바이트만 다르고 본문이 같으면 `content_verified`로 따로 보고한다.

재검증 기록: `source_checks/2026-10-09_archived_copy.json`(세션 임시 보관본, 14/14, OCR 재실행 포함), `source_checks/2026-10-09_refetch.json`(원 URL 재다운로드, 12 일치·1 본문 일치·1 OCR 미재실행).
