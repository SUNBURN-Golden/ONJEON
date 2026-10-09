# 실문서 표본 확보 기록 (설계 검증용)

작성 2026-10-09 (수집 04:22~04:44Z). 목적: FieldAssertion·PremiumObservation·규칙 DSL이 실제 약관·요약서·공시의 조항(면책·감액·제외·별표·특약 종속·갱신·한도·가격 조건)을 표현할 수 있는지 검증하기 위한 **표본**이다. 서비스 범위(전 보험사·전 상품·전 특약)를 줄이는 결정이 아니다.

- 표본 목록: `samples.csv` (14개 파일, 표본 ID 14개. 협회 작성기준 팝업은 `klia_pub_cancer_criteria`)
- 조항 발췌: `extracts/<sample_id>.md` (모든 인용은 추출 텍스트에서 앵커 정규식으로 잘라 그대로 붙였다 — 앵커를 못 찾으면 실패하도록 만든 스크립트로 생성)
- 원본 파일: scratchpad `samples/<sample_id>/` (저장소에는 넣지 않음). 수집 로그 `samples/fetch_log.tsv`

## 1. 환경과 도구

| 항목 | 내용 |
|---|---|
| 요청 | `curl -sS -m 60~120`, 일반 브라우저 User-Agent, 같은 호스트 요청 사이 ≥1초. TLS 검증 해제·차단 우회 없음 |
| PDF 텍스트 | poppler `pdftotext` (`-layout` / 기본 읽기순서), `pdfinfo`, `pdffonts`, `pdfimages` |
| 보조 추출 | `pip install pdfplumber pypdf` (pdfplumber 0.11.10) |
| OCR | `apt-get install tesseract-ocr tesseract-ocr-kor` → tesseract 5.3.4, `-l kor --psm 3`, `pdftoppm -r 300 -gray` |
| 안전 | 내려받은 파일은 표본별 새 디렉터리, 스크립트는 별도 디렉터리, Python은 `-I`로 실행·경로는 인자로 전달 |
| 주의 | `file` 명령의 PDF 쪽수 보고가 틀린 경우가 있었다(별표15: `file`은 2쪽, `pdfinfo`는 492쪽). 쪽수는 `pdfinfo` 기준으로 기록 |

## 2. 접속 확인 결과 (2026-10-09 04:22~04:44Z)

| 호스트 | 결과 | 비고 |
|---|---|---|
| www.kyobo.com | 200 | 공시실 HTML + JSON API(POST) + 파일 다운로드 엔드포인트. 주 수집원 |
| www.kbinsure.co.kr | 200 | EUC-KR 서버 렌더링 HTML, form POST, `CG802030003.ec?fileNm=` 다운로드 |
| pub.insure.or.kr | HTTPS 간헐 `Connection reset by peer`(curl 35) | 재시도로 HTTPS 200 수신. HTTP는 200이었지만 사용하지 않음 |
| www.law.go.kr | HTTPS 간헐 reset (5회 중 4회 실패한 구간도 있음) | 재시도로 본문·별표 PDF 수신 |
| www.samsunglife.com | 200 (3.6KB 셸) | Vue SPA. `app.*.js`(2.4MB)에 공시 API 경로가 없고 지연 로딩 청크에 있는 것으로 보여 이번에는 추적하지 않음 |
| www.meritzfire.com | 200 (637B 셸) | `/common/index.js?<timestamp>`를 document.write로 로드하는 JS 셸. 추적하지 않음(손보 표본은 KB로 대체) |
| www.klia.or.kr, www.fss.or.kr, fine.fss.or.kr | 200 | 표본에는 직접 쓰지 않음 |
| knia.or.kr | 302 → `/main` | 상위 페이지는 응답. 이번에 탐색하지 않음 |
| kpub.knia.or.kr | 간헐: `/`는 69바이트 JS 리다이렉트, `/main.do`는 reset, `carProductInf.do`는 200 | 손보협회 비교공시 — 이번 표본에 쓰지 않음 |
| data.go.kr | 상위 페이지 200 | 탐색하지 않음(지시상 차단 목록이었으나 이 시각엔 응답) |
| www.samsungfire.com | 상위 페이지 200 | 탐색하지 않음(지시상 차단 목록이었으나 이 시각엔 응답) |
| www.dbins.co.kr | `CONNECT tunnel failed, response 502` | 차단 |
| www.hanwhalife.com | `unsafe legacy renegotiation disabled` (OpenSSL) | TLS 레거시 재협상 — 우회하지 않음 |

