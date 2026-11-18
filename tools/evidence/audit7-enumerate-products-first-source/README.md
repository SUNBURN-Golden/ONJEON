# Audit 7 첫 공개 목록 관측 실행 기록

## 공개 조회

2026-11-18 12:23:50–13:17:34 UTC에 수동 1회 실행했다. 설정은 crawler 네트워크 허용, 프로젝트 연락처를 포함한 고정 User-Agent, 호스트 요청 간격 5초 이상, 동시 실행 1, HTTP 시도 최대 2회, 출처당 일일 요청 상한 50, 응답 한도 8 MiB, 범위당 최대 7쪽이었다.

```sh
ONJEON_CRAWLER_ALLOW_NETWORK=1 python3 -B tools/enumerate_products.py --config crawler.json --snapshot first-source-run.json --max-pages 7
```

조회 범위 54개에서 목록 쪽 69개를 계획·처리했고 robots 확인과 실패를 포함해 전송 호출은 39회였다. 성공한 목록만 원시 응답 SHA-256과 바이트 수를 갖는다. 구조 검증에 실패한 HTTP 응답에는 해당 실패 근거가 남는다. 공시 목록의 파생 메타데이터와 응답 해시는 [스냅샷](../../../data/registry/product_discovery.json)에 있다.

```text
0724fd6aaed2338ba0ba61fa68161ba71846cd344b2adacc1a934ac81c85863a  data/registry/product_discovery.json
{"expected_documents": 11938, "scopes": {"blocked": 37, "complete": 10, "failed": 6, "partial": 1}, "source_products": 5213}
```

회차 결과에서 추적한 문서 후보의 원문이나 R2는 조회하지 않았다. 회사·협회별 공백과 범위는 [Audit 7 원장 기록](../../../docs/blueprint/audits/2026-11-18_enumerate_products_first_source.md)을 따른다.

## 로컬 검증

전체 프로젝트 시험과 원장 일치 검사 결과는 [verification.log](verification.log)에 있다. 검사는 네트워크나 R2 토큰 없이 실행했다.
