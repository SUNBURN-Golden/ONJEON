# Audit 6 — 데몬 받은편지함 독성 메시지 격리

2026-11-12. 개발 도구 T-OP-09 실제 실행기의 전달 경로를 수정했다.
제품 추적은 BLUEPRINT §9.5·09 §5의 T-OP-08 축 5에 한정한다.

감리 지적: `runner_verify/daemon_main.py`의 `op_drain`(63행)과 최상위
catch(200행 부근)가 `(PreconditionFailed, SpecGap, KeyError, RuntimeError)`만
잡았다. 받은편지함 파일 하나가 그 밖의 예외를 내면 — 푸시 어댑터의
`PushFailed`, 타임아웃(`TimeoutError`·`subprocess.TimeoutExpired`), `"envelope": "x"`처럼
봉투가 딕셔너리가 아닐 때의 `AttributeError` — 드레인 전체가 죽어 뒤의
모든 파일이 전달되지 못했고, 임대는 만료까지 방치됐다. JSON이 깨진
파일은 건너뛰기만 해 받은편지함에 영원히 남았다.

이제 드레인은 메시지마다 읽기·파싱·처리를 하나의 try로 묶고 `Exception`을
잡는다. 실패한 메시지는 기존 실패 처리와 같은 격리다: `daemon_done/`에
`ok:False` 기록(오류 유형·메시지)을 남기고 원본 파일을 옮긴 뒤 다음
파일로 계속한다. 원본은 보존돼 나중에 검사할 수 있다. 깨진 JSON도
건너뛰지 않고 같은 격리를 받는다. HTTP 전달(`serve`)도 같은 수리를
받았다: 잘못된 본문은 요청 처리기를 죽이는 대신 오류 응답을 받고
서버는 계속 전달한다. 최상위 catch도 `Exception`으로 넓혀 어떤 작업
실패든 하네스가 파싱하는 `RV_RESULT` 한 줄을 유지한다(생 traceback 없음).

가드 대기 재전달(`issue_lease.on_guard_wait`)과 `drain:processed_unmoved`
장애 지점은 그대로다. 장애 지점은 SIGKILL이라 어떤 except도 가로챌 수
없어 크래시 시나리오(R12·R16)의 의미는 변하지 않는다. 푸시 실패 뒤
요청 신원이 claimed로 남는 것은 Remote 포트 계약 그대로다: 격리는
재전달을 막을 뿐 모호한 원격 쓰기를 반복하지 않는다.

[실제 실행기 시험](../../../tools/daemon/runner_verify/tests/test_runner_verify.py)의
`DrainPoisonMessage`는 다섯 가지 예외(`PushFailed`·`TimeoutError`·
`subprocess.TimeoutExpired`·`AttributeError`·`TypeError`) 각각에서 독성 파일 앞뒤의 정상 메시지가 전달되고 격리
기록·원본이 남는 것, 깨진 JSON의 격리, 가드 대기 재전달과의 공존을
검사한다. 실제 프로세스 시험은 실제 어댑터 위에서 `"envelope": "x"`의
`AttributeError`, 미발급 자격의 `PushFailed`(permission_denied), 깨진 JSON을
같은 드레인에서 격리하고 뒤의 첫 하트비트가 leased→building으로 수락되는
것을 본다. HTTP 시험은 잘못된 본문 두 건이 오류 응답을 받고 서버가
세 번째 정상 메시지를 수락하는 것을 본다. 수정 전 소스에서는 이 시험들이
실패해 finding이 재현된다([재현 로그](../../../tools/evidence/audit6-daemon-drain-poison-message/prefix-reproduction.log)).

전체 회귀·시나리오·실행기 시험 결과와 재현 명령은
[실행 증거](../../../tools/evidence/audit6-daemon-drain-poison-message/README.md)에 기록한다.

2026-11-13 수정 1라운드: 전체 Python 시험 재실행에서 보고된 R2 admission
시간 초과(170초 > 120초)를 다뤘다. 로컬 HTTP 요청·바이트 회계 시험의
`EndToEnd` 두 클래스는 `r2_budget`의 monotonic 시계만 고정해 호스트 부하와
분리한다. botocore·서버의 실제 타임아웃은 유지한다. 별도 deadline 시험은
시계를 진행시켜 admission 거부·실행 시간 초과·정산을 계속 검증한다.
Git 어댑터의 실제 타임아웃 유형인 `subprocess.TimeoutExpired`도 독성 메시지
회귀에 추가했다. 운영 코드의 예산 제한은 바꾸지 않았으며, 전체 Python·실행기 시험과
독립 R2 회귀 결과를 위 실행 증거에 갱신한다.

증거 기록과 별개의 한계가 있다. 이 수리는 검증 도구의 전달 경로이지
상주 데몬(루프·스케줄러 없음)의 것이 아니다. 격리 기록 자체를 쓸 수 없는
인프라 실패(디스크 가득 참 등)는 여전히 작업 전체의 실패이며
`RV_RESULT ok:False`로 보고한다. 격리된 메시지의 재처리 절차는 없으며
원본을 사람이 검사하는 것이다. 결정 게이트·자격·전이·비용 정책은 그대로다.

이번 작업에서 제품 저장소의 Git 커밋·푸시·GitHub·실제 제공자 호출은 하지 않았다.
실행기 시험의 Git 원격은 표식이 붙은 임시 로컬 bare 저장소다.
이 증거는 [09 §5](../proposals/설계검토_결과/09_제품목적_대응표.md)의 개발 도구
보강이며, P01~P19의 전 상품 수집·트윈·소비자 화면·첫 출시 완료 판정을
바꾸지 않는다.
