# Owner ruling — D-04 (2026-10-13 17:53 KST, 준태님)

> "R2 토큰 폐기안한다. 나의 결정이다" — 준태님, 2026-10-13 17:53 KST

D-04(R2 운영 원칙과 토큰 폐기): 대화에 노출된 R2 토큰은 폐기하지 않는다. 사용자(소유자) 본인의 결정이다.
Fable 대리 결정이 아니다. docs/decisions PR로 기록한다.

---

# DEC-D-04 D-04 소유자 결정 기록: R2 토큰 폐기하지 않음

상태: 기록(소유자 직접 결정, 2026-10-13 17:53 KST) | 결정자: 준태님 (owner) | 대상 결정 ID: `D-04` (`DEC-D-04`)

이 문서는 **준태님(사용자·소유자 본인)이 2026-10-13 17:53 KST에 직접 내린 `D-04` 결정**을 위 원문 그대로 기록한다. Fable 대리 결정이 아니며, 기록자는 결정을 다시 판단하거나 고치지 않았다.

## 기록 항목

| 항목 | 값 |
|---|---|
| decision_id | `D-04` (`DEC-D-04`) |
| decided_by | 준태님 (owner, 사용자·소유자 본인 결정 — Fable 대리 결정 아님) |
| time (`decided_at`) | 2026-10-13 17:53 KST |
| decision | 대화에 노출된 R2 토큰은 폐기하지 않는다 (`"R2 토큰 폐기안한다. 나의 결정이다" — 준태님, 2026-10-13 17:53 KST`) |
| scope | R2 운영 원칙 `BP-D-16`~`BP-D-18`은 변경 없음. 대화에 노출된 R2 토큰 폐기만 수행하지 않는다 |
| consequence | 이 문서는 "대화에 노출된 R2 토큰을 폐기하지 않는다"는 소유자 결정을 기록할 뿐이며, 노출된 토큰의 재사용이나 R2 접근 제한 해제를 승인하지 않는다. 정본 `docs/blueprint/DECISIONS.md` `O13`·`tasks.json`·`05_VM실행준비.md` §4 및 데몬 `decisions_recorded`는 이 PR에서 변경되지 않으므로, 이 문서 자체로 `T-OP-04`(`start: [D-04]`)나 `T-DT-01`·`T-DT-04`·`T-OP-02`(`real_data: [D-04]`) 관문이 열리지 않는다(단, `T-DT-01`·`T-DT-04`·`T-OP-02`의 모의·로컬 경로 작업은 `real_data_allowed = false`로 시작·진행·병합 가능) |
| revisit_if | 소유자(준태님)가 R2 접근 자격(별도 범위 제한 토큰 발급 또는 `O13`·`tasks.json` `D-04` 관문 조건 개정 및 `decisions_recorded` 등록)이나 토큰 폐기·재발급을 후속 지시할 때, 비인가 접근·원장/청구 이상이 감지될 때, 또는 `O14`·`O17` 관문 및 `BP-D-16`~`BP-D-18` 개정 시 |

## 적용 범위 (Scope: BP-D-16~BP-D-18 유지)

- **바뀌는 점:** 대화에 노출된 R2 토큰을 폐기하지 않는다(토큰 폐기 미수행).
- **바뀌지 않는 점 (그대로 유지되는 R2 운영 원칙 `BP-D-16`~`BP-D-18`, `docs/blueprint/DECISIONS.md` 및 ADR-0016·ADR-0017 사용자 결정):**
  - `BP-D-16` (ADR-0016): 원본 보관소 제공자를 Cloudflare R2(`onjeon-raw-sources`, `onjeon-derived-sources`)로 하고 `BP-D-14`의 나머지 규칙(원본·파생 버킷 분리, SHA-256 경로, 같은 URL의 바뀐 문서는 새 원본으로 추가, 덮어쓰기 금지, 비공개, 저장 시 암호화, 수집 주체 삭제 권한 없음, 개인 계약·건강·가족력·DNA 자료 금지, 보존과 재배포 분리, 보관본 재현 검사와 현재 출처 변경 감지 분리, 무기한 잠금 금지와 승인 전 잠금 금지)을 유지한다.
  - `BP-D-17` (ADR-0017): 대량 수집 전 비용 제한(실행별 제한 + 원장 누적 사용량을 이용한 폭주 완화 장치)을 구현하고, 최초 작업은 고정 119키(원본 58, 파생 v2 61)의 업로드·대조만 허용한다. 총 바이트·API 요청·재시도·실행 시간을 실행 전에 제한하며, 한도 소진 또는 한도 기록(원장) 조회 실패 시 중단하고, 재실행·병렬 실행은 원장 기준으로 한도에 들어간다. 계정 전체 과금 상한이나 모든 실행의 요청 상한을 보장한다고 표현하지 않으며 원장에 남지 않는 요청은 도구 내부 한계로 적고, 예산 알림을 과금 차단으로 표현하지 않는다.
  - `BP-D-18` (ADR-0017): R2 초기 운영은 지정 실행 환경 하나, 동시 실행 1개, 수동 실행만 허용한다. 대량 자동 수집은 별도 관문(`O17`)으로 둔다.
- **이 기록의 경계:**
  - 이 문서는 소유자의 결정 원문을 기록할 뿐이다. 정본 결정 원장(`docs/blueprint/DECISIONS.md` `O13`), 작업 명세(`docs/blueprint/proposals/설계검토_결과/tasks.json`), VM 실행 준비(`05_VM실행준비.md` §4), 데몬 상태 저장소의 `decisions_recorded`(`daemon_rules.json`의 `decision_record`: `{decision_id, recorded_at, recorded_by, source_ref}`)는 이 PR에서 수정하거나 기록하지 않는다.
  - 비밀값(실제 토큰 문자열)은 저장소·문서·로그·봉투 어디에도 기록하거나 출력하지 않는다. 이 PR은 `docs/decisions/DEC-D-04.md` 한 파일만 기록하며 다른 파일은 변경하지 않는다.

