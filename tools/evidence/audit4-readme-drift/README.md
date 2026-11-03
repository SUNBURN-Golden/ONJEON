# Audit 4: 루트 README의 ADR·문서 위계 정합성

검증일: 2026-11-04. 기준 커밋: `d6e348930af399079e3b76e28e32e47a81ca940c` + 이 노드의 미커밋 변경.

- 시작 시 ADR 목록은 이미 0001~0019였다. 기존 `DecisionsRow.test_every_adr_number_is_listed`가 `docs/decisions/ADR-*.md`와 양방향 대조하므로 목록을 다시 바꾸지 않았다.
- 남아 있던 “불변 원칙 → 제2부 → 제3부 → 제1부”와 제3부 §56 예외 문장을 [BLUEPRINT §0.1 문서 위계](../../../docs/BLUEPRINT.md#01-문서-위계) 링크로 교체했다. 근거는 [결정 원장 §2](../../../docs/blueprint/DECISIONS.md#2-충돌-해소표)의 과거 문서 우선순위 정정이다. 위계를 README에 중복 정의하지 않는다.
- [회귀 시험](../../tests/test_readme_index.py)의 `DocumentHierarchy` 두 시험은 §0.1 링크·대상 절의 존재와 옛 우선순위·예외 문구의 부재를 검사한다. 기존 CI의 Python 전체 발견 명령에 포함된다.

| 증거 | 직접 실행한 명령·결과 |
|---|---|
| [수정 전](before-tests.log) | 새 회귀 추가 후 README 수정 전 `python3 -m unittest tools.tests.test_readme_index -v`: 11개 중 위계 시험 2개 실패, 종료 1. ADR 대조는 통과 |
| [수정 후](readme-tests.log) | 같은 명령: 11개 통과, 종료 0 |
| [변이 검사](mutation-tests.log) | `unittest.mock.patch.object`로 시험 모듈의 `README` 문자열만 변경: ADR 행을 0011 뒤에서 자르면 기존 ADR 시험 실패, 감사 당시 우선순위 복원 시 새 시험 2개 실패, 현행 링크를 유지한 채 옛 문구를 추가해도 금지 시험 실패. 예상 실패 수·오류 없음·문자열 복원을 assert했고 종료 0. 실제 README 파일은 변경하지 않음 |
| [결정 색인](blueprint-status.log) | `python3 -I tools/blueprint_status.py`: 37개 ADR/DEC 정합, 종료 0 |
| [Python 전체](python-tests.log) | `python3 -m unittest discover -s tools/tests -v`: 1,363개 실행, 실패·오류 0, skip 6, 종료 0 |
| [Rust 전체](rust-tests.log) | `cargo test --all --locked --offline`: 문서 시험 포함 495개 통과, 실패 0, ignored 1, 종료 0 |

Python skip 6개는 원본 보관 경로 미설정 2개, 로컬 보관소·pdftotext가 필요한 재현 시험 3개, 설치된 botocore가 조건부 쓰기를 지원해 해당하지 않는 구버전 거부 시험 1개다. Rust ignored 1개는 기존 `regenerate_declared_abox_fixture` 재생성 시험이다. README 회귀에는 skip이 없다. `git diff --check`와 이 증거 문서의 로컬 링크 존재 검사도 통과했다.

이 증거는 README 문서 정합성 finding의 해결을 입증한다. [09_제품목적_대응표](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md)의 P01~P19 실제 수집·트윈·소비자 화면·첫 출시 완료 증거를 대신하지 않는다. 보호 경로 변경·커밋·푸시·GitHub 호출은 하지 않았다.
