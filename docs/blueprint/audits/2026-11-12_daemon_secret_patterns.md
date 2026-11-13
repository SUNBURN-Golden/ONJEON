# Audit 6 — 데몬 비밀값 형식·이력·파일 크기 공백

2026-11-12. 개발 도구 T-OP-00·T-OP-09의 비밀값 탐지 경계를 보강했다.
제품 추적은 BLUEPRINT §9.5·09 §5의 T-OP-08 축 5에 한정한다.

감리 지적은 세 가지였다. (1) `daemon_rules.json`의 패턴이 GitHub `gho_`·`ghu_`·`ghr_`,
Anthropic `sk-ant-`, `scheme://user:token@` 형식의 자격 URL을 잡지 못했다.
`github_pat_`·`ghs_`·AWS `ASIA`·AWS secret·R2 키·Bearer·JSON `"token": "…"`은
Audit 5에서 들어갔지만 이번 감리는 그 존재도 함께 회귀로 고정하기를 요구했다.
(2) 실제 Git 어댑터의 `included_files`가 파일을 2,000,000바이트에서 잘라
그 뒤의 비밀은 보지 못했다. (3) 스캔은 작업 트리의 내용만 봤다. 커밋했다가 지운
비밀은 트리에 없지만 push가 싣고 나가는 이력에는 그대로 남는다.

[규칙 데이터](../proposals/설계검토_결과/daemon_rules.json)에 `gho_`·`ghu_`·`ghr_`을
포함하는 GitHub 형식, `sk-ant-`, 스킴 길이를 32자로 제한한 자격 URL 패턴을 더하고,
`secret_patterns.scan`에 `preserve_history` 지점을 추가했다. `Git.history_texts`는
`base..HEAD`의 각 커밋 메시지와 패치를 돌려주고(`git log`·`git show -m --first-parent
--patch`), 인계 코어는 `confirm_quiescent`와 `preserve_commit`·`preserve_push` 직전에
그 이력을 다시 검사한다. 커밋 단위는 파일처럼 제외할 수 없으므로 일치하면
`secret_detected`(R-10)로 인계를 멈추고 커밋·푸시는 일어나지 않는다. 이력을 읽지
못하면(`QueryUnavailable`, 읽을 수 없는 base 포함) 검사를 건너뛰지 않고
`quiescence_failed`·`preserve_*_failed`의 닫힌 실패가 된다. `included_files`는
이제 파일 전체를 읽는다.

URL 패턴의 스킴 한계 32자(첫 글자 뒤 최대 31자)는 성능 안전장치다. 경계 없는 스킴 반복은 같은 문자가
길게 이어진 파일에서 `://` 불일치를 위치마다 다시 시도해 2차 시간이 걸렸고,
그 회귀가 2.5 MB 시험 파일에서 나타났다. 통상적인 `https`·`ssh`·`git` 스킴은
포함하지만 32자를 넘는 사용자 정의 스킴은 탐지 범위 밖이다.

[회귀 시험](../../../tools/tests/test_daemon_secret_scan.py)은 사전 검사 corpus를
36개 형식으로 늘려 새 형식을 양성으로, 자격 없는 URL(사용자 정보 없음·포트만·
`user@`만·scp 형식)을 음성 경계로 고정했다. `HistoryScan`은 이력의 비밀이
인계를 멈추고 커밋·푸시가 0건인 것, 커밋 직전·푸시 직전에 나타난 이력도 걸리는 것,
읽을 수 없는 이력이 `handoff_blocked`로 닫히는 것, 깨끗한 이력은 인계를 지연시키지
않는 것을 검사한다. `RealGitScan`은 실제 클론에서 2.5 MB 파일의 꼬리 비밀 탐지,
base..HEAD 두 커밋의 메시지·패치가 옮겨지는 것, 읽을 수 없는 범위의
`QueryUnavailable`을 확인한다. 실제 Git 시험은 init·add·commit·rev-parse·
write-tree·ls-files·log·show·config만 허용하며 원격·푸시를 만들지 않는다.

