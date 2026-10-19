# 실제 R2 검증 절차와 기록

기록: [real_r2_record.json](real_r2_record.json). **`status: executed_with_failures` — 실제 R2에서 실행했고, 11개 중 pass 8 · fail 1 · 미확인 2다. done이 아니다.**

실행: 2026-10-16 13:11~13:17 UTC. 준태님이 2026-10-16 19:45 KST에 명시 승인(`state/T-OP-04.ruling.md`)한 환경의 기존 R2 자격으로, 이번 검증에 한해 실행했다. 재발급 없음. 키·엔드포인트·계정 ID는 어디에도 적지 않았다. 대상 SHA는 감독기가 커밋한 뒤 채운다(기준 main `8d4c9d3` 위 커밋 전 작업 트리에서 실행). 실행 도구: [real_run/](real_run/)(비밀값 없음, 환경 변수만 읽음). 저장소의 `tools/`를 쓰며 boto3는 저장소 밖에 설치된 것을 쓴다.

보충 측정(2026-10-19 02:24~02:33 UTC): 누락됐던 종료 코드·요청 수를 채우려고 두 번째 시험 원장 버킷(`onjeon-t-op-04-test-ledger2`)을 만들고 `genesis → fixpolicy → status ×3 → race → gate → checkpoint → status → cprewrite → audit`를 같은 하네스로 다시 실행했다(첫 시험 원장은 달 마감이라 새 실행이 거부된다). 운영 버킷에는 요청을 보내지 않았다. 범위 프로브는 첫 실행이 승인 범위를 넘었던 것(운영 보관 버킷에 읽기 2회 — 쓰기·삭제 없음, `real_r2_record.json`의 `scope_note`)을 고쳐, 시험 버킷과 존재하지 않는 버킷 이름만 가리키는 `scope_probe.py`로 재실행했다(종료 코드 0, 요청 6).

## 결과

| 항목 | 결과 | 한 줄 요약 |
|---|---|---|
| `admission-before-read` | pass | 운영 status 실행: HEAD 2(마감 표지) → 입장 PUT → 그 뒤 LIST·GET. 클라이언트 쪽 관측 |
| `closure-after-limit` | pass | 시험 원장에서 한도 소진 → 마감 기록 생성, 마감을 모르는 컴퓨터는 HEAD 1회에서 거부 |
| `local-gate-one-at-a-time` | pass | 두 번째 동시 실행은 요청 0건으로 거부(종료 코드 0; 10-19 재측정 동일) |
| `reservation-race-412` | pass | 경쟁자가 순번 4를 먼저 쓰고 이 실행은 다시 판단해 순번 5. 412 코드는 결과로 확인(한 VM). 요청 수는 10-19 재측정(32요청) |
| `settlement-worst-case` | 미확인 (not_run) | R2 쪽 요청 수를 볼 수 없었다. 재시도 0건이라 재시도 경로도 못 봤다 |
| `conditional-write-412` | pass | 도구와 원시 PUT 모두 기존 키에 412, 바이트 불변(시험 버킷) |
| `ledger-tail-and-checkpoint` | pass | 체크포인트 뒤 실행은 기록 14건 중 2건만 읽음. 요청 종류별 분해는 못 함 |
| `checkpoint-write-once` | pass | 같은 키 재쓰기 412·불변, audit 통과. 요청 수는 10-19 재측정(재쓰기 18·audit 39) |
| `meter-matches-server-count` | 미확인 (not_run) | 토큰에 계정 분석 권한 없음. 대시보드 대조가 필요(사람). 클라이언트 호출 수 = 계량기 수(37 = 37)만 확인 |
| `token-scope-no-admin` | **fail** | 현재 자격은 계정 전체 범위: 목록·임의 버킷 지정·삭제 호출·버킷 생성이 거부되지 않음(10-19 시험 범위 프로브로 재확인) |
| `bucket-lock-not-applied-without-approval` | pass | 운영 3개와 시험 1개 버킷 모두 잠금 규칙 0건(읽기 조회) |

항목별 명령·종료 코드·요청 수·증거는 JSON 기록에 있다. 이 기록의 pass는 시험 조건 안에서의 통과이며, 이 과제의 완료 조건 중 **`token-scope-no-admin`은 실패, 두 항목은 미확인으로 남는다.** 해소하려면 TOKENS.md 절차의 범위 제한 토큰(소유자 작업)과 대시보드의 R2 분석 대조가 필요하고, 그 뒤에 이 기록의 해당 항목만 다시 실행한다.

## 쓴 요청과 남은 것

- 운영 원장: A와 `admission-before-read`의 status 실행 2번(입장·예약·정산 각 1건 = 항목당 1회 수준). 운영 객체는 삭제·덮어쓰지 않았다. 첫 범위 프로브가 승인 범위를 넘어 운영 보관 버킷에 HeadBucket·ListObjectsV2(키 1개)를 한 번씩 보냈다 — 읽기뿐이었으나 범위 밖이므로 일탈로 기록한다(`scope_note`). 고친 프로브와 보충 측정(10-19)은 운영 버킷에 요청을 보내지 않았다.
- 시험 버킷 3개를 새로 만들었다(시험 원장·시험 보관 10-16, 두 번째 시험 원장 10-19). 시험 원장은 이 달 입장 한도를 3으로 줄인 시험 정책 사본으로 일부러 마감시켰다. 승인 범위가 삭제를 금지해 **버킷과 객체를 지우지 않았다(소유자가 정리)**. 시험 원장에 settle되지 않은 예약 1건(하네스의 게이트 시험 중 첫 시도)이 있다.
- 잠금은 적용하지 않았다. 정책·작업 파일은 바꾸지 않았다.

