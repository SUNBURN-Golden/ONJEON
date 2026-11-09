# Audit 5 — 보관소 제공자 분류와 에뮬레이터 예외 제한

대상: `audit5-archive-provider-classification`, `tools/source_archive.py::provider_of`.
연결: Blueprint A1·Q7·L1·I6·M1, 09 제품 목적 대응표 P02·P03, ADR-0017.

## 판정과 변경

작업 시작 시 R2 호스트의 DNS 끝 점 제거와 소문자 변환은 이미 구현돼 있었다.
끝 점이 있는 R2의 작업 파일 요구·자격 증명 선택·요청 계량도 기존 시험이 검사했다.
하지만 그 외 명시적 엔드포인트를 모두 `emulator`로 분류하여 명시적 AWS 주소나
임의 원격 저장소에 예산 세션 없이 접근할 수 있었다.

에뮬레이터 예외를 HTTP(S)의 `localhost`·`127.0.0.1` 호스트로 한정했다.
호스트 대소문자·끝 점 정규화는 유지하고, HTTPS R2는 기존 예산·계량 경로를 따른다.
그 밖의 명시적 주소(명시적 AWS 포함)와 파싱 불가능한 주소는 제공자 분류에서
`SystemExit`로 거부한다. 오류 문구에 입력 주소를 넣지 않는다.
엔드포인트 생략 시 AWS 선택과 작업 파일 요구는 유지한다.
명령행 도움말과 모듈 설명에도 허용 범위를 명시했다.

## 검증

[`test_store_provider.py`](../../../tools/tests/test_store_provider.py)는 다음을 검사한다.

- 기본 AWS, HTTPS R2, 끝 점·대소문자·관할 호스트 변형의 R2 분류와 HTTP R2 거부.
- 로컬 허용 호스트의 HTTP(S)·끝 점·대소문자 변형 허용. 유사 로컬 이름·다른 IP·
  AWS 전역/리전/버킷 주소·유사 R2·경로/쿼리 속 R2 문자열·잘못된 URL은 거부.
- 명시적 인수와 `ONJEON_S3_ENDPOINT` 모두에서 원격 주소를 거부하고
  `boto3.client`를 호출하지 않음. 예산 세션 유무·원장 클라이언트 여부도 교차 검사.
- 로컬 에뮬레이터는 예산 없이 클라이언트 생성 가능. 기본 AWS와 끝 점 R2는
  예산 없이 클라이언트를 생성하지 않음. 끝 점 R2의 계량기 부착·허용 외 요청의
  전송 전 거부는 기존 `test_r2_budget.py`를 다시 실행해 확인.

[변이 검사](../../../tools/evidence/audit5-archive-provider-classification/check_provider_mutation.py)는
마지막 거부 분기만 메모리에서 `return "emulator"`로 되돌린다. 원격 주소·유사 R2·
클라이언트 생성 경계의 회귀 시험 세 개 모두 이를 검출해야 성공한다.
실제 AWS·R2 접근이나 보관소 변경 없이 합성 자격 증명·모의 클라이언트·Stubber를 사용한다.

명령과 실제 결과는 [검증 기록](../../../tools/evidence/audit5-archive-provider-classification/README.md)에 있다.
이 증거는 비용 통제 우회 차단의 로컬 회귀 증거다. P02·P03의 실제 공시 확보율·
R2 관측 목록 대조·소비자 화면·첫 출시 완료를 뜻하지 않는다.