2026-11-13 재검증에서 Git이 바이너리·`.gitattributes`의 `-diff` 파일 내용을
일반 패치에서 생략하는 추가 공백을 실패 시험으로 재현했다.
`history_texts`에 `--text --no-textconv`를 적용해 원래 패치를 읽고,
UTF-8이 아닌 바이트는 대체하면서 ASCII 자격 형식을 보존한다.
바이너리·diff 제외·textconv 설정 파일의 추가 후 삭제, 커밋 메시지만의 시크릿,
보존 커밋·푸시 직전 이력 읽기 실패를 추가 회귀로 고정했다. 합성 값만 사용하며
`textconv` 설정은 임시 시험 저장소에만 적용한다.

전체 회귀·실행기·정적 검사 결과와 재현 명령, HEAD 대비 탐지 공백을 재현한
before 로그는 [실행 증거](../../../tools/evidence/audit6-daemon-secret-patterns/README.md)에
기록한다. `o13_unchanged_gates.json`의 규칙 파일 해시는 HEAD와 구조적으로 대조해
`preserve_manifest.secret_patterns` 외 모든 값이 같은지 확인한 뒤 갱신 이유와
함께 다시 고정했다. 보고서·로그 해시 머리말도 현재 소스 해시로 다시 썼고,
audit5 이후 낡아 있던 `검증/실행로그_spec_check.txt`(45건 기록, 현재는 G48 포함
46건)도 이번 실행 출력으로 갱신했다.

2026-11-13 수정 2회차는 감독자의 900초 초과(`python_codegen_suite_passes`)를
실패로 처리했다. 변경 전 Python 호환 검사 단독 실행은 121.049초에 통과해
같은 900초 지연을 재현하지는 못했다. 다만 느린 부분은 실제 Cargo를 실행하는
`CheckCompatScript`였고, 바깥 `--offline`이 자식 Cargo에 전달되지 않으며
잠금 파일 없는 회귀는 레지스트리를 다시 조회할 수 있었다. 시험에서
`CARGO_NET_OFFLINE=true`와 작업 트리 안의 `target/compat-probe`를 고정하고
각 호환 검사에 120초 제한을 넣었다. 제한 초과 시 출력과 함께 실패하고
셸뿐 아니라 자식 빌드 프로세스 그룹까지 종료하는 회귀도 추가했다.
임시 저장소·Cargo 실행 위치가 rustup의 작업 트리 재정의를 벗어나던 경로도
`--manifest-path`로 고쳤다. Rust가 호출하는 Python 시험은 상세 이름을 출력한다.
현재 원문 해시와 달랐던 데몬 증거 머리말도 다시 계산했다.
최종 재실행은 전체 Python 1,604개(기존 skip 6개), codegen 130개,
실제 실행기 61개, Rust 514개(기존 ignored 1개)가 통과했다.
900초 제한을 건 전체 Rust 명령은 169.993초에 종료 0이었고,
그 안의 codegen 시험은 142.700초에 끝났다. 증거 로그 재작성 때 빠뜨린
`# output` 구분자도 복원한 뒤 전체 Python을 다시 실행했다.

2026-11-13 수정 3회차는 전체 Python 실행에서 정적 검사 CLI 시험 하나가
30초 제한을 초과한 실패를 처리했다. `test_cli_rejects_planted_violations_without_executing_them`은
심어 둔 위반을 검출하는지 보려고 복사된 데몬 트리의 CLI를 열 번 실행하는데,
당시 기계는 8코어에 부하 평균 45로 다른 작업 트리와 자원을 나누고 있었다.
원인은 이번 패턴 변경이 아니라 기존 구조였다. `all_static()`의 각 검사가 같은
소스를 다시 읽어 파싱해서, 한 실행에 24개 파일을 160번(파일당 최대 7번) 파싱했다.
기준 커밋에서도 같음을 [static-before-round3.log](../../../tools/evidence/audit6-daemon-secret-patterns/static-before-round3.log)로
재현했다. 파싱이 실행 시간의 대부분이었고, 부하가 겹치면 CLI 한 번이 30초를 넘겼다.

