# Audit 8 M1 공유 계약 소유권

기준 커밋 `93d0d0f`에서는 BLUEPRINT §5.1·§9.3의 RawAsset,
SourceObservation, ClauseOccurrence, CodeSet, ParameterTable에 대응하는
공유 스키마 파일과 명시적 소유 과제가 없었다. T-CT-01의 계약 골격은
병합되어 있고 T-DT-01·T-DT-02의 보관·복원 코드에는 자체 레코드가 있다.

S0의 T-CT-10에 다섯 스키마 파일, Rust·Dart·TypeScript 생성물, 계약 판과
두 잠금 파일 갱신, 객체별 수락 시험을 배정했다. 이 노드는 소유권과 작업
순서를 등록했다. 버전 상향에 필요한 루트 `Cargo.lock`은 이 노드의 수정
범위 밖이며, 스키마 구현과 왕복·거부 시험은 T-CT-10의 산출물이다.
[작업 계약](../proposals/설계검토_결과/tasks.json)

T-KN-05는 원본·관측·조항 스키마를 사용하므로 T-CT-10 병합을 기다린다.
T-KN-08은 같은 선행 경로를 통해 코드 집합과 파라미터 표 스키마를 받는다.
두 S1 관문과 최종 관문에서도 T-CT-10을 선행으로 추적할 수 있다.
09의 P02·P03·P05·P08에 이 과제를 연결했다. 진척 보고에서 67개 과제 중
병합 20개, 완료한 제품 목적 행은 0/19다.
[설계도](../../BLUEPRINT.md#92-마일스톤) · [제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)

## 검증 결과

이 작업 트리에는 전역 Rust 기본값이 없어 첫 시험 실행에서 `cargo`가 도구
체인을 고르지 못했다. README의 작업 트리 한정
`rustup override set --path "$PWD" 1.98.1`을 등록한 뒤 아래 명령을 다시
실행했고, 검사기 `test_cmd` 전체가 종료 코드 0으로 통과했다. TypeScript·Dart
검사는 로컬에 설치한 `tsc`·Dart SDK를 `TSC`·`PATH`로 지정해 실행했다.

| 실행 | 결과 |
|---|---|
| `python3 -m unittest tools.tests.test_m1_contract_ownership tools.tests.test_s1_prerequisites -v` | 9개 통과. 스키마 소유권 누락·중복 10개와 추출 선행 제거 1개를 메모리에서 각각 재현해 검출했다. [소유권 시험](../../../tools/tests/test_m1_contract_ownership.py) · [선행 시험](../../../tools/tests/test_s1_prerequisites.py) |
| `python3 -m unittest discover -s tools/tests -v` | 1,788개 중 1,782개 통과. 실제 보관 자료가 필요한 5개와 구형 botocore 전용 1개 건너뜀 |
| 실행기 검증 도구·CI 검사기 단위 시험 | 각각 81개, 21개 통과 |
| `cargo test --all --locked --offline` | 537개 통과, 픽스처 재생성 시험 1개 무시 |
| 시나리오 API·온톨로지 실행기 독립 Cargo 시험 | 각각 4개 통과. 온톨로지 검증기 통과 |
| `env ONJ_REQUIRE_TOOLCHAINS=1 bash packages/schemas/codegen/build_check.sh` | 기존 Rust·TypeScript·Dart 생성물 빌드와 픽스처 검증 통과 |
| 계약 호환 검사 `--latest` 및 `test_compat.py -k all_clients` | 이전 출시 태그 부재로 필드 삭제 자체 시험을 실행했다. 합성 태그를 사용한 3개 언어 호환 및 거부 시험 2개가 통과했다 |
| 작업 명세·제품 목적·부트스트랩 검사 | 기계 47/47, 존재 72/72 통과. 제품 목적 링크 검사 통과. 부트스트랩은 기존 경로 권고 6건 |
| 출시 진척 보고 및 증거 판정 `--purpose` | 진척 보고 0/19 완료. 증거 판정은 P행 19개 및 기능 64개를 열린 상태로 보고하고 종료 코드 1 반환 |
