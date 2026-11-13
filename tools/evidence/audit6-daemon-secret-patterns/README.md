# audit6-daemon-secret-patterns 실행 증거

2026-11-12 최초 기록 · 2026-11-13 재검증. [수정 기록](../../../docs/blueprint/audits/2026-11-12_daemon_secret_patterns.md) ·
[회귀 시험](../../tests/test_daemon_secret_scan.py)(`HistoryScan`, `RealGitScan`, 확장 corpus) ·
[실행기 어댑터](../../daemon/runner_verify/adapters.py)(`included_files` 무제한, `history_texts`).
기준 커밋 `ee9331b3660d033b2dcf09df1e5344c081815497` 위 미커밋 변경이며,
[manifest.json](manifest.json)은 변경 소스·문서·시험·로그의 SHA-256을 기록한다.

수정 3회차(2026-11-13): 감독자의 전체 Python 실행 실패(정적 검사 CLI 시험의
30초 초과)를 처리했다. 실패는 이번 패턴 변경과 무관한 기존 구조였다.
`all_static()`의 각 검사가 같은 소스를 다시 파싱해 한 실행에 24개 파일을
160번(파일당 최대 7번) 파싱했고, 8코어 부하 평균 45의 공유 기계에서
CLI 한 번이 30초 제한을 넘겼다. 기준 커밋 재현은
[static-before-round3.log](static-before-round3.log)다. 이제 한 실행은
소스당 한 번만 읽고 파싱하며(24번), 캐시는 실행 안에서만 켜졌다가 풀린다.
검사 함수 직접 호출은 항상 새로 읽으므로 오래된 내용을 줄 수 없고 판정은
캐시 전후가 같다. 새 회귀 3개가 파일당 1회 파싱·실행 간 결과 동일·캐시 해제·
직접 호출의 최신 읽기를 고정한다. [static-round3.log](static-round3.log)는
24번 파싱, CLI 단독 0.76~1.96초, 정적 13/13 통과다.

| 수정 3회차 증거 | 결과 |
|---|---|
| [static-before-round3.log](static-before-round3.log) | 기준 커밋에서 파일당 최대 7번·모두 160번 파싱 재현(속도 저하의 원인) |
| [static-round3.log](static-round3.log) | 24개 파일 24번 파싱, CLI 단독 0.76~1.96초, 정적 13/13 통과 |
| [focused-round3.log](focused-round3.log) | 비밀값 27개·정적 22개(새 캐시 회귀 3개 포함) 통과 |
| [python-round3.log](python-round3.log) | 전체 Python 1,607개/490.097초, 실패·오류 0·기존 skip 6개, 종료 0 |
| [runner-round3.log](runner-round3.log) | 실제 실행기 회귀 61개/544.580초 통과, 종료 0 |
| [dry-run-round3.log](dry-run-round3.log) | 모의 데몬 695개 검사·필수 ID 33/33 통과 |
| [spec-round3.log](spec-round3.log), [secrets-round3.log](secrets-round3.log) | 명세 기계 46/46·존재 72/72·추적 비밀 파일 검사 통과 |

Rust 소스·코드젠은 이번 회차에 바뀌지 않아 2회차 증거가 그대로 유효하다.
어휘·검증 자료·청사진 색인 검사도 입력이 바뀌지 않아 2회차 로그를 유지한다.
`reports/unittest.log`은 이번 전체 실행에서 데몬 네 모듈(모의 300·비밀값 27·
정적 22·필수 커버리지 7) 356개 결과를 발췌했고, `reports/dry_run.log`·
`검증/실행로그_dry_run.txt`와 머리말 해시는 현재 소스 해시로 다시 썼다.
`검증/실행로그_spec_check.txt`는 본문이 현재 실행 출력과 같아 그대로다.

수정 2회차(2026-11-13): 감독자의 900초 초과를 실패로 처리했다.
`python_codegen_suite_passes` 안에서 실제 Cargo를 실행하는
`CheckCompatScript`를 분리해 검사했다. 변경 전 단독 실행은
[codegen-before-round2.log](codegen-before-round2.log)의 129개/121.049초 통과로,
같은 900초 지연은 재현하지 못했다. 바깥 `--offline`이 자식 Cargo로 전달되지 않고
잠금 파일 없는 시험이 레지스트리를 조회할 수 있는 경로, 호출자의 빌드 경로 공유,
호환 검사 subprocess의 시간 제한 부재를 제거했다. 시험은 작업 트리 안의
`target/compat-probe`와 `CARGO_NET_OFFLINE=true`를 쓰며, 각 검사 120초 초과 시
셸·자식 빌드 그룹을 종료하고 출력과 함께 실패한다. 이 정리 경로는 새 회귀가 검사한다.
또한 `--manifest-path`로 임시 크레이트를 실행해 작업 트리의 rustup 재정의를 유지한다.
[codegen-round2.log](codegen-round2.log)는 환경에 Rust 전역 기본값이나
`RUSTUP_TOOLCHAIN`을 추가하지 않은 실행이며 130개/141.645초 통과했다
(새 작업 트리 내부 빌드 캐시 생성 포함). 속도 개선을 주장하는 결과는 아니다.

