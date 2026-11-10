# Audit 5 — samples.csv SHA-256 형식 재검증

대상: `audit5-samples-sha256-format-check`.
연결: BLUEPRINT Q7·L1·I6·M1, 09 제품 목적 대응표 P02·P03.

## 판정과 변경

보고된 형식 검사 누락은 기준 코드에서 이미 Audit 4로 해결되어 있다.
[기존 수정 기록](2026-11-03_samples_csv_validation.md)대로
`validation_check.check`는 `derived_manifest_sha256` 검사 옆에서 각 표본의
`sha256`을 공통 `source_metadata.check_sha256`으로 검사한다.
64자리 ASCII 16진수만 허용하며 대소문자를 보존한다. 빈 값·누락·다른 타입·
공백·유니코드 유사 문자·경로 구분자를 거부한다.
`source_archive.object_key`도 같은 검사를 실행하므로 `verify_sources.materialize`를
직접 호출해도 저장소 조회와 해시 이름의 파일 쓰기에 도달하기 전에 실패한다.

이번 작업은 기존 동작을 유지하면서 검사 목적을 코드 주석에 명시하고 회귀 증거를
보강했다. 실제 CSV 진입점의 반복 시험에서 발생한 파일 미닫힘 경고도
`validation_check.load`의 문맥 관리자로 해결했다.

## 회귀와 변이 검증

[`test_samples_csv_validation.py`](../../../tools/tests/test_samples_csv_validation.py)에
세 시험을 추가하고 기존 잘못된 해시 목록을 확장했다.

- 정확히 64자인 상대·절대·역슬래시 경로, 64자리 뒤 개행, 비ASCII 문자와
  문자열이 아닌 값을 거부한다. 올바른 대소문자 16진수는 계속 허용한다.
- 기존 14개 표본의 각 행을 하나씩 변조한다. 연결된 인코딩 문서의 해시도 같은 값으로
  바꿔 문자열 일치 검사를 만족시켜도 해당 표본의 형식 오류가 정확히 발생한다.
- 임시 `samples.csv`를 실제로 로딩하여 `main()`의 실패 반환값 1과 필드 오류를
  확인한다. 누락 열·빈 셀·따옴표로 감싼 개행도 검사하며 정상 값은 0을 반환한다.
- `object_key` 직접 호출과 fetch·verify·materialize 경로가 잘못된 해시를 거부한다.
  모의 저장소의 `get`·`exists`·`list` 호출은 없고 출력 디렉터리는 비어 있다.

[`check_hash_mutations.py`](../../../tools/evidence/audit5-samples-sha256-format-check/check_hash_mutations.py)는
행별 SHA-256 검사를 제거한 변이와 공통 검사를 길이 64 확인으로만 바꾼 변이를
메모리에서 적용한다. 첫 변이는 선택한 세 메타데이터 시험 모두가,
두 번째는 직접 키 생성·저장소 진입점까지 포함한 다섯 시험 모두가 검출해야 성공한다.
디스크의 운영 코드는 변경하지 않는다.

## 실행 증거와 한계

2026-11-10 이 작업 트리에서 실행한 명령·결과는
[증거 안내](../../../tools/evidence/audit5-samples-sha256-format-check/README.md)에 기록한다.
시험은 임시 CSV·합성 데이터·모의 저장소와 기존 로컬 회귀 도구를 사용한다.
이 증거는 표본 메타데이터와 보관 도구 경계의 로컬 검증이며 실제 공시 확보율·
R2 관측 대조·소비자 화면·P02·P03 전체·첫 출시 완료 증거를 대체하지 않는다.
