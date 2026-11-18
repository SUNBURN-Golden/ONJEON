# Audit 7 — S0 선행 경로 병합 재검토

2026-11-18 KST. 기준 `70ed72f` (작업 시작 시점의 로컬 `origin/main`).

T-CT-01과 T-OP-01의 기존 병합을 유지한다. 로컬 `grokbot/onjeon-T-CT-01` 끝 `4349b8e`와 `grokbot/onjeon-T-OP-01` 끝 `7e9be36`은 각각 #102와 #101의 두 번째 부모이며 둘 다 기준 커밋의 조상이다. 후속 일곱 과제도 모두 병합되어 두 선행 브랜치의 미병합을 원인으로 한 차단은 해소됐다. T-OP-09(#98)는 두 과제보다 먼저 병합됐고 최종 감리 T-OP-08의 개발 도구 검증 기록에 해당한다.

## 로컬 병합 이력과 작업 계약 대조

표는 기준 브랜치의 병합 순서이며 선행 열은 [tasks.json](../proposals/설계검토_결과/tasks.json)의 `prereq_tasks`를 그대로 옮겼다. T-CT-02도 T-CT-05의 선행이어서 함께 대조했다.

| 과제 | 선행 과제 | 첫 부모 이력의 병합 SHA |
|---|---|---|
| T-OP-09 | T-OP-00 | `8d4c9d3` |
| T-OP-01 | 없음 | `631331f` |
| T-CT-01 | 없음 | `57f14e7` |
| T-CT-02 | 없음 | `5e06eb5` |
| T-CT-03 | T-CT-01 | `6855ad3` |
| T-CT-06 | T-CT-01 | `3ee000b` |
| T-CT-04 | T-CT-01 | `750d48d` |
| T-CT-05 | T-CT-01, T-CT-02 | `464ba25` |
| T-KN-01 | T-CT-01 | `fd05605` |
| T-KN-03 | T-CT-01 | `2621d66` |
| T-DT-01 | T-OP-01, T-CT-04 | `c915729` |

`git merge-base --is-ancestor <브랜치> 70ed72f`는 두 브랜치에서 종료 0이다. `git log --first-parent --merges 70ed72f`로 각 병합을 대조했다. [회귀 시험](../../../tools/tests/test_audit7_s0_critical_path.py)은 표와 작업 계약·문서 링크를 확인한다. 전체 Git 이력이 있으면 병합 커밋·선행 순서도 확인한다.

## 작업 수락 조건 재실행

