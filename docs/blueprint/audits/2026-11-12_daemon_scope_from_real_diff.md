# Audit 6 — 데몬 PR 범위를 실제 diff에서 계산

2026-11-12. 개발 도구 T-OP-00·T-OP-09의 PR 범위 산정을 수정했다.
제품 추적은 BLUEPRINT §9.5·09 §5의 T-OP-08 축 5에 한정한다.

감리 지적: `core/observation.py`가 PR 기록의 범위(`changed_paths`)를 빌더가 스스로
신고한 `touched_paths`에서 가져왔고(결과 봉투 처리·`on_pr_opened`), docs-only
판정은 빌더가 단 `docs-only` 라벨을 신뢰했다. 코드를 바꾼 빌더가 경로 신고를
빼먹거나 라벨을 달면, 규칙·데몬 코드 변경이 감리 없이 `merged → done`으로
완료될 수 있었다.

이제 범위는 Git 어댑터의 실제 diff에서 온다. `core/ports.py`에
`Git.changed_paths(task_id, base_sha, head_sha)`를 추가했다(`merge-base(base, head)..head`,
rename은 삭제+추가로 봐 두 경로 모두 범위). `on_pr_opened`는 PR 기록을 만들거나
다시 쓸 때, `head_sha_changed` 관측은 head가 바뀔 때 이 조회로 `changed_paths`를
다시 계산한다. 빌더의 신고는 계속 범위 검사(`result_scope`)를 거치지만 PR 기록의
범위로는 쓰지 않고, 실제 diff와 다르면 `pr_claimed_paths_differ` 진단으로만
남는다. diff를 계산할 수 없으면(`QueryUnavailable`, 잘못된 자료형, 안전하지 않은
경로) `diff_unavailable`을 세우고 닫힌 쪽으로 실패한다: 즉시 감리 필수,
docs-only 아님(`pr_diff_unavailable` 진단). 빈 diff는 알 수 없는 범위가 아니지만
docs-only도 아니므로 구현 PR로 세어 감리 큐에 넣는다. `docs-only` 라벨은
`pr.labels`에 기록만 하고 판정에는 쓰지 않는다.

`audit_triggers.immediate_audit_paths`에 `tools/daemon/**`, `daemon_rules.json`,
정본 규칙 경로(`docs/blueprint/proposals/설계검토_결과/daemon_rules.json`)를
추가했다. docs-only는 모든 변경 경로가 `docs/**` 아래이면서 즉시 감리 경로가
하나도 없을 때만 성립하므로, `docs/**` 아래의 규칙 파일을 고치는 PR도 더는
감리를 건너뛰지 못한다. 글롭 없는 `daemon_rules.json`은 루트의 그 파일에만
일치하므로 현재 정본 위치의 전체 경로를 함께 적었다(패턴 읽기는
conflict_match(G29)와 같다).

[모의 회귀](../../../tools/tests/test_daemon_dry_run.py)의 `ScopeFromRealDiff`는
신고와 다른 diff가 기록·진단으로 남는 것, docs만 신고하고 데몬 코드를 바꾼 PR이
즉시 감리·구현 카운터로 가는 것, 규칙 파일 PR(정본 경로·루트 이름 모두)이
즉시 감리인 것, diff 부재·잘못된 자료형·경로 이탈의 닫힌 실패, head 갱신 뒤
범위 재계산, 새 경로를 뺀 규칙에서는 finding이 재현되는 것(변성 검사)을
검사한다. `DocsOnlyLandingCond`는 라벨이 착륙을 결정하지 않는 것으로 고쳤다.
[실제 실행기 어댑터 시험](../../../tools/daemon/runner_verify/tests/test_runner_verify.py)은
실제 클론에서 merge-base 계산·rename 삭제+추가·브랜치 이후 main 진전 제외·
알 수 없는 SHA의 `QueryUnavailable`을 확인하고, R8은 실제 프로세스 시나리오에서
빌더가 한 파일을 커밋하고 다른 파일을 신고했을 때 데몬이 실제 diff를 쓰는지
본다. M23은 규칙 파일 PR의 즉시 감리와 docs-only 라벨 무력화를 시나리오로
고정했다.

전체 회귀·시나리오·실행기 시험 결과와 재현 명령은
[실행 증거](../../../tools/evidence/audit6-daemon-scope-from-real-diff/README.md)에 기록한다.

증거 기록과 별개의 한계가 있다. 모의 Git의 diff 레지스트리는 모델이고, 실제
실행기의 `changed_paths`는 빌더 워크트리가 같은 객체 저장소를 공유하는 클론에서
`git merge-base`·`git diff --name-only --no-renames -z`로 계산한다. PR 본문·원격
호스트의 diff 조회는 하지 않으며 diff를 읽을 수 없을 때의 처리는 항상 감리 쪽이다.
규칙 파일의 범위 외 필드는 HEAD와 대조해 변함이 없음을 확인한 뒤
`o13_unchanged_gates.json`의 파일 해시와 갱신 이유만 고쳤다. 결정 게이트·
자격·전이·비용 정책은 그대로다.

이번 작업에서 Git 커밋·푸시·GitHub·실제 제공자 호출은 하지 않았다.
이 증거는 [09 §5](../proposals/설계검토_결과/09_제품목적_대응표.md)의 개발 도구
보강이며, P01~P19의 전 상품 수집·트윈·소비자 화면·첫 출시 완료 판정을
바꾸지 않는다.
