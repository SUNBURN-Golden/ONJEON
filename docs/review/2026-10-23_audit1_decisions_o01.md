# Audit 1: 원장 O01(공제·우체국보험 포함 여부)은 ADR-0018이 이미 결정했다

검증일: 2026-10-23. 작업 트리: `audit1-decisions-o01-close`. 최신 갱신: fix round 5.

| 위치 | 상태 | 비고 |
|---|---|---|
| `docs/blueprint/DECISIONS.md` §3 O01 행(52행) | **미수정, 보호 문서** | 아래 교체안. [한 행 패치](2026-10-23_audit1_decisions_o01.patch) |
| `tools/tests/test_decisions_o01.py` | **추가** | 원장의 세 상태(미수정·수정됨·수정 후 패치 삭제) 통과. 회귀·제3의 문구·행 중복은 실패. 닫힌 상태 검사는 CI가 매번 원장 사본에 패치를 적용해 실행 |
| `docs/review/evidence/audit1-decisions-o01/` | **추가** | 라운드별 명령·전체 출력·종료 코드 (`round1/`~`round5/`) |

**finding은 아직 닫히지 않았다.** `docs/blueprint/DECISIONS.md`는 이 작업의 수정 금지 목록에 있고
감독 장치는 이 과제에 `allowed_paths` 예외가 없어 그 파일의 어떤 변경도 거부한다(변경하면 라운드 자체가
거부되고 PR은 갱신되지 않는다). 그래서 원장 행은 그대로이고, 고친 행은 패치로 두고 시험이 실제 원장과 대조한다.
새 제품·법률·비용·운영 결정은 필요 없다(ADR-0018 §4가 이미 결정한 범위를 원장에 옮기는 일).
`DECISION_REQUIRED.md`는 생성 조건(비가역·돈·법·비밀·운영)에 해당하지 않아 만들지 않았다.
감독 장치 설정상 이 라운드가 이 과제의 마지막 수정 라운드(일반 3 + Fable 2)라, 운영자 조치 없이는 과제가 보류(PARKED)된다.

같은 52행을 겨냥한 과제가 더 있다(`audit2-blueprint-open-decisions-stale`, `audit4-decisions-ledger-sync`,
`audit5-decisions-ledger-sync`, `audit11-stale-docs-batch`). 모두 같은 보호 경로에 막히므로 아래 경로 중 하나를
한 번 열면 그 과제들의 O01 부분도 같이 끝난다.

## 원장 수정 경로(운영자)

다음 둘 중 하나로 닫힌다. 어느 쪽이든 추가 변경 없이 `tools/tests/test_decisions_o01.py`가 통과한다
([states.log](evidence/audit1-decisions-o01/round5/states.log) 상태 2·3).

1. 과제 `audit1-decisions-o01-close`에 `allowed_paths`를 주고 fix round를 한 번 더 돌린다.
   `allowed_paths`가 있으면 목록 밖 파일도 거부되므로 이 가지가 바꾸는 파일을 전부 적어야 한다:
   `docs/blueprint/DECISIONS.md`, `docs/review/2026-10-23_audit1_decisions_o01.md`,
   `docs/review/2026-10-23_audit1_decisions_o01.patch`, `docs/review/evidence/audit1-decisions-o01/**`,
   `tools/tests/test_decisions_o01.py`. 그 라운드가 할 일은 세 가지다:
   `git apply docs/review/2026-10-23_audit1_decisions_o01.patch`, `git rm docs/review/2026-10-23_audit1_decisions_o01.patch`
   (패치가 없어지면 시험은 닫힌 상태만 허용해 원래 질문으로 되돌리는 회귀를 막는다), 위 표의 "미수정" 행 정리.
2. 원장을 고칠 수 있는 사람이 `main`에서 같은 패치를 적용한다. 이 PR은 시험·근거만 병합해도 CI가 깨지지 않는다.
   패치 파일을 같은 커밋에서 지우면 시험은 그때부터 닫힌 상태만 허용한다(지우지 않아도 통과한다).

## 교체안

52행을 아래로 바꾼다(O13 양식: 질문에 취소선, 결정 근거, 확정 범위, D11 구현 작업 구분 보존, 오래된 후속 열 정리).

```
| O01 | ~~공제·우체국보험의 포함 여부~~ → D19·ADR-0018 §4로 결정. 우체국보험 포함(기관 유형 구분), 공제 제외(확보율 분모에서도 제외). 전체 기관·소스 목록 작성 자체는 구현 작업(D11) | 제품 책임자 | ADR-0018로 확정 | 우체국보험 포함(기관 유형 구분) / 공제·확보율 분모 제외 |
```