→ "차단" 목록 일부가 이 시각에 상위 페이지를 응답했다. 소스별 상태는 시점에 따라 바뀌므로 SourceRegistry에 `last_attempt`/`last_success`를 분리하는 계약(DATA_PIPELINE_CONTRACT §2)이 실제로 필요하다.

## 3. 수집 경로 (재현용)

**교보생명 상품공시실** — `https://www.kyobo.com/dgt/web/product-official/all-product/search` 페이지의 JS가 호출하는 API:
- 목록: `POST /dtc/product-official/find-allProductSearch` (JSON: `dgtPdtAtrDvCd:"M"`, `dgtPdtAtrMclCd:"PAMS04"`(보장성), `dgtPdtAtrSmclCd:"99"`, `saleYn:"Y"|"N"`, `pagePerSize` …) → 상품별 `a1`(상품요약서)·`a2`(약관)·`a3`(사업방법서) 파일명, `saleStDt`, `preNnnn`(1999년 이전 여부)
- 다운로드: `GET /file/ajax/download?fName=/dtc/pdf/mm/<파일명>` (파일명 앞 base64 조각 + 원래 파일명)
- 보장성 판매중 123건, 판매중지 383건(그중 `preNnnn=Y` 13건)을 목록으로 확인. 상세(판매기간별 이력) API `find-allProductSearchDetail`은 존재 확인만 함.

**KB손해보험 공시실** — `CG802030001.ec`(상품목록(약관)) form POST(`search_gubun=b` 운전자보험, `search_onsale_yn=Y`) → `CG802030002.ec`(bojongNo=25465) 상세 표: 판매기간 2행(2026-09-01~09-13 / 2026-09-14~), 각 행에 약관·사업방법서·상품요약서 → `CG802030003.ec?fileNm=25465_2_{1,2,3}.pdf`. 간병인 지원비용은 `CG802130001.ec`(정적 HTML).

**생명보험협회 공시실** — `/compareDis/prodCompare/assurance/listNew.do?search_prodGroup=024400010004`(암보험) 서버 렌더링 표 + `informationPopup.do`(작성기준). 엑셀 다운로드(`excelDownloadNew.do`)·비교 팝업은 시도하지 않음.

**법제처** — `행정규칙/보험업감독업무시행세칙` → iframe `admRulInfoP.do?admRulSeq=2200000108939` → 본문 `POST admRulLsInfoR.do`(별표 링크 포함) → `flDownload.do?flSeq=168885301`([별표 15] PDF; HWP는 flSeq=168884315).

## 4. 구조별 시도와 결과