| 수정 2회차 증거 | 결과 |
|---|---|
| [focused-round2.log](focused-round2.log) | 비밀값·큰 파일·삭제된 이력 회귀 27개 통과 |
| [codegen-round2.log](codegen-round2.log) | 130개 통과; 잠금 파일 없는 오프라인 탐침·시간 초과 시 자식 종료 포함 |
| [rust-round2.log](rust-round2.log) | `timeout 900s cargo test --all --locked --offline`: 169.993초, 514개 통과·기존 ignored 1개, 종료 0. 포함된 Python codegen 130개/142.700초 통과 |
| [python-round2.log](python-round2.log) | 전체 Python 1,604개/518.966초 실행, 실패·오류 0·기존 skip 6개, 종료 0. 데몬 300개 결과를 `reports/unittest.log`에 발췌 |
| [runner-round2.log](runner-round2.log) | 실제 실행기 회귀 61개/486.660초 통과, 종료 0 |
| [fmt-round2.log](fmt-round2.log), [clippy-round2.log](clippy-round2.log) | fmt·Clippy `-D warnings` 통과 |
| [ontology-round2.log](ontology-round2.log) | 온톨로지 실행기 4개 통과 |
| [dry-run-round2.log](dry-run-round2.log) | 모의 데몬 695개 검사·필수 ID 33/33 통과 |
| [static-round2.log](static-round2.log), [spec-round2.log](spec-round2.log), [secrets-round2.log](secrets-round2.log) | 정적 13/13·명세 기계 46/46/존재 72/72·추적 비밀 파일 검사 통과 |

[python-before-evidence-refresh-round2.log](python-before-evidence-refresh-round2.log)는
이전 데몬 로그의 소스 해시가 현재 내용과 다름을 발견한 실행이다.
[python-before-delimiter-fix-round2.log](python-before-delimiter-fix-round2.log)는
로그 재작성 중 빠뜨린 `# output` 구분자의 비교 오류를 발견한 실행이다.
두 오류를 고친 뒤 위 `python-round2.log`로 전체 재실행했으며,
중단된 두 로그는 통과 증거로 세지 않는다. 아래 표의 이전 회차 기록은 과거 실행이다.

수정 2회차 재현(README의 도구 체인·의존성 준비 후 루트에서):

```sh
python3 -I -m unittest discover -s packages/schemas/codegen/tests -v
timeout 900s cargo test --all --locked --offline
python3 -m unittest discover -s tools/tests -v
python3 -m unittest tools.daemon.runner_verify.tests.test_runner_verify -v
```

