# Audit 7 초기 상품 목록 조회와 ExpectedDocument 후보

작업 `audit7-enumerate-products-first-source` · L0 · M3 · 09 P01/P02

## 수정 2차 실측 (2026-11-19 KST)

- 재검토의 수락 범위 조정 경로를 적용했다. 협회 두 곳과 확인된 보험사 공시 진입점 여덟 곳에서 허용된 목록은 끝까지 읽고, 접근이 되지 않은 범위는 최초 응답과 재개 조건을 남겼다. [수락 범위 결정](../../decisions/audit7-enumerate-products-first-source.md).
- 스냅샷의 54개 조회 범위 중 허용된 13개 목록을 종료까지 조회했다. 흥국화재 판매중지 장기 225쪽과 일반 95쪽, 에이스아메리칸 판매중지 2,972행을 포함한다. 흥국화재 장기는 192쪽의 본문 읽기가 실패해 1쪽과 191쪽의 정규화 행을 재확인한 뒤 192쪽부터 마지막 쪽까지 이어서 조회했다. [실행 증거](../../../tools/evidence/audit7-enumerate-products-first-source/README.md).
- 37개 범위가 차단됐고 4개 범위는 robots.txt 요청 중 TLS 연결이 종료됐다. KLIA 17개 범위와 DB손해보험 1개 범위는 robots.txt 규칙으로 차단됐고, KNIA 19개 범위는 robots.txt HTTP 403으로 보류했다. TLS 오류는 처브라이프생명, 교보라이프플래닛, 미쓰이스미토모 한국지점에서 발생했다. [기관 원장](../../../data/registry/README.md#초기-상품-목록-관측-2026-11-19-kst).
- 보험사 4곳의 상품·특약 관측행 11,222개와 ExpectedDocument 후보 29,469개를 기록했다. 약관 9,209, 특약 약관 2,413, 사업방법서 11,238, 요약서 6,605, 안내 4개다. 공개 참조가 있는 후보는 28,473개이고 참조 미확정은 996개다. 후보의 원문 확보 상태는 모두 `unqueried`다. [관측 스냅샷](../../../data/registry/product_discovery.json).
- 보험사 원장의 전체 목록 상태는 `failed` 7곳(후보 관측 4곳, TLS 오류 3곳), `blocked` 1곳, `unqueried` 45곳이다. 관측에 성공한 회사에는 조회한 범위의 종료와 전체 분모 미확정을 함께 남겼다. [기관 원장 CSV](../../../data/registry/insurers.csv).

## 검증 범위

`python3 tools/enumerate_products.py --check`는 조회 계획, 페이지·해시 형식, 문서 역할·행 연결, 허용된 요청과 회사 원장 일치를 검사한다. 회귀 시험은 20쪽 이상인 목록의 종료, 늦은 본문 오류의 제한된 재시도, 검증할 수 없는 과거 문서 참조의 처리, 완료 표시와 마지막 쪽 일치, robots 차단과 증거를 확인한다. 공개 페이지는 변동할 수 있으며 당시 응답은 해시와 파생 행으로 추적한다. 09 P01/P02의 전 대상 분모와 원문 보존·판 연결은 T-DT-04 실데이터 관문 O19를 따른다. [검증 기록](../../../tools/evidence/audit7-enumerate-products-first-source/verification.log).
