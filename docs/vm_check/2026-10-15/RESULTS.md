# T-OP-09 실제 실행기 검증 결과 (R1~R22)

생성 2026-10-15T12:06:45Z · 대상 {'parent_commit': 'c74a545a45d1aba9eee71b76d81b3017ac16bbbb', 'branch': 'grokbot/onjeon-T-OP-09'}

> 이 실행은 사람이 준비한 VM의 CLI·원격·자격 설정이 아니라, 이 호스트에서 로컬 구성요소(bare 원격, hook, 스크립트 빌더, 시험 프록시)로 한 것이다. 실제 호스트의 보호 브랜치·단기 자격과 벤더 CLI(claude CLI 하나를 빼고)는 확인하지 못했다.
> 이 과제의 완료는 가동 승인이 아니다. 가동 여부는 05 §7의 점검표와 사용자 결정으로만 정해진다.

시나리오 22개: PASS 19, FAIL 0, PARTIAL 3, UNCONFIRMED 0. 검사 404건 중 실패 0건, 미확인 11건, 명세 불일치(GAP) 1건.

| R | 필수 시험 ID | 항목 | 결과 | 검사 | 실제로 쓴 구성 | 한계·대체물 |
|---|---|---|---|---|---|---|
| R1 | late-write-fenced | 늦은 결과: 만료된 임대의 푸시 | **PASS** | 14/14 | OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL); 실제 파일 시스템(권한·mtime·/proc 핸들 검사); 실제 git(worktree·임시 인덱스·write-tree·push); 로컬 bare 원격(보호 브랜치·단기 자격 hook); 파일 잠금+원자적 rename 상태 저장소; 공용 전이·검증 코어(tools/daemon/core) | 빌더 프로세스는 스크립트(standin) — 벤더 CLI 아님; TTL·grace 경과는 시계 offset으로 만든다(대기 아님) |
| R2 | late-result-rejected | 늦은 결과: 만료된 임대의 결과 봉투와 인계 순서 | **PASS** | 9/9 | OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL); 실제 파일 시스템(권한·mtime·/proc 핸들 검사); 실제 git(worktree·임시 인덱스·write-tree·push); 로컬 bare 원격(보호 브랜치·단기 자격 hook); 파일 잠금+원자적 rename 상태 저장소; 공용 전이·검증 코어(tools/daemon/core) | 빌더 프로세스는 스크립트(standin) — 벤더 CLI 아님 |
| R3 | late-write-fenced | 교체 전후 동시 쓰기 | **PASS** | 12/12 | OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL); 실제 파일 시스템(권한·mtime·/proc 핸들 검사); 실제 git(worktree·임시 인덱스·write-tree·push); 로컬 bare 원격(보호 브랜치·단기 자격 hook); 파일 잠금+원자적 rename 상태 저장소; 공용 전이·검증 코어(tools/daemon/core) | 빌더 프로세스는 스크립트(standin) — 벤더 CLI 아님 |
| R4 | resume-after-interrupt | 중단·재개 | **PASS** | 13/13 | OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL); 실제 파일 시스템(권한·mtime·/proc 핸들 검사); 실제 git(worktree·임시 인덱스·write-tree·push); 로컬 bare 원격(보호 브랜치·단기 자격 hook); 파일 잠금+원자적 rename 상태 저장소; 공용 전이·검증 코어(tools/daemon/core) | 빌더 프로세스는 스크립트(standin) — 벤더 CLI 아님; 강제 종료는 SIGKILL(전원 차단 아님) |
| R5 | duplicate-run-prevented | 중복 실행 | **PASS** | 11/11 | OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL); 실제 파일 시스템(권한·mtime·/proc 핸들 검사); 실제 git(worktree·임시 인덱스·write-tree·push); 로컬 bare 원격(보호 브랜치·단기 자격 hook); 파일 잠금+원자적 rename 상태 저장소; 공용 전이·검증 코어(tools/daemon/core) | 동시 인스턴스는 별도 OS 프로세스 |
| R6 | provider-scoped-switch | 전환 신호 실제 채널 | **PARTIAL** | 21/26 | OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL); 실제 파일 시스템(권한·mtime·/proc 핸들 검사); 실제 git(worktree·임시 인덱스·write-tree·push); 로컬 bare 원격(보호 브랜치·단기 자격 hook); 파일 잠금+원자적 rename 상태 저장소; 공용 전이·검증 코어(tools/daemon/core); claude CLI(시험 프록시, 더미 키) | 다른 CLI는 이 호스트에서 시험하지 못함(미확인) |
| R7 | provider-scoped-switch | 종료 코드 확인표 | **PARTIAL** | 10/15 | claude CLI(시험 프록시); 시험 프록시 | 다른 CLI는 미확인 |
| R8 | - | 반송 재개·결정 관문 | **PASS** | 8/8 | OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL); 실제 파일 시스템(권한·mtime·/proc 핸들 검사); 실제 git(worktree·임시 인덱스·write-tree·push); 로컬 bare 원격(보호 브랜치·단기 자격 hook); 파일 잠금+원자적 rename 상태 저장소; 공용 전이·검증 코어(tools/daemon/core) | 빌더 프로세스는 스크립트(standin) — 벤더 CLI 아님; 관측(CI·리뷰·결정 기록)은 도구가 넣은 입력 |
| R9 | hard-stop-heartbeating-job | 강제 종료 기한 | **PARTIAL** | 17/19 | OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL); 실제 파일 시스템(권한·mtime·/proc 핸들 검사); 실제 git(worktree·임시 인덱스·write-tree·push); 로컬 bare 원격(보호 브랜치·단기 자격 hook); 파일 잠금+원자적 rename 상태 저장소; 공용 전이·검증 코어(tools/daemon/core); claude CLI(시험 프록시, 변형) | 빌더 프로세스는 스크립트(standin) — 벤더 CLI 아님; TTL·grace 경과는 시계 offset으로 만든다(대기 아님) |
| R10 | usage-recorded-not-capped | 사용량 기록(상한 없음, U-05) | **PASS** | 10/10 | OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL); 실제 파일 시스템(권한·mtime·/proc 핸들 검사); 실제 git(worktree·임시 인덱스·write-tree·push); 로컬 bare 원격(보호 브랜치·단기 자격 hook); 파일 잠금+원자적 rename 상태 저장소; 공용 전이·검증 코어(tools/daemon/core); claude CLI(시험 프록시); 시험 프록시 계량 | cost_units 단위 미정의, 금액은 기록 불가 |
| R11 | handoff-quiescent-before-preserve | 정지 확인 뒤 보존 | **PASS** | 18/18 | OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL); 실제 파일 시스템(권한·mtime·/proc 핸들 검사); 실제 git(worktree·임시 인덱스·write-tree·push); 로컬 bare 원격(보호 브랜치·단기 자격 hook); 파일 잠금+원자적 rename 상태 저장소; 공용 전이·검증 코어(tools/daemon/core) | 빌더 프로세스는 스크립트(standin) — 벤더 CLI 아님; lsof 대신 /proc 검사 |
| R12 | duplicate-delivery-noop | 중복 전달 noop | **PASS** | 9/9 | OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL); 실제 파일 시스템(권한·mtime·/proc 핸들 검사); 실제 git(worktree·임시 인덱스·write-tree·push); 로컬 bare 원격(보호 브랜치·단기 자격 hook); 파일 잠금+원자적 rename 상태 저장소; 공용 전이·검증 코어(tools/daemon/core); 파일 큐; HTTP(로컬) | 빌더 프로세스는 스크립트(standin) — 벤더 CLI 아님 |
| R13 | retry-new-idempotency-key | 재시도 새 키 | **PASS** | 21/21 | OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL); 실제 파일 시스템(권한·mtime·/proc 핸들 검사); 실제 git(worktree·임시 인덱스·write-tree·push); 로컬 bare 원격(보호 브랜치·단기 자격 hook); 파일 잠금+원자적 rename 상태 저장소; 공용 전이·검증 코어(tools/daemon/core) | 빌더 프로세스는 스크립트(standin) — 벤더 CLI 아님 |
| R14 | preserve-manifest-same-function | 보존 manifest | **PASS** | 18/18 | OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL); 실제 파일 시스템(권한·mtime·/proc 핸들 검사); 실제 git(worktree·임시 인덱스·write-tree·push); 로컬 bare 원격(보호 브랜치·단기 자격 hook); 파일 잠금+원자적 rename 상태 저장소; 공용 전이·검증 코어(tools/daemon/core) | 빌더 프로세스는 스크립트(standin) — 벤더 CLI 아님 |
| R15 | preserve-failure-recoverable-stop | 보존 실패 정리 | **PASS** | 63/63 | OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL); 실제 파일 시스템(권한·mtime·/proc 핸들 검사); 실제 git(worktree·임시 인덱스·write-tree·push); 로컬 bare 원격(보호 브랜치·단기 자격 hook); 파일 잠금+원자적 rename 상태 저장소; 공용 전이·검증 코어(tools/daemon/core); user namespace tmpfs(가득 찬 디스크) | 빌더 프로세스는 스크립트(standin) — 벤더 CLI 아님; 원격 거부는 hook 제어 파일로 만든 것 |
| R16 | daemon-restart-during-handoff | 인계 도중 데몬 재시작 | **PASS** | 54/54 | OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL); 실제 파일 시스템(권한·mtime·/proc 핸들 검사); 실제 git(worktree·임시 인덱스·write-tree·push); 로컬 bare 원격(보호 브랜치·단기 자격 hook); 파일 잠금+원자적 rename 상태 저장소; 공용 전이·검증 코어(tools/daemon/core) | 빌더 프로세스는 스크립트(standin) — 벤더 CLI 아님 |
| R17 | envelope-id-distinct-events | 봉투 식별 | **PASS** | 7/7 | OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL); 실제 파일 시스템(권한·mtime·/proc 핸들 검사); 실제 git(worktree·임시 인덱스·write-tree·push); 로컬 bare 원격(보호 브랜치·단기 자격 hook); 파일 잠금+원자적 rename 상태 저장소; 공용 전이·검증 코어(tools/daemon/core) | 빌더 프로세스는 스크립트(standin) — 벤더 CLI 아님 |
| R18 | lease-issue-atomic-single-owner | 발급 원자성 | **PASS** | 42/42 | OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL); 실제 파일 시스템(권한·mtime·/proc 핸들 검사); 실제 git(worktree·임시 인덱스·write-tree·push); 로컬 bare 원격(보호 브랜치·단기 자격 hook); 파일 잠금+원자적 rename 상태 저장소; 공용 전이·검증 코어(tools/daemon/core) | SIGKILL 시험(전원 차단 아님) |
| R19 | restart-ttl-expired-no-resend | 발급 직후 중단 뒤 TTL 경과 | **PASS** | 6/6 | OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL); 실제 파일 시스템(권한·mtime·/proc 핸들 검사); 실제 git(worktree·임시 인덱스·write-tree·push); 로컬 bare 원격(보호 브랜치·단기 자격 hook); 파일 잠금+원자적 rename 상태 저장소; 공용 전이·검증 코어(tools/daemon/core) | TTL·grace 경과는 시계 offset으로 만든다(대기 아님) |
| R20 | restart-revoked-pending-void | 폐기된 pending | **PASS** | 5/5 | OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL); 실제 파일 시스템(권한·mtime·/proc 핸들 검사); 실제 git(worktree·임시 인덱스·write-tree·push); 로컬 bare 원격(보호 브랜치·단기 자격 hook); 파일 잠금+원자적 rename 상태 저장소; 공용 전이·검증 코어(tools/daemon/core) | 빌더 프로세스는 스크립트(standin) — 벤더 CLI 아님 |
| R21 | restart-valid-pending-resend | 유효 pending 재전송 | **PASS** | 8/8 | OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL); 실제 파일 시스템(권한·mtime·/proc 핸들 검사); 실제 git(worktree·임시 인덱스·write-tree·push); 로컬 bare 원격(보호 브랜치·단기 자격 hook); 파일 잠금+원자적 rename 상태 저장소; 공용 전이·검증 코어(tools/daemon/core) | 빌더 프로세스는 스크립트(standin) — 벤더 CLI 아님; TTL·grace 경과는 시계 offset으로 만든다(대기 아님) |
| R22 | restart-corrupt-record-returned | 손상 기록 | **PASS** | 16/16 | OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL); 실제 파일 시스템(권한·mtime·/proc 핸들 검사); 실제 git(worktree·임시 인덱스·write-tree·push); 로컬 bare 원격(보호 브랜치·단기 자격 hook); 파일 잠금+원자적 rename 상태 저장소; 공용 전이·검증 코어(tools/daemon/core) | 빌더 프로세스는 스크립트(standin) — 벤더 CLI 아님 |

