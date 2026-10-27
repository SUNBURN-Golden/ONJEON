# Audit 2 — HTML 링크·onclick 다운로드 대상의 콘텐츠 해시 보존

대상: `audit2-content-hash-onclick-links`, `tools/html_content_hash.py`.
연결: Blueprint A1·Q7·L1·I6(원본 변경 관측 기반)·M1, 09 제품 목적 대응표 P03.

## 발견과 수정

v2의 링크 정규식은 따옴표로 감싼 속성 하나만 읽었다. `<a href=/old.pdf>` 또는 `<a href="#" onclick="download('old.pdf')">`에서 `old.pdf`만 바꾸면 콘텐츠 해시가 같아 `detect`가 `bytes_changed_content_same`으로 보고했다. 이는 링크 문서 파일명 변경을 감지한다는 모듈 계약과 어긋났다.

v3는 표준 라이브러리 `HTMLParser`로 `a href`·`iframe src`·`embed src`·`object data`·`form action`을 읽는다. 대소문자·속성 따옴표 유무를 처리하고, 따옴표 안의 `<`·`>`에 잘리지 않으며, `data-href`나 다른 속성 값 안의 `href=`를 링크로 오인하지 않는다. `onclick`은 요소 종류에 관계없이 전체 핸들러를 별도 신호로 남긴다. JavaScript를 실행하거나 문자열이 파일명인지 추정하지 않아 계산식·문서 식별자 변경도 보존한다. 이 보수적 정책 때문에 핸들러 내부의 세션 값·코드 변경도 콘텐츠 변경이 될 수 있다.

주석·script·style은 계속 제외한다. 제목의 호스트별 노드 표식, 링크의 세션 인수 제거와 호스트별 제한은 유지한다. 속성과 텍스트의 HTML 엔티티는 한 번만 해제한다. 해시 규칙을 `html-visible-text-v3`으로 올렸으며, `verify_sources.py`는 이름이 다른 v1·v2 기준선과 비교하지 않고 바이트가 다르면 `changed`로 보고한다. 과거 원본·관측·기준선은 변경하지 않았다. 비공개 원본을 사용한 기준선 재계산은 이 로컬 수정의 범위 밖이다.

## 회귀 증거

- [`test_html_content_hash.py`](../../../tools/tests/test_html_content_hash.py): 다섯 링크 속성 × 세 가지 따옴표 형식, 대문자 속성, 링크·버튼·입력·표 셀·div의 핸들러, 직접 파일명·URL 인수·계산식 변경, 엔티티로 감싼 인수, `<`·`>`가 있는 속성, 가짜 속성 제외, 엔티티 1회 해제, 주석·script·style 제외, 세션·제목·가격·조건 회귀를 검사한다.
- [`test_verify_sources.py`](../../../tools/tests/test_verify_sources.py): 따옴표 없는 링크와 링크·버튼의 `onclick` 파일명 변경이 실제 `cmd_detect` 보고서에서 `changed`인지 검사한다. 세션 값만의 변경은 `bytes_changed_content_same`이며 v1·v2 기준선은 비교하지 않는다. 다운로드는 모의 응답이고 보고서는 임시 로컬 파일이다.
- [수정 전 로그](../../../tools/evidence/audit2-content-hash-onclick-links/before.log): 새 콘텐츠 해시 시험을 v2 구현에 실행하여 23개 시험 중 하위 사례를 포함한 실패 35건·건너뜀 2건을 확인했다. 다운로드 대상 누락 외에 v3 버전 기대와 파서 경계 회귀도 포함한다.
- [v2·v3 판정 대조](../../../tools/evidence/audit2-content-hash-onclick-links/target-comparison.json): 작업 시작 시 `HEAD`의 v2 모듈과 수정한 v3 모듈을 같은 `cmd_detect`에 넣고 합성 입력 4쌍을 대조했다. 따옴표 없는 링크·링크 핸들러·버튼 핸들러의 파일명 변경 3쌍은 v2의 `bytes_changed_content_same`에서 v3의 `changed`로 바뀌고, 링크 세션만 바꾼 대조군은 두 규칙 모두 `bytes_changed_content_same`이다.

## 실행 결과

이 작업 트리에서 합성 HTML·모의 다운로드·임시 로컬 파일로 실행했다. 실제 공시 요청·R2 접근·자격 증명을 사용하지 않았다.

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p test_html_content_hash.py -v` | 23개 실행, 21개 통과·2개 건너뜀, 종료 코드 0 | [콘텐츠 해시 로그](../../../tools/evidence/audit2-content-hash-onclick-links/hash-tests.log) |
| `python3 -m unittest discover -s tools/tests -p test_verify_sources.py -v` | 36개 실행, 33개 통과·3개 건너뜀, 종료 코드 0 | [변경 감지 로그](../../../tools/evidence/audit2-content-hash-onclick-links/detect-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 990개 실행, 984개 통과·6개 건너뜀, 종료 코드 0 | [Python 전체 로그](../../../tools/evidence/audit2-content-hash-onclick-links/python-tests.log) |
| `cargo test --all --locked` | Rust 447개 통과·1개 무시, 내장 Python 39개·129개 통과, 종료 코드 0 | [Rust 전체 로그](../../../tools/evidence/audit2-content-hash-onclick-links/rust-tests.log) |
| 온톨로지 실행기 빌드·`ontology_check.py` | 빌드와 전체 검사 종료 코드 0 | [온톨로지 로그](../../../tools/evidence/audit2-content-hash-onclick-links/ontology-check.log) |
| 어휘·검증 자료·검증기 selftest·Blueprint 현황·제품 목적 연결·설계 명세·`git diff --check` | 모두 종료 코드 0 | [일관성 검사 로그](../../../tools/evidence/audit2-content-hash-onclick-links/consistency-checks.log) |

첫 전체 Python 실행은 온톨로지 실행 파일이 예상 경로에 없어 기존 시험 2개가 오류로 끝났다([초기 로그](../../../tools/evidence/audit2-content-hash-onclick-links/python-tests-initial.log)). `cargo build --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir docs/blueprint/proposals/온톨로지/검증/runner/target --locked`로 이 작업 트리 안에 실행기를 빌드한 뒤 전체 990개를 재실행하여 통과했다.

전체 Python 시험의 건너뜀 6개는 비공개 원본 보관소가 필요한 기존 시험 5개와 설치된 botocore가 이미 조건부 PUT을 지원하여 해당하지 않는 구버전 시험 1개다. 신규 회귀는 모두 실행했다. 이 증거는 변경 감지 도구의 회귀 검증이며, 실제 공시 확보율·R2 관측 목록 대조·변경 후 영향 재처리·화면·출시 완료 증거나 P03 전체의 완료를 대신하지 않는다.
