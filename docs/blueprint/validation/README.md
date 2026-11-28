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
| `REVERIFY_AUDIT1_STORAGE_DOCS.md` | BLUEPRINT의 R2 보존 완료·남은 조건·코드 목록 수정과 회귀 시험, 기존 R2 기록 대조 |
| `REVERIFY_AUDIT1_DEC_RECORDS.md` | BLUEPRINT §0.1의 DEC 결정 게이트 기록 정의와 결정 원장 §3의 세 기록·상태 등록, 회귀 시험과 프로젝트 검사 결과 |

실제 조항에서 만든 규칙은 `publication_state=fixture_only`로 고정된다. `encoded/*.json`의 `rules[].file`이 현행 규칙 위치를 가리킨다. 교보 암 주계약·종신 재해사망·질병사망의 개정 규칙은 `packages/rules-engine/tests/fixtures/real/`에 있고, 해당 규칙의 이전 판과 나머지 규칙은 `packages/fixtures/rules/real/`에 있다.

V1 종료의 담당·순서·필수 증거와 미재생성 6건 목록은 [Audit 2 V1 종료 결정](../../decisions/audit2-v1-gate-closure.md)을 따른다. 현재 관문은 미통과이며, 로컬 시험 통과와 DEC-D-02 기록만으로 재현·교차 검수 완료로 바꾸지 않는다.

## 검사

세 종류를 섞지 않는다.

| 검사 | 무엇을 보나 | 어디서 실행되나 |
|---|---|---|
| 내부 일관성 | 조항 인용이 지정한 문서·페이지의 인용 구간에 있는지, 필드 원문값·가격 금액이 근거 조항 구간 안에 있는지, 화면 금액이 선언한 출처와 같은지, 화면의 퍼센트·기간 숫자가 근거 문구에 있는지, 지급액 문구가 엔진 결과에서 생성된 것과 같은지, 가격 조건의 일치·불일치·원문 미기재 구분, 상태값·참조, 교차 검수 없는 `accepted` 금지. 표본 SHA-256의 64자리 16진수·HTTPS 출처 URL 형식을 검사하며 해시 일치는 적힌 문자열끼리만 비교 | CI 매 푸시 (`validation_check.py`, `--selftest` 40종, `cargo test --test real_clauses` 변조 6종 포함, Python 단위 시험) |
| 보관본 재현 | 보존한 원본의 바이트 SHA-256, 인용 페이지 재추출, 스캔본 OCR 재실행, `samples.csv`에 고정한 파생 명세(해시·원본 연결·출력 파일 존재와 해시·명세 밖 출력 없음), 명세 출력 전부의 재생성 바이트 일치. 기록이 깨지면 `derived_record_invalid`, 재생성이 다르면 `derived_mismatch`(둘 다 실패), 비교 못 한 것이 있으면 `derived_unverified`(미검증) | 수동: `tools/verify_sources.py reproduce`. CI 아님(판정 로직의 단위 시험만 CI) |
| 현재 출처 변경 감지 | 원 URL의 현재 문서가 마지막 관측과 같은가. 바뀌면 새 원본으로 보존하고 검수 대기 | 수동: `tools/verify_sources.py detect`. CI 아님. GitHub `sources` 워크플로 detect 작업(수동). main 첫 실행(2026-10-09, run 38005507041)은 추출기를 찾지 못해 출처를 받기 전에 멈췄다(`pip --user` 설치를 `python3 -I`가 보지 못함, venv로 고침). 받지 못한 출처가 하나라도 있으면 종료 코드 1이며, 출처별 결과를 작업 요약에 쓴다. 워크플로 성공은 모든 출처를 받았다는 뜻이다 |

