# Audit 3 — 원장 상한 영구 잠금 해소

대상: `audit3-r2-ledger-cap-lockout`, `tools/r2_budget.py::Ledger.read/append`, `Session`, `_cli`.
연결: Blueprint A1·L1~L2·M1, ADR-0017, 09 제품 목적 대응표 P02·P03.

## 발견과 수정

**발견 1 — 영구 잠금(진).** 실행마다 원장에 예약·정산 2건을 남기고, 체크포인트 이후 기록이 `max_ledger_records`(100)에 도달하면 `Ledger.read`가 `>=`로 거부한다. 뒤받침을 줄이는 `checkpoint` 명령도 같은 입장·예약 경로를 쓰므로 100건에서 그 명령의 예약 읽기가 거부되고, 99건에서는 자신의 예약이 100번째 자리를 쓴 뒤 `write_checkpoint`의 읽기가 거부된다. 정산 실행 약 50회(`sources` 워크플로 `reproduce`의 예산 실행 3회/회 기준 약 16회)면 아무 실행·명령도 뒤받침을 읽지 못하는 영구 잠금이었다.

**수정.** `Ledger`에 `over_limit_ok`(기본 False)를 두어 `read`의 `>=` 거부와 `append`의 기록 수 거부를 넘는다(순번 연속·해시 연결·정책·genesis 검증과 계량기 요청 한도는 그대로). `Session`/`start`에 `purpose`를 추가하고 `purpose == "checkpoint"`일 때만 세션 원장에 이 플래그를 준다. `_cli`의 `checkpoint` 명령만 이 우회 목적을 지정하므로 `audit`·`status`·`verify`·`upload` 등 일반 실행은 변함없이 상한에 거부된다.

복구 세션의 예약·정산 두 건은 상한을 넘어 쓰이지만, `checkpoint` 실행이 쓰는 체크포인트는 자신의 예약까지 덮는다. 그래서 100건에서의 복구는 예약 101번 → 체크포인트 101번 → 정산 102번으로 끝나고, 직후 일반 실행은 뒤따르는 기록 1건만 읽는다. `audit` 세션은 상한을 넘지 못한다. 감사는 뒤받침을 줄이지 않아 반복 실행이 체크포인트의 예약 전 읽기 입장 한도(Class B 110)까지 소진할 수 있기 때문이다. 100건에서 거부되면 체크포인트를 먼저 쓰고 감사를 실행한다. 예약 후 감사의 전체 이력 검증은 유지한다. 복구 세션도 예약 한도(전체·작업 caps)와 입장 한도·계량기는 그대로 지키며, 100건에서 예약 전 요청은 Class B 102~103회로 입장 한도 110 안에 든다.

**발견 2 — `tail()`/`append()` 상한 미검사(부분 진).** `tail()`은 상한을 검사하지 않지만 읽기 전용이다. 쓰기 경비는 `append`의 `count - base_seq >= limit` 검사(Audit 2 경계 수정, `9eb76fd`)로 일반 경로의 101번째 기록을 저장소 PUT 전에 막는다. 현재 코드에서 일반 세션이 원장을 101건으로 만드는 경로는 없으며 시험으로 고정했다. 상한을 넘는 쓰기는 위 체크포인트 복구 세션의 예약·정산 두 건뿐이다.

**발견 3 — 거부된 실행의 입장 기록(의도된 동작).** 입장 기록은 읽기 전에 쓰는 것이 원칙이다. 예약 전 요청의 상한이자 회계 근거이므로, 거부된 실행이 입장을 남기지 않으면 거부 반복이 공짜가 된다(이전 감리의 발견 1이 고친 결함). BUDGET.md §4에 명시됐고 기존 시험(`test_repeated_refused_runs_are_recorded_then_closed`, `test_ledger_get_exhausts_admission_before_reservation`)이 검증하므로 코드는 바꾸지 않는다.

## Fix round 1 — 반복 감사의 복구 여유 소진

초기 수정은 감사에도 상한 우회를 허용했다. 검토자가 100건에서 감사 5회 후 110건이 되고 체크포인트 예약 전 읽기가 `class_b would reach 111 > limit 110`으로 막힘을 재현했다. 우회 대상을 체크포인트로 한정했다. 입장·프로필·비용 한도는 올리지 않았다. 새 회귀는 90건에서 감사 5회 성공 → 100건에서 감사 6회 거부 → 체크포인트 101·정산 102 → 일반 읽기 및 전체 감사 재개를 확인한다. S3 스텁에서도 배포된 입장 한도와 `verify`·`status` 프로필로 감사 6회 거부 후 체크포인트 입장 Class B 102, 복구 및 일반 실행 재개를 확인한다. 거부된 감사의 입장은 계속 기록되지만 원장 예약·정산은 늘지 않는다.

최신 실행 결과: [fix-round1 증거](../../../tools/evidence/audit3-ledger-cap-lockout/fix-round1/README.md). 아래 초기 로그는 첫 수정 당시의 이력이며 이번 회귀 실행으로 대체된다.

## 회귀 증거

