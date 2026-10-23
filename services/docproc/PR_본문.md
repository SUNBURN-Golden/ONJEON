## 목적과 설계 연결

- 과제 ID: T-DT-02, fix round 4. 기존 설계 구현이며 정책·범위 변경 없음.
- A1·A2, Q1·Q2·Q7, L2, I6·I13, M2. 요구 ID: R04(원본 해시 연결), R05(불확실 구조 보류), R08(근거의 인용·쪽·좌표 검증).
- 소비자는 후보 정보의 원본 쪽과 좌표까지 추적할 수 있다. 미확인 후보는 모두 hold/extraction_uncertain이다.
- 근거: DATA_PIPELINE_CONTRACT §3, 구현 계약 §1.1/§6.1, 어휘 축 doc_role(packages/schemas/vocabulary.json), 온톨로지 _fingerprint_rule fp-0.1, tools/verify_sources.py의 쪽별 재추출. ADR-0001·0006의 기존 경계 안에서 구현했다.

## 변경 내용

- 차단 지적(P1): 구획·조항 ID와 doc_role 입출력에 한국어 화면 표기(보통약관 등)를 넣어 공용 evidence_ref 문법(doc_role은 소문자 snake_case)·SegmentRef/ClauseRef 스키마·Rust 파서가 모두 거부했고, 정식 코드 terms는 추출기가 거부했다. 후속 근거 사슬에 연결되지 않는 결함이었다.
- 수정: 입력·출력·ID 모두 어휘 축 doc_role 코드를 쓴다. 허용 집합은 02 §1.1 DocumentSegment의 여섯 역할에 대응하는 terms, rider_terms, annex, summary, disclosure_list, guide_page다. 화면 표기·폐기 표기(official_terms)·그 밖의 어휘 코드는 거부하고 대응표로 바꾸지 않는다. 구획 명세 검사(validate_specs)와 ID 생성(segment_id, clause_id)을 순수 함수로 분리해 Poppler 없이도 검사한다. 구획 명세 검사는 Poppler 호출 전에 실행한다.
- 회귀 시험(공용 스키마): packages/schemas/json/common.schema.json의 SegmentRef·ClauseRef·EvidenceRef 정규식과 json/vocabulary.schema.json의 doc_role enum을 읽어, 여섯 역할의 구획·조항 ID가 모두 합격하고 여섯 한국어 표기 ID가 모두 불합격함을 확인한다. 입력 거부 목록(한국어 표기, official_terms, price_example, 대소문자·공백 변형, 비문자열)과 ID가 필드를 되풀이하는지 검사하는 check_output의 변조 거부를 포함한다. 실제 추출 결과(native 24.02)도 같은 규칙으로 검사하며, 컨테이너 suite에는 스키마 파일을 읽기 전용으로 마운트한다. 라이브 하네스는 제품 CLI 출력을 호스트에서 다시 대조한다(SHARED CONTRACT 줄).
- 회귀 시험(공용 파서): 임시 디렉터리의 임시 크레이트가 packages/schemas(onjeon-contracts)를 경로 의존성으로 받아 onjeon_contracts::evidence_ref::validate와 DocRole enum을 호출한다. 역할마다 구획 1건·조항 2건의 ID가 합격·왕복·종류 일치하고, 한국어 표기 ID·범위 밖 쪽의 조항 ID·official_terms가 거부됨을 확인한다. cargo가 필요하며 test_sandbox.sh는 기본으로 필수(DOCPROC_REQUIRE_RUST_PARSER=1)다. packages/schemas는 수정하지 않았다.
- 변경은 services/docproc/**뿐이다. 화면·가격·규칙·개인정보·출시 기능의 변화는 없다. 원문·자격 정보·실제 상품 데이터는 넣지 않았다.

## 검증과 한계

- 대상 checkout SHA: 4c319684c28d1c1622347ecc30c579a276df6cc3. 이 수정은 해당 SHA 위의 미커밋 작업 트리다. 검증 대상 파일은 evidence/source-sha256.txt로 고정하고 명령·종료 코드·전체 로그는 evidence/validation.txt 및 연결된 로그에 기록한다. 현재 checkout 자체가 수정 내용을 포함한다고 주장하지 않는다.
- 작성 참여 역할·실행 경로: 감독 프로세스가 연 터미널 CLI의 단일 작성 에이전트가 구현·시험·자체 점검을 수행했다. 작업 트리 /workspace/onjeon-run/wt/T-DT-02. 모델 식별자 원문은 기록하지 않는다. 커밋·푸시·GitHub 호출 없음.
- 독립 리뷰: 제공된 차단 리뷰(대상 4c31968)를 수정 근거로 사용했다. 수정 후의 서로 다른 작성 계열 독립 리뷰는 감독 프로세스가 커밋 후 최종 대상 SHA에 고정해야 한다. 자체 점검을 독립 승인으로 세지 않는다.
- 필수 시험: `cd services/docproc && python3 -m pytest -q`, `bash services/docproc/test_sandbox.sh`(라이브 포함). 별도로 DOCPROC_SANDBOX_REQUIRE_LIVE=1 실행, unittest(Rust 파서 대조 필수), 직접 컨테이너 시험, cargo test --workspace, 누출·스켈레톤 검사도 실행한다. 실제 결과는 검증 로그가 기준이다.
- native 24.02 컨테이너 시험은 합성 PDF만 검증한다. 호스트 25.03은 추출 시험을 명시적으로 건너뛰며 수락 증거가 아니다. 컨테이너에서는 DOCPROC_REQUIRE_PINNED=1로 버전 불일치·추출 건너뛰기·스키마 파일 부재를 허용하지 않는다.
- 컨테이너 시험 이미지에는 cargo가 없어 Rust 파서 대조 시험 1건은 그 안에서 건너뛴다. 호스트 실행(unittest·pytest·test_sandbox.sh 1단계)이 그 증거다. 이 대조는 ID와 코드의 모양 검사이며, 역할별 허용 근거(basis·cross_check)와 realizes 판단은 릴리스 빌더·DB 제약의 몫이다(02 §6.1).
- PDF에는 보편적인 바이트 단위 원문 공백 표현이 없다. 인용의 정확성은 좌표 crop의 Poppler layout 출력에 대한 일치다(quote_basis=poppler-layout-region). 표·각주·계층·OCR 복원은 미지원이며 구조의 빈 값은 미분류를 뜻한다. 실제 원문 정확도·사용자 검증·출시 승인을 주장하지 않는다.
- CI 연결은 수정 금지 경로 .github/workflows/**가 필요하므로 이 과제에서 바꾸지 않았다. 로컬 필수 live 실행의 증거를 첨부한다.

## 확인

- [x] BLUEPRINT·PRINCIPLES를 읽었고 범위·개인정보·추천 기준 변경을 숨기지 않았다.
- [x] doc_role 코드 전환과 불확실성 보류를 기록했다. 규칙·가격·라벨의 의미 변경 없음. 어휘 정본은 수정하지 않았다.
- [x] 합성 시험 통과를 실제 상품 정확도나 출시 승인으로 표현하지 않았다.
- [x] 비밀값·모델 식별자 원문·원문 발췌 없이 허용 경로 안에서만 수정했다.
- [ ] 요구사항 추적표 갱신과 최종 SHA 독립 리뷰는 감독 프로세스 담당이다. 추적표는 수정 금지 경로다.
