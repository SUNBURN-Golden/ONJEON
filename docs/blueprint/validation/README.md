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

```bash
python3 tools/validation_check.py                                  # 인용·해시·어휘·참조·부족분 ID
cargo test --manifest-path packages/rules-engine/Cargo.toml --test real_clauses   # 규칙 사례·배타성·단위·화면 수치
```

원본 파일은 저장소에 넣지 않았다. `samples.csv`의 URL과 sha256으로 다시 받아 대조한다. 내려받은 파일은 신뢰하지 않는 입력으로 다룬다.