| 증거 | 결과 |
|---|---|
| [before.log](before.log) | HEAD 규칙에서 corpus 6개 형식 미탐지(gho_·ghu_·ghr_·sk-ant-·자격 URL 둘), HEAD 어댑터가 2.5 MB 파일을 2,000,000바이트에서 잘라 꼬리 비밀 미탐지, `history_texts` 없음 — finding 재현 |
| [after.log](after.log) | 현재 규칙은 corpus 36개 전부 탐지·음성 경계 25개 전부 비탐지, `missing_cases` 0 |
| [history-binary-before.log](history-binary-before.log) | 기존 이력 어댑터에서 바이너리·`-diff` 파일을 추가 후 삭제하면 원문을 읽지 못함: 두 하위 사례 실패로 재현 |
| [focused.log](focused.log) | 비밀값 회귀 27개 통과(이력 스캔 5개·실제 Git 5개·corpus 포함), 종료 0 |
| [python-tests.log](python-tests.log) | 2026-11-13 전체 Python 1,600개 실행, 실패·오류 0, 기존 skip 6개, 종료 0 |
| [모의 시나리오](../../daemon/reports/dry_run.log) | 검사 695건 통과, 필수 ID 33/33, 종료 0 |
| [daemon-dry-run-recheck.log](daemon-dry-run-recheck.log) | 2026-11-13 모의 시나리오 재실행: 검사 695건 통과, 필수 ID 33/33, 종료 0 |
| [데몬 회귀](../../daemon/reports/unittest.log) | 수정 2회차 전체 실행에서 300개 통과 결과 발췌; 현재 소스 내용 해시 기록 |
| [runner-adapter-tests.log](runner-adapter-tests.log) | 실제 실행기 시험 61개 통과, 종료 0 |
| [static-checks.log](static-checks.log) | 공용 코어 정적 검사 13/13 통과, 종료 0 |
| [rules-scope-check.log](rules-scope-check.log) | `daemon_rules.json`의 HEAD 대비 차이가 `preserve_manifest.secret_patterns.{_note,patterns,scan}`뿐; `o13_unchanged_gates.json`은 그 파일 해시만 갱신 이유와 함께 다시 고정 |
| [rust-tests.log](rust-tests.log) | 2026-11-12 기존 기록: fmt·clippy 통과, 워크스페이스 515개 통과·기존 fixture 재생성 시험 1개 ignored, 종료 0 |
| [rust-tests-recheck.log](rust-tests-recheck.log) | 2026-11-13 워크스페이스 전체 재실행: 514개 통과·1개 ignored, 종료 0 |
| [ontology-runner-tests.log](ontology-runner-tests.log) | 온톨로지 실행기 4개 통과, 종료 0 |
| [spec-check.log](spec-check.log) | 기계 검사 46/46·존재 검사 72/72 통과, 종료 0 |
| [vocabulary.log](vocabulary.log), [validation.log](validation.log), [validation-selftest.log](validation-selftest.log) | 어휘·검증 자료 일관성·변조 탐지 검사 통과, 종료 0 |
| [blueprint-status.log](blueprint-status.log), [blueprint-counts.log](blueprint-counts.log) | 결정 색인·등록 수 일치, 종료 0 |
| [tracked-secrets-recheck.log](tracked-secrets-recheck.log) | 추적 대상 비밀 파일 검사 통과, 종료 0 |

`HistoryScan`은 커밋했다가 지운 비밀이 인계를 멈추고 커밋·푸시 0건인 것,
보존 커밋·푸시 직전에 나타난 이력도 걸리는 것, 읽을 수 없는 이력이
`handoff_blocked`로 닫히는 것, 깨끗한 이력은 인계를 지연시키지 않는 것을 본다.
`RealGitScan`은 실제 클론에서 2.5 MB 파일 꼬리의 비밀 탐지, base..HEAD의
메시지·패치가 반환되는 것, 읽을 수 없는 범위의 `QueryUnavailable`을 확인한다.
2026-11-13 추가 회귀는 바이너리·`-diff`·textconv 설정 파일을 추가 후 삭제해도
원문에서 탐지하는 것, 커밋 메시지에만 있는 시크릿, 커밋·푸시 직전 이력 읽기 실패의
닫힌 실패를 확인한다. `--text --no-textconv`와 디코딩 오류 대체로 Git의
표시 설정이나 UTF-8이 아닌 바이트 때문에 ASCII 자격 형식이 숨지 않게 했다.
기존 skip 6개는 보관소 환경 미설정 2개, 로컬 보관소·pdftotext 필요 3개,
설치된 botocore가 조건부 쓰기를 지원해 해당하지 않는 구버전 시험 1개다.

재현(루트에서):

```sh
python3 -m unittest tools/tests/test_daemon_secret_scan.py -v
python3 -m unittest tools/tests/test_daemon_dry_run.py -v
python3 -m unittest tools.daemon.runner_verify.tests.test_runner_verify -v
python3 -I tools/daemon/static_checks.py
python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all --quiet
python3 -m unittest discover -s tools/tests -v
cargo +1.98.1 fmt --all -- --check
cargo +1.98.1 clippy --locked --all-targets --offline -- -D warnings
cargo +1.98.1 test --all --locked --offline
cargo +1.98.1 test --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml
python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py
python3 -I tools/vocab_check.py
python3 -I tools/validation_check.py
python3 -I tools/validation_check.py --selftest
python3 -I tools/blueprint_status.py
python3 -I tools/check_tracked_secrets.py
RUSTUP_TOOLCHAIN=1.98.1 python3 -I tools/blueprint_counts.py
```

실제 Git 시험(`RealGitScan`)은 임시 클론만 만들고 init·add·commit·rev-parse·
write-tree·ls-files·log·show·config를 쓰며 원격을 만들지 않는다.
제품 작업 트리의 Git 커밋·푸시·GitHub·실제 제공자 호출은 하지 않았다.
전체 실행기 회귀는 임시 저장소 안의 합성 커밋과 시험 전용 로컬 원격을 사용한다.
이 증거는 09 §5의 개발 도구 보강이며 P01~P19의 완료 판정을 바꾸지 않는다.