근거: [ADR-0018 §4](../decisions/ADR-0018-보험-데이터-지식-기반의-정체성과-범위.md#4-포괄-범위)
(우체국보험 **포함**·기관 유형 구분, 공제 **제외**·확보율 분모에서도 제외), 같은 ADR의 "결과" 절
(열린 결정 "공제·우체국보험 포함 여부"를 닫는다), [원장 D19](../blueprint/DECISIONS.md#1-확정-방향).
"결정 시점 M3 확장 전"과 "별도 분모로 조사"는 결정 전의 임시 규칙이라 함께 지운다.

## 시험 설계

`tools/tests/test_decisions_o01.py`는 실제 원장·실제 ADR·커밋된 패치를 읽는다. skip·expectedFailure 없음. 시험 15개, 네 묶음.

- `Premise`: D19 행이 결정 범위를 적고, ADR-0018 §4 표가 우체국보험 포함·공제 제외를 적고, "결과" 절이 열린 결정을 닫는다.
- `PatchFile`: 패치는 원장 한 파일·hunk 하나·O01 한 행 교체. `-` 행은 감사가 지적한 문구("M3 확장 전", "별도 분모로 조사")이고
  닫힌 행 검사에 **실패**한다. `+` 행은 닫힌 행 검사를 만족한다.
- `LedgerCopyAfterPatch` (닫힌 상태의 CI 검증): 매 실행마다 패치를 원장 사본에 적용해(`git apply`와 같은 블록 치환) 결과가
  닫힌 O01 행 하나이고 바뀐 행이 정확히 그 한 행임을 본다. 같은 사본으로 패치를 지운 뒤 원래 행으로 되돌린 회귀,
  질문만 바꿔 쓴 제3의 문구(패치 유무 모두), 닫힌 행 중복이 각각 실패함을 확인한다.
- `O01Row` (실제 원장): O01 행은 정확히 하나·다섯 열이며 둘 중 한 상태다.
  - 미수정: 패치 파일이 있고, 행이 패치의 `-` 행과 바이트 단위로 같고, 패치의 이전 블록이 원장에 그대로 있어 적용 가능하며,
    패치의 `+` 행이 닫힌 행 검사를 만족한다. 원장이 흘러 패치가 안 맞게 되면 실패한다.
  - 수정됨: 행이 취소선·D19·ADR-0018 §4·확정 범위·D11 구분을 담고 "M3 확장 전"·"별도 분모로 조사"가 없다.
  - 그 밖의 문구는 실패한다. 패치 파일이 없으면 미수정 상태도 실패한다.
- 패치 파일이 없으면(원장을 닫은 뒤) 패치를 읽는 시험들은 skip 대신 "원장 O01 행이 닫혀 있다" 검사로 바뀐다.

닫힌 행 검사: 다섯 열, `~~공제·우체국보험의 포함 여부~~`로 시작, D19·ADR-0018 §4·"우체국보험 포함(기관 유형 구분)"·
"공제 제외(확보율 분모에서도 제외)"·D11 구분 포함, 책임 역할 "제품 책임자", 결정 시점에 ADR-0018 있고 "M3 확장 전" 없음,
허용/차단 열에 "우체국보험 포함"·"공제"·"분모 제외" 있고 "별도 분모로 조사" 없음.

expectedFailure를 쓰지 않은 이유: 원장이 고쳐지는 순간 CI가 깨진다. 실제 원장에서 실패하는 시험을 두지 않은 이유:
감독 장치는 시험 실패를 라운드 실패로 처리해 PR이 갱신되지 않는다(round 1~3). 남는 한계: 패치 파일이 있는 동안은
실제 원장의 오래된 행을 받아들인다. 그래서 닫는 라운드가 패치를 지우도록 위 경로에 적었다.

## Fix round 5 실행 결과

모든 명령은 저장소 루트에서 실행했다. 로그는 [round5](evidence/audit1-decisions-o01/round5/)에 명령·전체 출력·종료 코드로 둔다
(작업 트리 절대 경로는 `<repo>`, 임시 경로는 `<tmp>`로 바꿨다).

| 명령 | 결과 | 전체 로그 |
|---|---|---|
| `python3 -I -m unittest discover -s tools/tests -p test_decisions_o01.py -v` | 종료 0: 15개 통과(원장 미수정 상태) | [O01](evidence/audit1-decisions-o01/round5/o01-tests.log) |
| 여섯 상태 증명(원장 사본): 미수정 → 통과, `git apply` 후 → 통과, 적용 후 패치 삭제 → 통과, 패치 삭제 후 원래 행 복원 → 실패 11, 질문만 바꿔 쓴 행 → 실패 6, 닫힌 행 중복 → 실패 4 | 모두 예상대로 | [states](evidence/audit1-decisions-o01/round5/states.log) |
| `python3 -m unittest discover -s tools/tests -v` | 종료 0: 566개 실행, 실패 0·오류 0·skip 7 | [Python](evidence/audit1-decisions-o01/round5/python-tests.log) |
| `cargo test --all --offline --no-fail-fast` | 종료 0: 388개 통과·실패 0·ignored 1 | [Rust](evidence/audit1-decisions-o01/round5/cargo-tests.log) |
| `cargo fmt --all -- --check`, `cargo clippy --all-targets --offline -- -D warnings` | 모두 종료 0 | [검사](evidence/audit1-decisions-o01/round5/checks.log) |
| `tools/vocab_check.py`, `tools/validation_check.py`(+`--selftest`), `spec_check.py`, `git apply --check`, `git diff --check`(원문 출력을 보존하는 로그·패치 파일 제외), 보호 경로 diff 검사 | 모두 종료 0 | [검사](evidence/audit1-decisions-o01/round5/checks.log) |

기존 skip 7건은 round 4와 같다(비공개 원본/도구 미지정 5건, botocore의 conditional put 지원 1건, 온톨로지 runner의 오프라인 의존성 부재 1건).

## 이전 라운드 기록

- Fix round 4 ([round4](evidence/audit1-decisions-o01/round4/)): 두 상태 시험 7개로 바꿔 처음으로 전체 시험이 통과했다
  (Python 558, Rust 388, fmt·clippy·검사 모두 종료 0). 두 상태 증명은 [twostate.log](evidence/audit1-decisions-o01/round4/twostate.log).
- Fix round 1~3 ([round1](evidence/audit1-decisions-o01/round1/), [round2](evidence/audit1-decisions-o01/round2/),
  [round3](evidence/audit1-decisions-o01/round3/)): 원장을 그대로 읽어 실패하는 시험을 두고 수정 금지 예외를 요청했다.
  감독 장치는 시험 실패를 라운드 실패로 처리하므로 그 방식으로는 닫힐 수 없었다. 세 라운드 모두 O01 시험 2개 실패(원장 미수정)와
  실행 환경의 소켓 권한 오류(Python `test_r2_budget.EndToEnd`·`test_r2_checkpoint.EndToEnd` 6건, Rust `http_conformance` 1건)가 있었고,
  `git apply --check`·어휘 검사·검증 자료 검사·`git diff --check`·보호 경로 diff 검사는 통과했다. 그 로그는 실패 기록이며 현재 상태가 아니다.

## 리뷰 지적과 처리

round 4 리뷰(PR #169, head 5c9a619):

- 차단 1 / P1(원장 52행 미수정, 수락 조건 미충족): **미해결.** 보호 경로라 이 작업 트리에서 닫을 수 없다. 위 "원장 수정 경로"대로 운영자 조치가 필요하다.
- 비차단 3(round 1 실패 로그가 최상위에 있어 혼동): 최상위 로그를 `round1/`로 옮겼다. 현재 로그는 `round5/`다.
- 비차단 4 / P2(수정됨 가지가 커밋된 로그로만 증명됨, 시험이 미수정 상태를 받아들여 회귀 가능): `LedgerCopyAfterPatch`가 CI에서 매번
  패치를 사본에 적용해 닫힌 가지를 실행하고, 오래된 행이 닫힌 행 검사에 실패함을 `PatchFile`이 확인한다. 미수정 상태는 패치 파일이
  있는 동안만 허용되므로 닫는 라운드가 패치를 지우면 원래 질문으로 되돌리는 회귀는 실패한다(states 상태 4). 패치가 있는 동안
  실제 원장의 오래된 행을 받아들이는 점은 남는다(이유는 "시험 설계" 끝).
- 비차단 2(두 상태 시험·패치는 타당): 변경 없음.

최초 리뷰(PR #169, head 154bd60):

- 지적 1·4(원장 미수정, 보호 문서): 미해결(위와 같음).
- 지적 2(시험이 트리에 없음): `tools/tests/test_decisions_o01.py`를 추가했고 CI의 `unittest discover`가 자동 발견한다.
- 지적 3(근거를 확인할 수 없음): `/tmp` 로그 대신 저장소 내 로그로 바꿨다.
- 지적 5(비차단: 문구·후속 열): 패치가 결정 시점·허용/차단 열까지 갱신한다. "두 상태에서 통과하는 시험" 제안은 round 4에서 적용했다.
