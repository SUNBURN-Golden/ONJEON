# Audit 7 첫 공개 목록 관측 실행 기록

## 수정 2차 공개 조회

2026-11-19 02:31:34–2026-11-19 07:23:29 (KST) 사이의 관측이다. 프로젝트 연락처를 포함한 고정 User-Agent, 호스트당 요청 간격 5초 이상, 동시 실행 1, 페이지 요청 시도 최대 3회, 출처당 일일 요청 상한 400, 응답 한도 8 MiB를 사용했다. 목록 응답 소켓 제한 시간은 120초, 조회 범위당 페이지 상한은 500이다. [수동 설정](crawler.json).

```sh
ONJEON_CRAWLER_ALLOW_NETWORK=1 python3 -B tools/enumerate_products.py \
  --config tools/evidence/audit7-enumerate-products-first-source/crawler.json \
  --snapshot target/audit7-product-discovery.json --max-pages 500
```

54개 범위의 381개 페이지 기록에는 목록 조회와 robots 결과를 포함한 전송 시도 350회가 있다. 읽기가 끝난 HTTP 200 목록 응답과 robots.txt 응답은 해시와 크기를 기록한다. 협회와 보험사별 목록 종료·접근 공백은 감사 기록과 수락 범위 결정을 따른다. [감사 기록](../../../docs/blueprint/audits/2026-11-18_enumerate_products_first_source.md), [수락 범위 결정](../../../docs/decisions/audit7-enumerate-products-first-source.md).

흥국화재 판매중지 장기 목록의 첫 실행은 192쪽의 HTTP 200 응답 본문을 읽던 중 중단됐다. 첫 재개에서는 오래된 다운로드 참조의 형식을 검증하지 못해 멈췄다. 지원하지 않는 참조는 문서 역할을 유지하고 참조 미확정으로 표시하도록 보완했다. 최종 재개는 앞선 요청을 일일 상한에 반영하고 같은 요청 간격을 적용했다. 1쪽과 191쪽의 정규화 상품·문서 키와 출처 행 수를 대조한 뒤 192~225쪽을 읽었고, 재조회한 각 쪽에서 마지막 쪽 번호 225를 확인했다.

스냅샷은 1~191쪽의 최초 성공 기록과 192~225쪽의 성공 기록을 연결한다. 최초 읽기 실패와 최종 비교용 재조회에서 기록한 전송 시도 4회는 위 스냅샷 집계와 별도다. 에이스아메리칸 판매중지 응답은 2,948,310바이트를 읽었다. [복구 관측](continuation.jsonl).

```text
5cc477cc28944cad77ea766c9303ee82430997799ee43f74d2450619345c88cd  data/registry/product_discovery.json
{"expected_documents": 29469, "scopes": {"blocked": 37, "complete": 13, "failed": 4}, "source_products": 11222}
```

공시 목록의 파생 메타데이터와 해시는 스냅샷에 있다. 이번 관측에서 읽은 데이터는 공개 목록이며 모든 문서 후보의 원문 확보 상태는 `unqueried`다. [스냅샷](../../../data/registry/product_discovery.json).

## 로컬 검증

프로젝트 시험과 원장 일치 검사는 로컬에서 실행했다. [검증 기록](verification.log).

수정 3차(2026-11-19 KST)는 소스 변경 없는 환경 복구다. 감독자 재실행의 `onjeon-api-types` 시험 10개 실패는 삭제된 다른 작업 트리(`audit7-registry-supervisory-crosscheck-overdue`)의 절대 경로가 공유 cargo 대상 디렉터리 시험 바이너리에 컴파일 시점 박제된 것이 원인이다. 2차의 작업 트리 전용 대상 디렉터리 검증은 감독자가 쓰는 공유 대상을 고치지 못했다. 이번에는 동시 빌드가 없는 것을 확인한 뒤 공유 대상에서 워크스페이스 8개 패키지를 `cargo clean -p`로 정리하고 이 작업 트리에서 다시 빌드했다. 재빌드 바이너리는 이 작업 트리 경로를 박제하며 실패했던 10개 시험이 모두 통과한다. 전체 재실행: Rust 536 통과(1 무시)·Python 1,732 통과(6 건너뜀)·보조 스위트 4+4·스냅샷 `--check` 29,469행 일치. [검증 기록](verification.log).
