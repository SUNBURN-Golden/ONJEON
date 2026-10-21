"""The R1-R22 scenarios of 05 §6, the test ids of tasks.json (T-OP-09) they answer, and what each one rests on."""
from . import scn_cli, scn_envelope, scn_fence, scn_handoff, scn_restart

REAL_BASE = ["OS 프로세스·프로세스 그룹(SIGTERM/SIGKILL)", "실제 파일 시스템(권한·mtime·/proc 핸들 검사)", "실제 git(worktree·임시 인덱스·write-tree·push)",
             "로컬 bare 원격(보호 브랜치·단기 자격 hook)", "파일 잠금+원자적 rename 상태 저장소", "공용 전이·검증 코어(tools/daemon/core)"]
STANDIN = "빌더 프로세스는 스크립트(standin) — 벤더 CLI 아님"
CLOCK = "TTL·grace 경과는 시계 offset으로 만든다(대기 아님)"


def r9(rep, cx):
    scn_fence.r9(rep, cx)
    scn_cli.r9_real_cli(rep, cx)


# (R id, required test id or None, title, function, real components, stand-ins / limits)
SCENARIOS = [
    ("R1", "late-write-fenced", "늦은 결과: 만료된 임대의 푸시", scn_fence.r1, REAL_BASE, [STANDIN, CLOCK]),
    ("R2", "late-result-rejected", "늦은 결과: 만료된 임대의 결과 봉투와 인계 순서", scn_fence.r2, REAL_BASE, [STANDIN]),
    ("R3", "late-write-fenced", "교체 전후 동시 쓰기", scn_fence.r3, REAL_BASE, [STANDIN]),
    ("R4", "resume-after-interrupt", "중단·재개", scn_restart.r4, REAL_BASE, [STANDIN, "강제 종료는 SIGKILL(전원 차단 아님)"]),
    ("R5", "duplicate-run-prevented", "중복 실행", scn_restart.r5, REAL_BASE, ["동시 인스턴스는 별도 OS 프로세스"]),
    ("R6", "provider-scoped-switch", "전환 신호 실제 채널", scn_cli.r6, REAL_BASE + ["claude CLI(시험 프록시, 더미 키)"],
     ["다른 CLI는 이 호스트에서 시험하지 못함(미확인)"]),
    ("R7", "provider-scoped-switch", "종료 코드 확인표", scn_cli.r7, ["claude CLI(시험 프록시)", "시험 프록시"], ["다른 CLI는 미확인"]),
    ("R8", None, "반송 재개·결정 관문", scn_envelope.r8, REAL_BASE, [STANDIN, "관측(CI·리뷰·결정 기록)은 도구가 넣은 입력"]),
    ("R9", "hard-stop-heartbeating-job", "강제 종료 기한", r9, REAL_BASE + ["claude CLI(시험 프록시, 변형)"], [STANDIN, CLOCK]),
    ("R10", "usage-recorded-not-capped", "사용량 기록(상한 없음, U-05)", scn_cli.r10, REAL_BASE + ["claude CLI(시험 프록시)", "시험 프록시 계량"],
     ["cost_units 단위 미정의, 금액은 기록 불가"]),
    ("R11", "handoff-quiescent-before-preserve", "정지 확인 뒤 보존", scn_handoff.r11, REAL_BASE, [STANDIN, "lsof 대신 /proc 검사"]),
    ("R12", "duplicate-delivery-noop", "중복 전달 noop", scn_envelope.r12, REAL_BASE + ["파일 큐", "HTTP(로컬)"], [STANDIN]),
    ("R13", "retry-new-idempotency-key", "재시도 새 키", scn_envelope.r13, REAL_BASE, [STANDIN]),
    ("R14", "preserve-manifest-same-function", "보존 manifest", scn_handoff.r14, REAL_BASE, [STANDIN]),
    ("R15", "preserve-failure-recoverable-stop", "보존 실패 정리", scn_handoff.r15, REAL_BASE + ["user namespace tmpfs(가득 찬 디스크)"],
     [STANDIN, "원격 거부는 hook 제어 파일로 만든 것"]),
    ("R16", "daemon-restart-during-handoff", "인계 도중 데몬 재시작", scn_handoff.r16, REAL_BASE, [STANDIN]),
    ("R17", "envelope-id-distinct-events", "봉투 식별", scn_envelope.r17, REAL_BASE, [STANDIN]),
    ("R18", "lease-issue-atomic-single-owner", "발급 원자성", scn_restart.r18, REAL_BASE, ["SIGKILL 시험(전원 차단 아님)"]),
    ("R19", "restart-ttl-expired-no-resend", "발급 직후 중단 뒤 TTL 경과", scn_restart.r19, REAL_BASE, [CLOCK]),
    ("R20", "restart-revoked-pending-void", "폐기된 pending", scn_restart.r20, REAL_BASE, [STANDIN]),
    ("R21", "restart-valid-pending-resend", "유효 pending 재전송", scn_restart.r21, REAL_BASE, [STANDIN, CLOCK]),
    ("R22", "restart-corrupt-record-returned", "손상 기록", scn_restart.r22, REAL_BASE, [STANDIN]),
]

REQUIRED_TEST_IDS = ["late-write-fenced", "late-result-rejected", "resume-after-interrupt", "duplicate-run-prevented",
                     "provider-scoped-switch", "hard-stop-heartbeating-job", "usage-recorded-not-capped",
                     "handoff-quiescent-before-preserve", "duplicate-delivery-noop", "retry-new-idempotency-key",
                     "preserve-manifest-same-function", "preserve-failure-recoverable-stop", "daemon-restart-during-handoff",
                     "envelope-id-distinct-events", "lease-issue-atomic-single-owner", "restart-ttl-expired-no-resend",
                     "restart-revoked-pending-void", "restart-valid-pending-resend", "restart-corrupt-record-returned"]