```bash
python3 tools/validation_check.py              # 내부 일관성
python3 tools/validation_check.py --selftest   # 변조마다 의도한 오류가 나는지
python3 -m unittest discover -s tools/tests    # 본문 해시 규칙, 보관 쓰기 충돌, 재현 판정 시험
cargo test --manifest-path packages/rules-engine/Cargo.toml --test real_clauses
python3 -I tools/verify_sources.py reproduce --raw file:///…/raw --derived file:///…/derived --ocr --report r.json
ONJEON_CRAWLER_ALLOW_NETWORK=1 ONJEON_CRAWLER_CONTACT="$PUBLIC_CRAWLER_CONTACT" \
  python3 -I tools/verify_sources.py detect --out NEW_DIR --raw file:///…/raw --archive-new --report d.json
```

원본은 공개 저장소에 넣지 않는다. 보관소는 Cloudflare R2 비공개 버킷이다(ADR-0015·0016, `infra/r2/`). 2026-10-09 원본과 파생 v2를 R2에 보존하고 다시 받아 대조했다(아래 기록). 사용자에게 비공개로 전달한 묶음은 별도 사본이다. `samples.csv`의 `cache_path`는 캐시 기준 상대 경로이고, 보관소 키는 `sha256`에서 정해진다.

`pdfplumber`는 PDF 인용을 재추출하는 `reproduce`에만 필수다. `detect`는 PDF 바이트를 해시로 비교하므로 `pdfplumber` 없이 실행할 수 있으며 보고서의 해당 도구 버전은 `null`로 기록된다. 회귀 시험은 `tools/tests/test_verify_sources.py`의 `CliDependencies`에 있다. 공통 진입점의 `pdftotext` 필수 검사는 유지한다. [Audit 1 수정 검증 기록](REVERIFY_AUDIT1_DETECT_DEPENDENCY.md)에 실행 결과와 환경 제약을 적었다.

`detect`는 `ONJEON_CRAWLER_CONTACT`의 공개 이메일 또는 연락처 URL을 `ONJEON-SourceArchiver` User-Agent에 넣는다. 수동 `sources` 워크플로는 같은 이름의 저장소 변수에서 연락처를 받아 detect 단계에만 제공하며, 해당 단계에 `ONJEON_CRAWLER_ALLOW_NETWORK=1`을 설정한다. 로컬 실행에서도 위 예시의 `PUBLIC_CRAWLER_CONTACT`에 실제 공개 연락처를 지정한다.