| 과제·영역 | 명령 | 결과 |
|---|---|---|
| T-CT-01 생성물 | `ONJ_REQUIRE_TOOLCHAINS=1 bash packages/schemas/codegen/build_check.sh` | 생성물 30개 일치. Rust 1.98.1, TypeScript 5.9.3, Dart 3.13.5 빌드와 타입·픽스처 시험 통과 |
| T-CT-01 어휘·스키마 | `python3 tools/vocab_check.py`와 `python3 -m unittest discover -s packages/schemas/codegen/tests -v` | 정본 어휘 50축·271값 확인. enum 출처와 스키마 검증을 포함해 129개 통과 |
| T-CT-01 호환성 | `bash packages/schemas/codegen/check_compat.sh contracts-0.1.0` | 구조 비교와 이전 Rust 클라이언트 탐침이 필드 삭제 변이를 검출. 로컬 `contracts-*` 태그가 없어 실제 이전 릴리스 비교는 미실행 |
| T-CT-01 계약 크레이트 | `cargo test -p onjeon-contracts --locked --offline` | 55개 통과 |
| T-OP-01 로컬 기동 | `bash infra/compose/smoke.sh` | 정적 시험 33개와 `LIVE: PASSED`. 두 번 기동, 공개·개인 DB 인증과 네트워크 분리, 큐 읽기·쓰기, 개인 DB 로그, 객체 저장소 권한 16개 및 완전 정리 확인. [실행 로그 발췌](../../../tools/evidence/audit7-s0-critical-path-merge/compose-smoke.log) |
| T-CT-06 의존 검사 | `python3 -I tools/ci/check_deps.py`와 `python3 -m unittest discover -s tools/ci/tests -v` | 저장소 검사 위반 0, 회귀 시험 21개 통과 |
| Python 프로젝트 | `python3 -m unittest discover -s tools/tests -v` | 1,705개 실행, 실패 0, 기존 건너뜀 6개(보관 원본·로컬 재현물 또는 구버전 SDK 필요) |
| Rust 프로젝트 | `cargo test --all --locked --offline` | 536개 통과, 기존 무시 1개. 계약·API 타입·온톨로지·AI 게이트웨이·수집 보존 클라이언트 포함 |
| 독립 Rust 작업 공간 | `cargo test --locked --offline` (온톨로지 실행기) 및 `cargo test --manifest-path services/scenario-api/Cargo.toml --locked --offline --target-dir target/scenario-api` | 각각 4개 통과 |
| 설계 계약 | `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 47/47, 존재 검사 72/72 통과 |

## 재실행에서 발견한 결함과 수정

- 처음에는 Docker 미설치로 실제 기동 시험을 시작할 수 없었다. 이 작업 트리 안에 임시 Docker 29.9.1·Compose 5.6.0 환경을 준비하고, 공개 이미지 세 개를 내려받은 뒤 격리된 Linux 네트워크에서 합성 데이터로 실행했다. ShellCheck 0.10.0을 추가하자 일부 조건식과 보관된 구성요소 실험 스크립트에서 정적 시험이 실패했다. 현재 Compose 진입 스크립트에 ShellCheck를 적용하고 기동·격리·정리 시험의 분기를 명시했다. 개인 DB 로그 검색이 `grep` 오류를 통과로 세지 않도록 하고, 일치·불일치·잘못된 패턴의 세 경우를 회귀 시험에 넣었다.
- T-CT-06 의존 검사에서 온톨로지 골든 시험의 엔진 사용과 시나리오 API의 구역 누락으로 네 건이 보고됐다. 시나리오 API를 `api` 구역에 등록하고, 온톨로지·시나리오 API의 기존 개발 의존을 해당 시험 소스 경로에만 허용했다. 계약 패키지의 기존 개발 예외도 실제 시험 파일로 한정했다. 같은 의존을 서비스 의존이나 일반 소스에 넣으면 계속 실패하는지 검증했다.

## 재검토 1 — T-CT-01 태그 호환성 CI

[CI](../../../.github/workflows/ci.yml)는 태그와 전체 이력을 체크아웃하고 `ONJ_COMPAT_ALL_CLIENTS=1 bash packages/schemas/codegen/check_compat.sh --latest`를 실행한다. 검사는 HEAD의 앞선 조상에서 가장 높은 `contracts-*` 버전을 골라 그 커밋의 JSON Schema와 Rust·TypeScript·Dart 생성물을 꺼낸다. 구조 비교에 이어 새 JSON Schema에서 만든 문서를 태그의 Rust·Dart 코드로 역직렬화하고 태그의 TypeScript 타입에 대입해 확인한다. major 상향으로 선언한 깨지는 변경은 구조 비교에서 판정한다.

이 체크아웃의 이전 릴리스 태그는 0개다. CI 단계의 셸 본문을 로컬에서 실행해 도구 설치·체크섬 확인, 비교 대상 부재 메시지·필드 삭제 자체 시험, 합성 태그 회귀 시험을 확인했다. 합성 태그에서 선택 필드와 enum 값 추가는 세 언어 모두 통과했고, 태그에만 둔 역직렬화 키 또는 타입 결함은 각 언어에서 탐지했다. 최신 버전 선택, 얕은 체크아웃 거부, 누락된 생성물·도구의 설정 오류도 확인했다. [재검증 로그](../../../tools/evidence/audit7-s0-critical-path-merge/tagged-compat.log)

재검토에서는 계약 생성기 시험 137개와 세 언어 빌드, Python 프로젝트 시험 1,705개(기존 건너뜀 6개), Rust workspace 시험 536개(기존 무시 1개)를 확인했다. 독립 Cargo 작업 공간은 각각 4개, 의존 검사 회귀 시험은 21개가 통과했다. 병합 순서 회귀 시험 3개는 전체 Git 이력에서 통과했다. Compose는 이번 라운드에 정적 시험 33개를 재실행했으며 실제 기동은 위 표의 이전 실행이 증거다.

기존 작업별 구현 맥락은 [계약 패키지](../../../packages/schemas/README.md)와 [로컬 Compose](../../../infra/compose/README.md)에 있다. 개발 기반과 Git 이력의 증거다. V1 파생 재현·이종 검수·화면 관문과 M1의 I7·I12 전체 검증은 BLUEPRINT §9.2에 남아 있다. [09](../proposals/설계검토_결과/09_제품목적_대응표.md) 판정기를 현재 완료 등록부에 실행하면 P행 19개와 기능 64개 모두 open이며 종료 코드는 1이다.