## 실패와 미확인

- **UNCONFIRMED** R6 [Cursor CLI] 모델 제공자 상태가 CLI의 상태 채널로 데몬에 도달하는지 — 기본 주소를 시험 프록시로 돌리는 문서화된 설정을 확인하지 못했고, 호출에는 이 호스트에 없는 로그인이 필요하다 (설치 확인: 버전 2026.10.14-0f9edde)
- **UNCONFIRMED** R6 [grokbuild CLI] 모델 제공자 상태가 CLI의 상태 채널로 데몬에 도달하는지 — 설치되어 있지 않다
- **UNCONFIRMED** R6 [Devin CLI] 모델 제공자 상태가 CLI의 상태 채널로 데몬에 도달하는지 — 기본 주소를 시험 프록시로 돌리는 문서화된 설정을 확인하지 못했고, 호출에는 이 호스트에 없는 로그인이 필요하다 (설치 확인: 버전 devin 3000.11.92 (7f4e64980e22))
- **UNCONFIRMED** R6 [Claude Code(GLM 프로필)] 모델 제공자 상태가 CLI의 상태 채널로 데몬에 도달하는지 — GLM 호환 주소와 별도 프로필이 이 호스트에 없다. 같은 CLI의 Anthropic 주소 프로필 결과를 대신 쓰지 않는다
- **UNCONFIRMED** R6 [대체 모델 경로(GPT 계열, 경로 미정)] 모델 제공자 상태가 CLI의 상태 채널로 데몬에 도달하는지 — 사용할 CLI·API 경로가 정해지지 않았다(05 §1a)
- **UNCONFIRMED** R7 [Cursor CLI] 종료 코드·구조화 오류 확인 — 기본 주소를 시험 프록시로 돌리는 문서화된 설정을 확인하지 못했고, 호출에는 이 호스트에 없는 로그인이 필요하다
- **UNCONFIRMED** R7 [grokbuild CLI] 종료 코드·구조화 오류 확인 — 설치되어 있지 않다
- **UNCONFIRMED** R7 [Devin CLI] 종료 코드·구조화 오류 확인 — 기본 주소를 시험 프록시로 돌리는 문서화된 설정을 확인하지 못했고, 호출에는 이 호스트에 없는 로그인이 필요하다
- **UNCONFIRMED** R7 [Claude Code(GLM 프로필)] 종료 코드·구조화 오류 확인 — GLM 호환 주소와 별도 프로필이 이 호스트에 없다. 같은 CLI의 Anthropic 주소 프로필 결과를 대신 쓰지 않는다
- **UNCONFIRMED** R7 [대체 모델 경로(GPT 계열, 경로 미정)] 종료 코드·구조화 오류 확인 — 사용할 CLI·API 경로가 정해지지 않았다(05 §1a)
- **GAP** R9 끝난 임대의 작업 트리는 읽기 전용으로 남는다(04 §8) — hard_stop_deadline 전이의 부수 효과에 worktree_readonly가 없어 코어는 작업 트리를 읽기 전용으로 만들지 않는다. R9의 통과 기준(프로세스 그룹 종료·자격 회수·뒤의 푸시·봉투 거부)에는 들어 있지 않다
- **UNCONFIRMED** R9 [실제 CLI] SIGTERM을 무시하며 하트비트를 보내는 실제 CLI의 강제 종료(grace_s 뒤 그룹 종료) — 이 CLI는 SIGTERM에 스스로 종료했다(셸 trap으로 무시를 물려줘도 자체 핸들러가 이를 덮었다). grace_s 뒤 그룹 종료가 이 CLI를 끝낸 것이 아니므로 그 부분은 스크립트 프로세스(standin) 결과만 있다