- [`test_r2_checkpoint.py`](../../../tools/tests/test_r2_checkpoint.py) `Lockout` 8개: 100건에서 일반 세션 거부·입장 기록·로컬 잠금 해제, `checkpoint` 세션의 예약 101·체크포인트 101·정산 102와 직후 기록 1건 읽기, 99건에서 자기 예약을 덮는 체크포인트, 기존 체크포인트 뒤 100건 해소(예약 199·체크포인트 199·정산 200), `start`/`finish` 명령 경로, 반복 `audit`의 상한 준수·체크포인트 복구·복구 후 전체 감사, 플래그 미지정 원장의 읽기·쓰기 거부 유지, 복구 세션의 전체 한도 거부 유지.
- 같은 파일의 `EndToEnd.test_checkpoint_session_at_the_cap_stays_metered_and_clears_it`: 루프백 S3 스텁에서 100건 원장의 복구 실행이 예약 전 Class A 5·Class B 102(입장 한도 안), 전체 실행이 프로필 한도 안이고, 직후 일반 실행의 원장 GET이 2회임을 서버 기록으로 대조한다.
- [`test_r2_budget.py`](../../../tools/tests/test_r2_budget.py) `LedgerRecordCap.test_tail_reads_the_cap_but_append_cannot_extend_it`: `tail()`은 실제 꼬리를 보고하고 `append()`가 101번째 PUT 전에 거부해 원장이 100건에서 멈춤을 고정한다.
- [수정 전 로그](../../../tools/evidence/audit3-ledger-cap-lockout/before.log): `git show HEAD:tools/r2_budget.py`를 메모리에만 로드해 실행했다. 100건 원장에서 `write_checkpoint`와 일반 세션이 모두 `ledger has 100 records ... >= 100`으로 거부(영구 잠금 재현), 신규 회귀 10개 중 8개 오류(`purpose`·`over_limit_ok` API 부재), `tail`/`append` 대조 시험은 통과(쓰기 경비가 이미 있었음을 확인), S3 스텝 시험 1개는 격리 실행에서 boto3 부재로 건너뜀.
- [수정 후 로그](../../../tools/evidence/audit3-ledger-cap-lockout/after.log): 같은 절차에서 일반 원장·일반 세션은 계속 거부되고, `purpose="checkpoint"` 세션은 예약 101·체크포인트 101·정산 102를 쓴 뒤 다음 읽기가 `base_seq 101`·기록 `[102]`임을 확인한다. 신규 회귀 10개 모두 통과.

## 검증 범위

임시 로컬 원장과 루프백 S3 스텁으로 시험했다. 실제 R2에 접근하거나 자격 증명을 사용하지 않았고, 커밋·푸시·GitHub 호출도 하지 않았다. 모두 이 작업 트리에서 실행했다.

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_r2*.py' -v` | 117개 통과, 종료 0 | [예산·체크포인트 로그](../../../tools/evidence/audit3-ledger-cap-lockout/budget-tests.log) |
| `env -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -v` | 1,220개 실행, 통과·건너뜀 6, 종료 0 | [전체 Python 로그](../../../tools/evidence/audit3-ledger-cap-lockout/python-tests.log) |
| `cargo test --all --locked` | 466개 통과·실패 0·1개 무시, 종료 0 | [Rust 로그](../../../tools/evidence/audit3-ledger-cap-lockout/rust-tests.log) |
| `cargo fmt --all -- --check`, `cargo clippy --all-targets -- -D warnings` | 모두 종료 0 | [Rust 린트 로그](../../../tools/evidence/audit3-ledger-cap-lockout/rust-lint.log) |
| 어휘·검증 자료·검증기 selftest·설계 수치(`blueprint_counts`)·잠금 규칙 CLI·설계 묶음 `spec_check`·데몬 `dry_run --require-all`·`git diff --check` | 모두 종료 0 | [정합성 검사 로그](../../../tools/evidence/audit3-ledger-cap-lockout/consistency-checks.log) |

Python 건너뜀 6개는 비공개 로컬 원본이 필요한 기존 검사 5개와 설치된 botocore에는 해당하지 않는 구버전 검사 1개다. 신규 회귀 시험은 모두 실행·통과했다.

추가 `tools/ci/tests` 실행에서는 의존성 검사 시험 2개가 기존 DEP-ZONE 위반 3건(`packages/ontology` → `onjeon-rules-engine`)으로 실패했다. 관련 파일(`packages/ontology/Cargo.toml`, `packages/ontology/tests/common/mod.rs`, `packages/ontology/tests/fixture_origin/main.rs`, `infra/ci/deps.json`)은 모두 HEAD와 바이트 단위로 같고 이 노드는 해당 의존성 정책·코드를 바꾸지 않는다([정합성 검사 로그](../../../tools/evidence/audit3-ledger-cap-lockout/consistency-checks.log)).

이 증거는 원본 보관 도구의 비용 통제 경계에 한정한다. 실제 공시 확보율·R2 관측 목록 대조·화면·출시 완료 증거를 대신하지 않으며 P02·P03을 완료 처리하지 않는다.