[2026-10-10 조사](../../research/2026-10-10_source_survey/A_klia.md#6-접근-제한과-실패)의 전면 금지 기록에 따라 `pub.insure.or.kr` 표본 2건은 요청 없이 `fetch_failed`를 기록한다. 최신 robots 정책 확인은 등록된 나머지 HTTPS 출처에 적용한다. 문서 요청 전에 같은 출처의 `/robots.txt`를 같은 User-Agent로 확인하고 일치하는 그룹들의 규칙을 합쳐 판정한다. robots 조회에서 호스트를 보류하면 같은 실행의 이후 표본에도 적용한다. robots 429·503 보류는 응답 시점의 다음 UTC 자정과 유효한 `Retry-After` 중 더 늦은 시각까지 지속한다.

robots의 206 또는 `Content-Range`가 있는 다른 2xx, HTML 차단 페이지, 지원하지 않는 `Content-Type`·`Content-Encoding`이 붙은 2xx, 불완전한 헤더·본문은 `robots_unreachable`로 호스트를 보류한다. 성공 응답에 `Content-Type`이나 `Content-Encoding`이 있으면 각각 `text/plain`, `identity`를 요구한다.

문서에 대한 429 또는 `Retry-After`를 포함한 503 이후에는 같은 실행에서 해당 호스트의 robots와 문서 요청을 함께 보류한다. `Retry-After`의 미래 시각까지 보류하고, 사용할 수 있는 미래 시각이 없으면 다음 UTC 자정까지 보류한다.

문서와 `robots.txt` 요청은 리다이렉트를 따라가지 않는다. 보고서의 `requested_url`은 입력 URL이고, `final_url`과 `http_status`는 프래그먼트를 제외한 문서 응답 URL과 HTTP 상태다. 문서 응답 메타데이터가 없으면 두 값은 `null`이다. 변경 판정은 계속 `status`에 기록한다. 새 보관 관측에는 입력 URL·문서 응답 URL·HTTP 상태를 함께 남긴다.

출처별 120초 안에 robots 조회, 문서 다운로드와 연결 오류 재시도를 완료해야 한다. HTTP 200, MIME, PDF/HTML 시그니처를 확인하고, HTML의 앞 64 KiB에서 알려진 차단 페이지를 검사한다. 최종 응답에는 공용 전송 계층의 64 MiB 제한을 적용한다. 초과 길이를 선언하면 읽기 전에 거부하고, 실제 스트림이 상한을 넘으면 한 바이트를 더 읽어 초과를 판정한다. robots와 문서의 `Content-Length`가 반복되면 같은 숫자 값만 허용하며, 선언 길이와 다른 본문은 거부한다. 실패한 출처는 `fetch_failed`·종료 코드 1로 집계하고 캐시·원본·성공 관측을 쓰지 않는다. [Audit 8 수집 경계 검증](../audits/2026-11-28_detect_fetch_hardening.md).

### HTML 본문 해시

동적 HTML은 받을 때마다 세션 ID 등으로 바이트가 달라진다. 받은 바이트는 매번 새 원본으로 보존한다. `content_sha256`은 변경 감지의 보조 지표이고, 같아도 결과는 `bytes_changed_content_same`이지 바이트 일치가 아니다. 현재 규칙은 `html-visible-text-v3`다(`tools/html_content_hash.py`). 링크의 `sid`·`_t`·`_`·`ts`·`timestamp`는 사이트에 따라 문서 식별자일 수 있어 호스트별 목록(`HOST_VOLATILE_PARAMS`, 현재 KB손해보험의 `_t`)에서만 제거하고, `jsessionid`·`sessionid`·`phpsessid`는 모든 호스트에서 제거한다. KB의 목록이 실제 페이지의 변동 파라미터를 모두 덮는지는 비공개 원본으로 아직 확인하지 않았다.

v3는 HTML 파서로 따옴표 없는 링크 속성까지 읽고, 모든 요소의 `onclick` 전체를 보수적으로 보존한다. JavaScript 실행이나 파일명 추정 없이 다운로드 인수·계산식 변경을 감지하며, 핸들러 안의 세션 값·코드 변경도 `changed`가 될 수 있다. HTML 엔티티는 한 번 해제한다. v1·v2 기준선은 v3와 비교하지 않는다. [Audit 2 회귀·변경 감지 검증 증거](../audits/2026-10-27_content_hash_onclick_links.md).

`DATA_PIPELINE_CONTRACT` §3·§3.1의 v1 표기에는 [BLUEPRINT §4](../../BLUEPRINT.md#4-시스템-계층)의 v3 기준을 적용한다. 보호 문서라 이 작업에서 고치지 않은 `docs/data/DATA_PIPELINE_CONTRACT.md` 40·55행의 v1→v3 직접 정정은 `docs/data/` 편집 권한이 있는 경로의 남은 작업이며, 정정 전에는 설계도가 문서 위계(ADR-0011)로 우선한다. `source_checks/2026-10-09_detect_current_sources.json`과 ADR-0015의 v1은 당시 실행과 채택 기록이라 고치지 않는다. [원본 사본 제공 결정](../../decisions/audit7-pipeline-contract-hash-rule.md).

2026-11-20 확인 시 `samples.csv`의 HTML 표본 3건은 2026-10-09에 계산한 v1 기준값을 사용한다. 기준값을 갱신하기 전까지 바이트가 달라진 응답은 `changed`로 보고된다. 승인된 담당자가 지정 실행 환경에서 고정 키의 원본 3건을 읽어 로컬 보관 사본을 제공하면([결정](../../decisions/audit7-pipeline-contract-hash-rule.md)) 아래 명령으로 기준값을 갱신한다. 입력 디렉터리는 `objects/sha256/<aa>/<bb>/<sha256>` 구조를 사용한다. 도구는 원본의 바이트 SHA-256을 각 행과 대조하고 `content_sha256`·`content_hash_rule`을 함께 갱신한다. 원본이 없거나 해시가 다르면 CSV 갱신 전에 중단한다.

```bash
python3 -I tools/rebaseline_html_samples.py --raw-dir path/to/local/raw
```

### 검증 이력

문서 불일치 수정(Audit 1): `docs/BLUEPRINT.md` §11 "코드" 행(318행)을 2026-10-09 기준 단위·통합 테스트 39개 + 문서 시험(doctest) 3개로 나눠 적고, 재실행 근거인 `REVERIFY_87a19c5.md` §2에 연결했다. 두 커밋(87a19c5·839ecdb)의 `cargo test --workspace` 재실행 로그는 `docs/blueprint/validation/evidence/audit1_blueprint_test_count/`에 있다. `tools/tests/test_validation_test_counts.py`는 이제 합산값만 적은 행을 거부하며, 로그·REVERIFY·설계도의 39 + 3을 대조한다. [수정·검증 결과](REVERIFY_AUDIT1_BLUEPRINT_TEST_COUNT.md)에 회귀 시험과 재실행 결과를 적었다.

검사 기록 `source_checks/` (2026-10-09):

| 파일 | 검사 | 결과 |
|---|---|---|
| `2026-10-09_reproduce_local_archive_ocr.json` | 보관본 재현(임시 보관본, 파생 v2, OCR 29쪽 재실행) | reproduced 8, derived_unverified 6, derived_mismatch 0. 원본 해시·인용 위치는 14건 모두 맞음. 미검증은 재생성 도구가 저장소에 없는 파생물 때문([REVERIFY_839ecdb.md](REVERIFY_839ecdb.md)) |
| `2026-10-09_reproduce_s3_emulator.json` | 보관본 재현(S3 에뮬레이터 사본, OCR 미실행) | reproduced 8, derived_unverified 5, ocr_not_rerun 1 |
| `2026-10-09_archive_download_verify_s3_emulator.json` | 에뮬레이터에서 다시 받아 SHA-256 대조 | 14/14 바이트 일치 |
| `2026-10-09_archive_download_verify_bundle.json` | 비공개 전달 묶음을 풀어 SHA-256 대조 | 14/14 바이트 일치 |
| `2026-10-09_detect_current_sources.json` | 현재 출처 변경 감지(11:07Z) | unchanged_bytes 13, bytes_changed_content_same 1(KB 간병인 지원비용: 세션 ID·서버 표시만 다름) |

| `2026-10-09_r2_listing_raw.json` | R2 원본 버킷의 모든 키를 다시 받아 고정 목록과 대조(비용 한도 아래) | 58/58 바이트 일치 |
| `2026-10-09_r2_listing_derived_v2.json` | R2 파생 버킷 같은 대조 | 61/61 바이트 일치 |
| `2026-10-09_r2_verify_samples.json` | R2에서 표본 14건 원본 해시 대조 | 14/14 바이트 일치 |
| `2026-10-09_r2_reproduce_ocr.json` | R2 보관본 재현(OCR 29쪽 재실행, 고정 파생 명세 검증) | reproduced 8, derived_unverified 6, 불일치 0 |
| `2026-10-09_r2_budget_status.json` | 비용 한도 원장 상태(순번 10까지) | 작업 한도 안 |

R2 보존 절차와 차이는 `infra/r2/README.md`, 비용 한도는 `infra/r2/BUDGET.md`. 대조 기준은 Git에 고정한 키·해시 목록이다: `archive_listing_raw.json`(원본 16, 관측 42), `archive_listing_derived_v2.json`(파생 47, 파생 명세 14). 이 목록은 내용이 아니라 키와 SHA-256만 담는다.