## 증명하지 않은 것 (시나리오별)

- R1: 원격 거부(직접 푸시)가 데몬의 R-11 기록으로 이어지는 경로는 명세에 없다: 데몬이 R-11을 남기는 것은 데몬 경유 푸시 요청·결과 봉투·하트비트뿐이다
- R1: 실제 Git 호스트의 보호 브랜치와 단기 자격 발급·회수는 사람이 적용하는 설정이다(04 §8). 여기서는 로컬 bare 저장소의 hook이 그 역할을 했다
- R1: A는 벤더 CLI가 아니라 스크립트 프로세스(standin)다
- R2: 순서 증거는 데몬이 남긴 로그, 프로세스 레지스터, 원격 hook 로그의 시각을 맞춰 본 것이다. 서로 다른 호스트의 시계는 맞추지 않았다(한 호스트)
- R2: A는 벤더 CLI가 아니라 스크립트 프로세스(standin)다
- R3: 자격 구간은 데몬이 쓴 발급·회수 로그의 시각이다. 원격 hook은 푸시 시점에 같은 자격 기록을 읽는다. 실제 호스트의 토큰 만료·회수 전파 지연은 확인하지 못했다
- R3: 읽기 전용 격리는 파일 권한이다. 같은 사용자의 살아 있는 프로세스가 권한을 되돌릴 수 있고, 그 경우를 막는 것은 프로세스 그룹 종료와 열린 쓰기 핸들 검사다(R11)
- R3: A·B는 벤더 CLI가 아니라 스크립트 프로세스(standin)다
- R4: 강제 종료는 SIGKILL(커널이 프로세스를 즉시 없앰)이다. 전원 차단·디스크 캐시 유실은 시험하지 않았다(fsync는 호출하지만 하드웨어까지 확인하지 못했다)
- R4: A는 벤더 CLI가 아니라 스크립트 프로세스(standin)다
- R5: 같은 task_id의 열린 PR 재사용(M12의 PR 부분)은 이 시험의 범위가 아니다(R5 통과 기준은 임대·봉투 하나)
- R6: 프록시는 CLI의 기본 주소 설정으로 가리킨 로컬 서버다. 실제 제공자가 내는 429·5xx 본문·헤더·재시도 지시와의 차이는 확인하지 못했다
- R6: 확인한 것은 이 CLI 버전과 이 출력 모드(stream-json)에서의 상태 채널이다. 다른 모드·버전은 다시 확인해야 한다
- R6: claude CLI 밖의 실행 경로(Cursor, grokbuild, Devin, GLM 프로필, GPT Astra 경로)는 이 호스트에서 시험하지 못했다(§1b 확인표는 미확인으로 남는다)
- R7: 종료 코드는 시험 프록시가 만든 상황에서 얻은 값이다. 공식 문서의 종료 코드 표와 대조하지 않았다
- R7: §1b 확인표의 '모델 제공자 HTTP 응답을 데몬이 볼 수 있는 채널'은 claude CLI의 stream-json 출력(이 버전)만 확인되었다
- R8: CI·리뷰·결정 기록 입력은 시험 도구가 관측 계층에 직접 넣은 것이다(실제 CI·리뷰 서비스 없음). 이 시험이 보는 것은 같은 규칙이 실제 상태 저장소·프로세스에서도 같은 전이를 낸다는 것이다
- R9: SIGTERM을 무시하고 하트비트를 보내는 동작은 스크립트 프로세스(standin)로 시험했다. 벤더 CLI의 같은 동작은 R9 실제 CLI 변형(있으면 별도 기록)에서 본다
- R9: 중단 지시를 빌더에게 전달하는 SIGTERM은 어댑터(sender.request_stop)가 보냈다. 코어의 request_stop 효과는 시각만 기록하고 전달 호출을 하지 않는다
- R10: 호출 수·토큰은 프록시를 거친 호출만 계량한다. 프록시를 거치지 않는 직접 호출·제공자 청구액과의 대조는 하지 않았다(사람이 월 1회, 05 §3)
- R10: cost_units의 단위는 명세에 정의가 없다. 이 시험은 프록시가 센 토큰 수를 넣었고 금액이 아니다
- R10: 누적 10^9는 스크립트 프로세스가 결과 봉투에 적은 자기 보고 값이다
- R11: 쓰기 금지 격리는 파일 권한(chmod)이다. 같은 사용자의 프로세스는 권한을 되돌릴 수 있으므로 격리만으로 쓰기를 막았다고 말하지 않는다: 이 시험에서 쓰기를 막은 것은 프로세스 그룹 종료와, 그룹 밖 프로세스에 대한 열린 핸들 검사(정지 확인 실패)였다
- R11: lsof는 이 호스트에 없다. /proc/<pid>/fd와 fdinfo 검사로 대신했다(동등 수단)
- R11: 쓰는 프로세스는 벤더 CLI가 아니라 스크립트 프로세스(standin)다
- R12: HTTP는 같은 호스트의 로컬 서버다. 네트워크 지연·재정렬·부분 전송은 확인하지 못했다
- R13: 재임대 경로는 모의 과제의 상태 기계 경로다. CI 실패 뒤 재임대(ci_failed→building)는 관측 계층 입력이 필요해 이 도구에서 시험하지 않았다(R8과 같은 관측 입력 경로)
- R14: 트리 해시 함수가 하나라는 점(다른 해시 정의 없음)은 정적 검사가 본다. 여기서는 같은 함수의 결과가 실제 git 객체와 같다는 것을 확인했다
- R15: 원격 푸시 실패 네 가지 중 '네트워크 차단'은 닫힌 로컬 포트로 간 주소이고 '권한·보호 규칙 거부'는 hook의 시험용 제어 파일이 만든 거부다. 실제 호스트의 거부 응답 형식은 확인하지 못했다
- R15: '가득 찬 디스크'는 새 git 객체가 쓰이는 디렉터리를 64 KiB tmpfs로 바꾼 것이다(같은 프로세스의 마운트 네임스페이스에서만). 저장소 전체가 찬 경우의 다른 실패 지점은 보지 않았다
- R16: 재시작 시점은 데몬 코어의 fault 지점(SIGKILL로 죽는 위치)이다. 지점 사이에서 임의 시각에 죽는 경우는 R18의 저장 지점 훑기와 같은 방식으로만 보았다
- R18: 세대 증가의 단일 책임(issue_lease 한 곳)은 정적 검사가 본다. 여기서는 어느 저장 지점에서 죽어도 중간 상태가 없다는 것만 확인했다
- R18: SIGKILL 시험이다. 전원 차단 때 디스크가 쓰기 순서를 지키는지(fsync 의미)는 하드웨어·파일 시스템 몫이고 확인하지 못했다
- R22: 파일 수준 손상에서 데몬은 멈추기만 한다(복구·소유자 결정 절차는 사람 몫이다). 명세가 파일 수준 손상의 R 코드를 정하지 않았다

## 제품 브랜치

```json
{
 "head_before": "c74a545a45d1aba9eee71b76d81b3017ac16bbbb",
 "head_after": "c74a545a45d1aba9eee71b76d81b3017ac16bbbb",
 "refs_unchanged": true,
 "remotes_unchanged": true,
 "test_remote_pushes": {
  "accepted": 29,
  "rejected": 14,
  "applied_refs_outside_task": [],
  "applied": 29
 },
 "merge_calls": 0,
 "refs_applied_outside_task_branches": []
}
```