## 시작 조건 (처음 실행 때; 이번 실행은 위 승인으로 1을 대체)

1. D-04 해제: 재발급 토큰이 환경에 있다(TOKENS.md). 노출 토큰으로는 하지 않는다.
2. 이 브랜치의 SHA를 `target_sha`로 적는다.
3. 작업 `infra/r2/jobs/initial-119.json`의 한도 안에서만 돈다. 정책·작업 파일은 바꾸지 않는다.
4. 잠금(O14)은 적용하지 않는다. 승인 없이 잠그지 않는다.

## 절차 (한 번에 하나, 수동)

A. `python3 -I tools/r2_budget.py status --job infra/r2/jobs/initial-119.json` — 입장→원장 검증→예약→정산. R2 쪽 요청 기록(대시보드 분석 또는 응답 헤더)과 stderr의 `budget …` 요약을 대조한다. → `admission-before-read`, `settlement-worst-case`, `meter-matches-server-count`.

B. 같은 명령을 월 입장 한도를 넘기지 않는 범위에서 두 컴퓨터(또는 두 `ONJEON_GATE_DIR`)에서 거의 동시에 실행해 한쪽이 412로 재판단하는지 본다. 같은 컴퓨터에서 두 번째 동시 실행이 요청 없이 거부되는지 본다. → `reservation-race-412`, `local-gate-one-at-a-time`. 한도 소진과 마감은 실제 한도를 쓰지 않도록 시험용 작업·정책 복사본을 임시 버킷에서 쓴다(운영 원장에 쌓지 않는다). → `closure-after-limit`.

C. 재발급 토큰으로 범위 밖 요청(다른 버킷, 삭제, 버킷 설정 조회)을 보내 거부되는지 확인한다. → `token-scope-no-admin`.

D. 기존 키에 다른 바이트로 조건부 쓰기: `upload` 재실행 또는 `verify-copy`로 412와 바이트 불변을 확인한다. → `conditional-write-412`.

E. `python3 -I tools/r2_budget.py checkpoint --job …` 후 `status`를 다시 돌려 체크포인트 이후 기록만 GET하는지(요청 로그), 같은 순번 재쓰기가 412인지, `audit`이 통과하는지 확인한다. → `ledger-tail-and-checkpoint`, `checkpoint-write-once`.

F. 버킷 잠금 규칙 조회(Cloudflare API 또는 대시보드)로 O14 승인 기록 없이 규칙이 켜져 있지 않음을 확인한다. → `bucket-lock-not-applied-without-approval`.

## 기록하는 법

각 항목의 `result`를 `pass`로 바꾸고 `evidence`에 명령, 종료 코드, 요청 수 요약, 날짜를 적는다(키·엔드포인트·계정 ID는 적지 않는다). 하나라도 실패하면 `status`를 `done`으로 바꾸지 않고 실패한 항목과 원인을 적는다. 시험 `RecordsAndDocs`가 `done`일 때 모든 항목이 `pass`이고 증거가 있는지 확인한다.

## 원장 수치와 청구의 대조 (O17 항목)

원장은 도구가 센 값이고 청구가 아니다. `meter-matches-server-count`에서 같은 기간의 Cloudflare 사용량(대시보드의 R2 분석)과 원장 합계를 나란히 적고 차이의 이유(기록되지 않는 요청 BUDGET.md §5, 단위 올림)를 설명한다. 차이가 설명되지 않으면 이 항목은 통과가 아니다.

## 다시 실행하는 법 (real_run/)

환경: `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT`(도구는 `ONJEON_S3_ENDPOINT`로 읽으므로 같은 값을 넣는다), 읽기 조회용 `CLOUDFLARE_API_TOKEN`, 그리고 boto3 1.35 이상. `ONJEON_REPO=<저장소>`를 두고 `python3 real_run/real_r2_run.py <빈 작업 디렉터리> <단계>`를 단계 순서대로 부른다(boto3가 사용자 site-packages에 있으면 `-I`가 그것을 숨기므로 격리 없이 실행했다): `setup`(시험 버킷 생성) → `genesis` → `fixpolicy` → `status` → `race` → `gate` → `conditional` → `rawconditional` → `checkpoint` → `status` → `cprewrite` → `audit` → `limit 3` → `status`(거부·마감) → `closedcheck`. 시험 버킷 이름은 `ONJEON_TEST_LEDGER_BUCKET`·`ONJEON_TEST_ARCHIVE_BUCKET`로 바꿀 수 있다(10-19 보충 측정은 `…-test-ledger2`로 실행). `scope_probe.py`(시험 버킷·존재하지 않는 버킷만; 삭제 동사 1회 포함), `lock_query.py`, `wire_trace.py`는 각각 C, F, A의 조회다. 하네스는 시험 정책·작업 사본을 작업 디렉터리에만 쓴다. 출력에 키·엔드포인트가 섞이지 않게 실행 결과를 파일에 옮길 때 환경 값 치환을 거쳤다.
