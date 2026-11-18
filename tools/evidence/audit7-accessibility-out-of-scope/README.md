# Audit 7 접근성 제외 수정 1차 검증

기준 HEAD `517c607`. [ADR-0021](../../../docs/decisions/ADR-0021-첫-출시-최소-접근성.md)은 가역적인 개발·검증 기준이며 소유자의 공식 교체 답은 대기 중이다.

현재 Flutter 골격에서 예시 진입·종료와 부분 상태의 일반 텍스트 대비를 검사한다. 360 px에서 글자 200%를 적용해 진입점과 배너 버튼, 네 탭의 라벨과 조작, 공통 상태 7종의 배치를 확인한다. 시맨틱 트리에서 각 탭의 이름·버튼 역할·선택 상태를 읽고 활성화 동작으로 화면을 전환한다. 첫 진입 화면의 제목과 안내·버튼 읽기 순서도 확인한다.

| 표시 | 수정 전 | 수정 후 | 조정 |
|---|---|---|---|
| 예시로 둘러보기 | 4.47:1 | 4.92:1 | 채움 버튼 글자를 흰색으로 변경 |
| 예시 끝내기 | 4.48:1 | 5.19:1 | 배너 버튼 글자에 기존 `tabSelected` 사용 |
| 확인 필요 | 4.14:1 | 5.62:1 | 상태 글자에 기존 `accentText` 사용 |

진입점·상태 버튼과 네 탭은 글자가 늘어날 때 높이를 확보한다. 새 위젯 시험 6개를 기준 HEAD의 모바일 코드에 실행해 세 대비 오류, 탭 활성화 누락, 제목 역할 누락, 확대 시 글자 잘림을 모두 재현했다. [기준 HEAD 실패 로그](baseline-flutter-tests.log).

BLUEPRINT·원장·09·작업 계약의 정합성은 [문서 회귀 시험](../../tests/test_audit7_accessibility.py)으로 검사한다. 제3부 §51.4와 디자인 상세 부록은 이 작업의 수정 허용 경로 밖에 있어 BLUEPRINT §7.3과 ADR-0021에 우선 적용 조항을 기록했다.

09 P19의 실제 소비자 화면·공개 웹 시험과 TalkBack·VoiceOver·웹 스크린 리더 실행, P18의 고령 참가자 U7 시험은 해당 작업의 출시 증거로 남아 있다.

## 실행 기록

Flutter 3.47.7, Dart 3.13.5, Rust 1.98.1. 최종 Cargo 시험은 이 작업 트리의 `target/audit7-cargo`에서 실행했다. 초기 Cargo 실행은 환경의 공유 빌드 디렉터리를 사용했다.

| 명령 | 결과 | 기록 |
|---|---|---|
| `flutter analyze --no-pub`, `flutter test --no-pub`, `dart run tool/krw_lint.dart` (apps/mobile) | 분석 이상 없음, 103개 시험 통과, 금액 산술 검사 통과 | [분석](flutter-analyze.log), [시험](flutter-tests.log), [린트](krw-lint.log) |
| `python3 -B -m unittest` 문서·제품 목적 집중 검사 | 100개 통과 | [집중 검사](document-tests.log) |
| `python3 -B -m unittest discover -s tools/tests` | 1,708개 실행, 실패 0, 건너뜀 6 | [Python 전체 시험](python-tests.log) |
| `cargo test --all --locked --offline --quiet` | 532개 통과, 1개 무시 | [Rust 시험](rust-tests.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4개 통과 | [온톨로지 실행기](ontology-runner-tests.log) |
| BLUEPRINT 색인·등록 수, 제품 목적과 변이 검사, 묶음 명세, 토큰 생성과 시험 | 색인 43개 대조, 기계 47/47·존재 72/72, 토큰 시험 5개 통과 | [계약 검사](contract-checks.log), [등록 수](blueprint-counts.log) |
| 노출·스켈레톤·어휘·검증 세트 검사, 실행기 임대 시험 | 검증 자료 변이 40개 검출, 임대 시험 10개 통과 | [정적 검사와 임대 시험](static-checks.log) |
| `python3 -I tools/ci/check_deps.py` | 기존 온톨로지 의존성 위반 3건, 기준 HEAD와 동일 | [기준 HEAD](baseline-deps.log), [수정 후](dependency-check.log) |
| `python3 -I tools/release_readiness/check.py --purpose … --registry … --evidence docs/release-readiness/evidence/` | 예상 종료 코드 1. P18·P19를 포함한 P행 19개와 기능 64개가 열림 | [출시 증거 판정](release-readiness.log) |