| # | 구조 | 확보 표본 | 결과 |
|---|---|---|---|
| 1 | 정액 진단(면책·감액·소액암·별표 KCD) | kyobo_cancer_terms, kyobo_cancer_summary, kyobo_1995_cancer_scanned, (klia) | 확보. 90일 면책(계약일 포함 90일 다음날), 1년 미만 50%, 소액암 8급부 별도 금액, 별표2 KCD 제9차 코드표. 1995년 상품은 '3개월' 면책·ICD-9식 숫자 코드 |
| 2 | 실손(표준약관·자기부담·급여/비급여·비례보상·한도) | fss_std_terms_byl15, kyobo_silson_terms, kyobo_silson_summary | 확보. 표준약관(별표15)과 상품 약관(교보 5세대)을 둘 다 확보해 조문 번호·값 차이를 대조 |
| 3 | 수술비/입원일당 | kyobo_cancer_terms(NEW플러스수술특약: 1~5종 %, 수술분류표, 동시수술), kyobo_1995(입원급여금 3일 초과·120일), klia(암직접치료 입원 120일 한도 요약) | 수술은 확보. 일반 질병입원일당 약관 원문은 별도로 확보하지 않음(간병인지원 상해입원일당Ⅲ 조문으로 일당 구조는 확인) |
| 4 | 간병 | kyobo_care_summary(간병인사용 일당·체증형·장기요양 1~5등급), kb_driver_terms(간병인지원 상해입원일당Ⅲ), kb_caregiver_cost_html | 확보. 단 교보 간병 약관 원문은 미수집(요약서만) |
| 5 | 사망(종신, 재해 vs 질병) | kyobo_wholelife_summary, kyobo_wholelife_terms | 확보. 기간(제1/제2보험기간) × 원인 분기, 자살 2년 예외의 급부 재라우팅, 재해분류표 |
| 6 | 운전자 실손형 비용 | kb_driver_terms, kb_driver_summary | 확보. 벌금(1사고 2,000만원·비례분담), 변호사선임비용(심급별 500만원·자기부담 50%·계산 예시표). 일상생활배상책임 약관 원문은 발췌하지 않음(요약서 갱신 주석만) |
| 7 | 특약 종속·갱신 | kyobo_cancer_terms(제18조 소멸 종속, 제22조/제16~17조 갱신), kyobo_silson_terms(1년 갱신+5년 변경주기), kb_driver_summary(의무부가·【갱신계약】), kyobo_cancer_summary(특약별 20/10/5년) | 확보 |
| 8 | 가격 | kyobo_cancer_summary(남/여 1점 예시), kyobo_care_summary, kyobo_wholelife_summary, kb_driver_summary, klia_pub_cancer_compare(HTML 비교공시), kyobo_silson_summary(가격지수만) | 부분 확보. **나이×성별×납입기간 보험료 격자표(보험료표)는 찾지 못함** — 요약서는 40세 1점 예시뿐 |

형식 커버: text_pdf(일반·HWP 변환·2단 조판·Word 변환), scanned_pdf(1995 인쇄약관), html(협회 비교공시·KB 공시 표), 쪽을 넘는 표(요약서 p.118→119, 별표2 p.79→80, 실손 <표1> p.21→22, 요약서 보험종류 표 p.7→9). xlsx는 시도하지 않음(협회 엑셀 다운로드 존재만 확인).

## 5. 확보하지 못한 것과 이유

- **보험료표(나이×성별×기간 격자)**: 교보 상품요약서·KB 상품요약서에는 대표 1점 예시만 있다. 교보 '가격공시실'(`/dgt/web/dtp/sub-main`)과 사업방법서(a3)는 열어보지 않았다. KB '보험가격공시'(`CG803000001.ec`)는 자동차보험 '보험료계산' 링크 목록(`.ecs` 계산기)이라 공개 표가 아님 — 개인 입력 기반 조회는 범위 밖.
- **손해보험협회 비교공시(kpub.knia.or.kr)**: 간헐 reset. 이번 표본에서 제외.
- **삼성생명·메리츠화재 문서**: JS 셸 구조라 API 추적 비용이 커서 교보·KB로 대체(차단은 아님).
- **교보 간병 상품 약관 원문**: 요약서만 수집. 요약서가 인용한 '약관 제8조' 등은 미확인.
- **일반 질병입원일당 약관**, **일상생활배상책임 약관 조문**: 발췌하지 않음.
- **표준약관 별표15의 질병·상해 표준약관 부분**(p.142~): 이번엔 실손 부분만 발췌.

## 6. 추출 품질 관찰 (설계에 영향)

