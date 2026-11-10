# audit5-daemon-secret-scan-patterns 실행 증거

2026-11-10. [수정 기록](../../../docs/blueprint/audits/2026-11-10_daemon_secret_scan_patterns.md) ·
[회귀 시험](../../tests/test_daemon_secret_scan.py) ·
[T-OP-09 사전 검사](../../daemon/runner_verify/secret_scan_preflight.py).
기준 커밋 `a761843031d65a2ddd76e64fd1d9c0ec60d22592` 위 미커밋 변경이며,
[manifest.json](manifest.json)은 변경 소스·문서·시험·로그의 SHA-256을 기록한다.
모든 자격증명 모양은 반복 문자로 조립한 합성 값이며 실제 비밀값·API 키가 아니다.

| 증거 | 결과 |
|---|---|
| [before.log](before.log) | 수정 전 초기 회귀 7개 실행, 하위 사례 실패 118건, 오류 0, 종료 1 |
| [after.log](after.log) | 기존 회귀 7개와 사전 검사 회귀 10개(Fix round 1·2·3 포함): 17개 통과, 종료 0 |
| [모의 시나리오](../../daemon/reports/dry_run.log) | 검사 692건 통과, 필수 ID 33/33, 누락·미등록·중복 0, 종료 0 |
| [데몬 회귀](../../daemon/reports/unittest.log) | 289개 통과, 종료 0; 현재 소스 내용 해시 기록 |
| [runner-adapter-tests.log](runner-adapter-tests.log) | 실제 실행기 Adapters·StaticChecks 12개 통과, 종료 0 |
| [static-checks.log](static-checks.log) | 공용 코어 정적 검사 13/13 통과, 종료 0 |
| [runner-static-checks.log](runner-static-checks.log) | 실제 실행기 정적 검사 7/7·회귀 5개 통과 |
| [python-before-baseline-tests.log](python-before-baseline-tests.log) | 최초 전체 Python 1,434개 실행, 규칙 파일의 기존 전체 해시 고정 때문에 실패 1건, 기존 skip 6개 |
| [rules-scope-check.log](rules-scope-check.log), [baseline-regressions.log](baseline-regressions.log) | 탐지·제외·설명 이외 JSON은 HEAD와 동일; D-04 해시 픽스처 갱신 후 o13 회귀 11개 통과 |
| [python-tests.log](python-tests.log) | 최종 전체 Python 1,476개 실행, 실패·오류 0, 기존 skip 6개, 종료 0 |
| [rust-tests.log](rust-tests.log) | 워크스페이스 513개 통과, 기존 fixture 재생성 시험 1개 ignored, 종료 0 |
| [ontology-runner-tests.log](ontology-runner-tests.log) | 온톨로지 실행기 4개 통과, 종료 0 |
| [spec-check.log](spec-check.log) | 기계 검사 45/45·존재 검사 72/72 통과, 종료 0 |
| [vocabulary.log](vocabulary.log), [validation.log](validation.log), [validation-selftest.log](validation-selftest.log) | 어휘·검증 자료 일관성·변조 탐지 검사 통과, 종료 0 |
| [blueprint-status.log](blueprint-status.log), [blueprint-counts.log](blueprint-counts.log) | 결정 색인·등록 수 일치, 종료 0 |

초기 7개 시험에는 corpus가 시험 파일 안에 있었고, 구현 후 같은 corpus를 실행기 사전 검사 모듈로
옮겨 공유했다. `before.log`의 합성 문자열·행 번호는 이 초기 버전을 가리킨다.
이후 3개 시험은 현재 규칙 통과, 빈/누락/잘못된 패턴 차단, 읽기/JSON/구조 오류 차단을 검증했고,
Fix round 1에서 3개를 더해 corpus 라벨 25개 고정, digest 파일이 있는 인계 통과와 비밀 아님 경계의
유지, 빈 패턴·모두 일치 패턴 거부를 검증했다. Fix round 2는 bare 32/64자리 R2 키 3개를 양성
corpus로 옮기고(corpus 라벨 28개), bare 키 패턴이 빠진 규칙을 사전 검사가 거부하는 회귀를 더했다.
Fix round 3는 digest 예외를 digest 이름에 바로 대입된 값 하나로 좁히고, 혼합 JSON 음성/양성
경계(`bare-r2-key-mixed-with-digest`, corpus 라벨 29개)와 같은 파일의 digest+bare 키가 인계를
R-10으로 반송하며 커밋·푸시가 0건인지 검사하는 회귀를 더했다.
최종 전체 Python 실행은 이 17개를 모두 포함한다. 기존 skip 6개는 보관소 환경 미설정 2개,
로컬 보관소·pdftotext 필요 3개, 설치된 botocore가 조건부 쓰기를 지원해 해당하지 않는 구버전 시험 1개다.

재현(루트에서 Rust 1.98.1·잠긴 의존성 준비 후):

```sh
python3 -m unittest tools/tests/test_daemon_secret_scan.py -v
python3 -m unittest tools/tests/test_daemon_dry_run.py -v
python3 -m unittest tools.daemon.runner_verify.tests.test_runner_verify.Adapters tools.daemon.runner_verify.tests.test_runner_verify.StaticChecks -v
python3 -I tools/daemon/static_checks.py
python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all
python3 -m unittest discover -s tools/tests -v
cargo test --all --locked --offline
cargo test --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml
python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py
python3 -I tools/vocab_check.py
python3 -I tools/validation_check.py
python3 -I tools/validation_check.py --selftest
python3 -I tools/blueprint_status.py
python3 -I tools/blueprint_counts.py
```

실제 Git 제외 시험은 임시 인덱스·트리만 만들고 subprocess 명령을 init·add·write-tree·ls-files로
제한하며, 기본 인덱스는 전후 `ls-files -s`가 같은지 확인한다. 데몬 보존 시험은 메모리 모의 포트를
사용한다. CLI 실패 시험은 Ctx·시나리오 호출과 보고서 디렉터리 생성이 모두 없는지 확인한다.
Git 커밋·푸시·GitHub·실제 제공자 호출은 없으며, 커밋·푸시를 수행하는 T-OP-09 전체 시나리오는
실행하지 않았다.

자격 이름 없는 32/64자리 hex는 탐지한다. `checksum`·`sha256`·`content_hash`·`tree_hash` 같은
digest 이름에 바로 대입된 값만 일반 해시로 보고 제외하며, 같은 줄의 다른 필드에 있는 값은 탐지한다.
digest 이름과 값 사이에 다른 토큰이 끼어 있는 드문 배치나 이름 없는 일반 해시는 탐지될 수 있다. `R2_SECRET_ACCESS_KEY=<hex>`처럼 credential 이름이
붙은 값도 탐지한다. 패턴 기반 검사이므로 임의 형식 비밀값 전체의 탐지를 보장하지 않는다. 이 결과는 BLUEPRINT §9.5·09 §5의 개발 도구
증거이며 P01~P19나 첫 출시 완료 증거가 아니다.