## 과제 관문 영향 (Consequence for T-OP-04 / T-DT-01 / T-DT-04 `real_data` gates)

소유자 결정 원문은 **"대화에 노출된 R2 토큰은 폐기하지 않는다"**는 것뿐이며, 노출된 토큰의 재사용을 허가하거나 R2 접근 관문을 면제하지 않는다. 현재 저장소의 관련 정의(`DECISIONS.md` `O13` "토큰 폐기 전 추가 수집 금지", `설계검토_결과/README.md` §6 및 `03_작업명세.md` §5의 D-04 행 "대화 노출 R2 토큰 폐기·범위 제한 토큰 재발급"(`tasks.json` `decision_index.D-04`는 관문 과제 목록만 둔다), `05_VM실행준비.md` §4 "재사용·출력 금지. 폐기 전까지 T-OP-04는 시작 불가")와 데몬 규칙(`daemon_rules.json`: `decision_record`가 `decisions_recorded`에 등록되어야 관문 충족)에 따른 과제별 영향은 다음과 같다.

- **`T-OP-04`** (`decision_gates.start = ["D-04"]`, `decision_gates.merge = ["O14"]`):
  - **시작 관문(`start: ["D-04"]`) 미해제:** `T-OP-04`의 차단 조건(`blocked_by`: "시작: D-04(토큰 폐기·재발급 전에는 R2에 접근하지 않음). 병합: O14(잠금 승인)")과 `05_VM실행준비.md` §4는 노출 토큰의 폐기(사용자), 재사용·출력 금지, 폐기 전 `T-OP-04` 시작 불가를 정하고(범위 제한 토큰 재발급은 `O13`과 위 D-04 행에 있다), 데몬은 `decisions_recorded`에 `D-04`가 등록되어야 `blocked → queued`로 전이한다. 이 마크다운 문서만으로는 `decisions_recorded`가 갱신되지 않고 R2 접근 자격도 부여되지 않으므로 `T-OP-04`의 시작 차단은 그대로 유지된다.
  - **병합 관문(`merge: ["O14"]`):** `T-OP-04`의 병합 관문은 `O14`(R2 버킷 잠금 규칙 승인) 단일 관문이며 그대로 유지된다.
- **`T-DT-01` 및 `T-DT-04`** (`decision_gates.real_data = ["D-04"]`, `start = []`, `merge = []`, `release = []`):
  - **실데이터 관문(`real_data: ["D-04"]`) 미해제:** 두 과제의 실제 R2 쓰기·보존 단계는 `tasks.json`(`T-DT-01` `blocked_by`: "실데이터: R2 실제 쓰기만 D-04(토큰 폐기·재발급)에 막힌다", `T-DT-04` `blocked_by`: "실제 R2 보존은 D-04") 및 정본 `DECISIONS.md` `O13`("토큰 폐기 전 추가 수집 금지")에 묶여 있다. 이 결정 기록만으로는 `real_data_allowed = true`가 되지 않으며 실제 R2 쓰기는 계속 차단된다.
  - **로컬·모의 작업 및 병합은 차단되지 않음(`r2-local-work-allowed`):** `daemon_rules.json` `gate_semantics.real_data`에 따라 `real_data` 관문은 과제의 시작(`blocked → queued`), 코드 작성, 로컬 시험, 병합을 막지 않는다. `real_data_allowed = false` 봉투로 `T-DT-01`의 로컬 객체 저장소 경로·Rust 보관 클라이언트 적합성 시험과 `T-DT-04`의 분모 열거 어댑터·로컬 시험은 정상 진행·병합할 수 있다.
  - 참고: 대량 자동 수집 관문 `O17`은 `T-DT-05`의 출시·활성화 관문(`decision_gates.release = ["O17"]`, 예약 실행 on 전환 차단)이며 `T-DT-01`·`T-DT-04`의 `decision_gates`가 아니다.
- **`T-OP-02`** (`decision_gates.real_data = ["D-02", "D-04"]`):
  - `(a)` 코드 경로 관통(`environment = test` 모의 제공자·로컬 기반)은 `D-02`·`D-04` 없이 `real_data_allowed = false`로 진행 가능하며, `(b)` 실제 데이터 관문 통과 판정은 `D-02`와 `D-04`(실제 R2 보존 및 `decisions_recorded` 등록)가 모두 해결될 때까지 차단된 상태로 남는다.

## 재검토 조건 (Revisit Trigger)

1. 소유자(준태님)가 노출된 토큰을 폐기하지 않은 상태에서 실제 R2 접근에 사용할 자격(예: 별도 범위 제한 토큰 재발급 여부)과 정본 `DECISIONS.md` `O13`·`tasks.json` `decision_index.D-04` 관문 조건 개정 및 데몬 `decisions_recorded` 등록 여부를 후속 결정하거나, 반대로 토큰 폐기·재발급을 새로 지시할 때.
2. 원장(`onjeon-budget-ledger`) 기록과 Cloudflare R2 사용량·청구 대조에서 비인가 호출이나 이상 징후가 관측될 때.
3. `O14`(R2 버킷 잠금 규칙 승인, `T-OP-04` 병합 관문) 또는 `O17`(대량 자동 수집 관문, `T-DT-05` `release` 관문) 결정 시점에 R2 운영 환경·토큰 권한 범위를 확정할 때.
4. `BP-D-16`~`BP-D-18`의 R2 운영 원칙을 개정하는 후속 결정이나 ADR이 채택될 때.