이제 한 `all_static()` 실행은 소스마다 한 번만 읽고 파싱한 결과를 검사끼리 공유한다
(24개 파일 24번 파싱). 캐시는 실행 안에서만 켜지고 실행이 끝나면 풀린다.
검사 함수를 직접 부르는 호출은 항상 새로 읽으므로 캐시가 오래된 내용을 줄 수 없고,
판정 결과는 캐시 전후가 같다(정적 13/13 통과). 새 회귀 시험 세 개가 파일당 1회 파싱,
실행 간 결과 동일·캐시 해제, 직접 호출의 최신 내용 읽기를 고정한다.
[static-round3.log](../../../tools/evidence/audit6-daemon-secret-patterns/static-round3.log)의
CLI 단독 실행은 0.76~1.96초였다.

최종 재실행은 전체 Python 1,607개(기존 skip 6개, 새 회귀 3개 포함)가 490.097초에
통과했고, 실제 실행기 회귀 61개도 544.580초에 통과했다. 모의 데몬 695개 검사·
필수 ID 33/33, 정적 13/13, 명세 기계 46/46·존재 72/72, 추적 비밀 파일 검사가 통과했다.
보고서·로그 해시 머리말은 현재 소스 해시로 다시 썼고,
`reports/unittest.log`은 이번 전체 실행에서 데몬 네 모듈(모의 300·비밀값 27·정적 22·
필수 커버리지 7) 356개 결과를 발췄다. Rust 소스·코드젠은 이번 회차에 바뀌지 않아
2회차 Rust 증거가 그대로 유효하다.

2026-11-13 수정 4회차는 main(`a51a495a6eb2a8518825e1f7951ea915aa10a088`, PR #507
리스 만료 뒤 푸시 차단·#505 독성 메시지 격리·#501 push refspec 검증) 병합 충돌
다섯 건을 양쪽 의도를 모두 살려 해소했다. 09 대응표는 독성 메시지 격리와 비밀값
탐지 보강 불릿을 모두 유지하고, `o13_unchanged_gates.json`은 push-refspec과
secret-patterns 설명을 모두 이은 뒤 규칙 파일 해시를 병합 결과로 다시 고정했다
(각 부모 대비 차이가 상대방 필드뿐임을 구조적으로 확인). `reports/dry_run.log`는
README가 요구하는 기대·실제 전체 보고서로 복원했고(main 본문과 바이트 일치),
`검증/실행로그_dry_run.txt`는 현재 전체 실행의 quiet 출력으로 다시 만들었다
(본문은 3회차와 같다). `reports/unittest.log`는 이번 전체 실행에서 데몬 네 모듈
366개(모의 310·비밀값 27·정적 22·필수 커버리지 7)를 발췌했고, 두 보고서 머리말은
병합 부모(`8b2cf5c` + main `a51a495`)와 현재 소스 해시를 적는다. 전체 재실행은
Python 1,617개(기존 skip 6개) 433.919초, 실제 실행기 80개 724.807초,
Rust 515개(기존 ignored 1개), 온톨로지 실행기 4개, 모의 데몬 695개 검사·
필수 ID 33/33, 정적 13/13, 명세 기계 46/46·존재 72/72, 추적 비밀 파일 검사가
통과했다.

한계는 그대로다. 패턴 기반 검사이므로 임의 비밀값 전체를 검출한다는 보장은 없고,
이력 스캔은 푸시가 싣는 `base..HEAD` 범위만 본다(이미 원격에 있는 옛 커밋은
범위 밖이다). 커밋 메시지·패치를 스캔 대상으로 삼은 것은 인계 경계의 보존
행위이며 탐지된 원문은 어디에도 기록하지 않는다.
제품 작업 트리의 Git 커밋·푸시·GitHub·실제 제공자 호출은 하지 않았다.
Git 통합 시험은 임시 저장소 안의 합성 커밋과 시험 전용 로컬 원격만 사용한다.
이 증거는 [09 §5](../proposals/설계검토_결과/09_제품목적_대응표.md)의 개발 도구
보강이며, P01~P19의 전 상품 수집·트윈·소비자 화면·첫 출시 완료 판정을 바꾸지 않는다.
