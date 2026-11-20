# Audit 7 — 실제 실행기 회귀·정적 검사 CI

`audit7-ci-runner-verify-tests`의 기준 커밋은 `c13cc28`이다. 기존 CI는
`tools/tests`를 탐색하고 `CredentialLeaseFencing` 10개를 따로 실행했다.
`runner_verify` 전체 모음의 실제 어댑터 시나리오와 자체 정적 검사는 빠져 있었다.

별도 `runner-verify` 워크플로는 코드 PR과 `main`·`claude/**` 푸시에서
`tools/daemon/**`(공용 `Ports` 포함), `daemon_rules.json`, `tasks.json`,
`docs/vm_check/**` 또는 자체 파일이 바뀌면 실행된다. Ubuntu 작업에서 아래 명령을
실행하며 `StaticChecks.test_all_static_checks_pass`가 `all_static()`의 일곱 검사를
호출한다. 권한은 `contents: read`이며 SHA 고정·checkout 자격 증명 비보존을
기존 CI의 검사에 포함했다. [워크플로](../../../.github/workflows/runner-verify.yml) ·
[워크플로 회귀 시험](../../../tools/tests/test_runner_verify_workflow.py).

```sh
python3 -m unittest discover -s tools/daemon/runner_verify/tests -v
```

| 로컬 재현 | 관측 결과 |
|---|---|
| 현재 작업 트리에서 워크플로의 `run`을 추출해 벤더 CLI가 없는 `PATH`로 실행 | 80개 통과, R1~R22와 `test_all_static_checks_pass` 포함 |
| 임시 복사본에서 `Ports` 생성자에 필수 키워드를 추가하고 모의 조립 코드만 갱신 | T-OP-00 모의 dry run 통과. 워크플로 명령은 실제 조립의 필수 인자 누락 `TypeError`로 종료 코드 1 |
| 임시 복사본에서 `standin_builders.json`의 `fixture_only`를 `false`로 변경 | 워크플로 명령은 `fixtures_marked()`가 보고한 표시 위반으로 종료 코드 1 |

워크플로 회귀 55개가 통과했다. 프로젝트 Python 모음은 1,755개 중 6개를
건너뛰고 실패 없이 끝났다. Rust 작업 공간은 537개 통과·1개 ignored였으며,
시나리오 API와 온톨로지 실행기는 각각 4개가 통과했다. Rust 형식·Clippy와
§11 색인·수치 검사 및 09 작업·시험 ID 대응 검사도 통과했다.

로컬 실행 기록이다. GitHub Actions에서의 실행 결과는 아직 없다.
이 기록은 T-OP-08 축 5 개발 도구 검증에 해당한다. 제품 출시 판정은
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 완료 증거를 따른다.