1. **추출기 하나로 안 된다.** 별표15(HWP 변환)는 poppler에서 글자 순서가 뒤섞이고 pdfplumber에서 정상. KB 약관(HWP 2단)은 poppler `-layout`이 단을 섞고, 기본 모드는 단 순서는 맞지만 표가 셀 단위로 풀리며, pdfplumber는 단을 섞는다. → 문서·쪽별 추출 전략과 추출기 버전이 ClauseOccurrence의 일부여야 한다(계약 §3과 일치).
2. **항 번호 소실**: KB 약관의 ①②③이 모두 같은 사설영역 문자 U+F000으로 추출(3,623회). 조항 경로를 순서 세기로 추정해야 함 → clause_path에 `inferred` 표시 필요.
3. **표**: layout 텍스트에서 다열 표는 셀이 줄 단위로 교차(별표1 지급기준표, 실손 <표1>, 수술분류표, 체증형 일당표). 실손 <표1>의 'max(1만원, 20%, 본인부담률)'은 텍스트만으로 복원 불가 → 좌표 기반 셀 복원 전에는 hold.
4. **분수식**(다수보험 비례분담)은 어느 추출기에서도 분자·분모 구조가 사라진다.
5. **OCR**: 한글 본문은 대체로 맞지만 원문자(①→`0)`/`(1)`), 괄호(`)`→`|`), 숫자 공백(`233.1`→`233. 1`), '1회'→`1희`, 영문 병기 전체가 깨짐. 원문 인쇄 오기('지접목적')도 있어 OCR 교정과 원문 오기를 구별해야 한다. 100dpi 시각 판독은 오히려 틀렸다(300dpi로 확인).
6. **쪽번호**: 물리 쪽과 인쇄 쪽이 문서·구간마다 다르게 어긋난다(+0~+6), 별표15는 목차 자체가 1쪽 틀림.
7. **HTML도 해석이 필요**: 협회 목록은 '나이' 열이 HTML 주석으로 숨겨져 조건이 다른 문서(작성기준 팝업)에 있고, KB 간병인 지원비용 표는 10열씩 접힌 2단 머리글.

## 7. 데이터 구조 검증에 바로 쓸 관찰 (근거는 각 extracts 파일)

- 같은 판매본의 상품요약서(KCD 제8차)와 약관(제9차)이 다르다 → 문서별 FieldAssertion + `conflicting`.
- 대기기간 단위: 90일(현행) vs 3개월(1995) — 일·월 단위를 정규화로 합치면 안 됨. 기산 규칙('그 날을 포함하여 … 다음날')도 필드로.
- 질병 코드 체계: KCD 제9차(C00-C14, D47.1…) vs ICD-9식 숫자(230~239) → `code_system`+`edition`+`as_of(진단 시점)` 필요. 약관 스스로 '진단 시점 KCD로 판단, 이후 개정으로 재판단 안 함' 규칙을 둔다.
- 감액 조건이 원인에 따라 갈림(간병인사용: 1년 미만 & 비재해만 50%), 기산점이 '최초계약'(갱신 무시)인 경우가 있다.
- 면책 예외가 '다른 급부로 지급'을 지정(종신 제8조: 2년 후 자살 → 질병사망보험금) → 규칙 결과가 2값이 아니라 급부 재라우팅.
- 동시 수술 max 규칙, 신체부위 동치류, 심급별 합산·균등 배분, 1일=24시간/8시간 미만 규칙, 입원 1일 평균 병실료 등 집계 연산이 필요.
- 금액 표현: 비율형(수술 1~5종 %)과 예시 금액형(소액암 '1,000만원 기준 200만원')이 혼재.
- 한도 값이 약관 밖에 있다: KB 간병인지원비용 = '회사가 정한 비용' → 공시 HTML의 가입일(갱신일)×경과기간 표. 시간 가변 파라미터 노드가 증거 사슬에 필요.
- 표준약관 vs 상품: 표준 '5천만원 이내 회사가 정한 금액 중 계약자 선택'(상한) vs 상품 '5천만원'(확정) — 표준약관 값은 상한/허용범위로 저장.
- 비례분담·다수보험은 개인 가입내역 없이는 `undetermined`.
- 가격: 조건이 표 밖(소제목의 성별, 괄호 안 월납보험료, 다른 문서의 작성기준)에 있다. 손보 예시는 상해급수·운전형태·담보 묶음(8개)·이율 시나리오 3종·천원 미만 절사가 조건. 협회 목록 값(50,790원)은 상품요약서 예시(100세만기)와 일치하지만 협회 작성기준은 80세만기 → `condition_mismatch` 후보. 협회 작성기준 표 자체에 오기로 보이는 값(간병/치매 보험기간 '90년', 납입기간 '20세')이 있다.
- 채널 변형: 협회 목록에 `교보통합암보험 (무배당)`과 `교보통합암보험 [D](무배당)`이 같은 보험료로 별도 행 → 상품 버전 식별에 채널 차원.
