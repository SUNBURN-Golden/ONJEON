# 데몬 모의 작업 도구 (T-OP-00, dry_run)

`daemon_rules.json`을 데이터로 읽어 05 §5의 M1~M44를 공용 전이·검증 코어(`core/`)로 실행하고, 시나리오마다 기대 전이와 실제 전이를 나란히 보여 준다. 개발 도구다. 출시 완성품의 일부가 아니고(09 §5), 완료가 가동 승인이 아니다.

```sh
python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json \
  --tasks tools/daemon/mock_tasks.json --scenario all [--report <경로>.json] [--quiet] [--require-all]
python3 -m unittest tools/tests/test_daemon_dry_run.py
```

`--scenario`는 `all`, M 번호(`M41`), 또는 필수 시험 ID(`restart-ttl-expired-no-resend`)를 받는다. 하나라도 기대와 다르거나 시나리오가 예외로 멈추면 종료 코드는 1이다. 실행 기록과 보고서는 `reports/`에 있다. `reports/dry_run.log`가 보고서이고, 통과한 검사도 기대·실제 열(전이 열 포함)을 줄이지 않고 다 적는다. JSON이 필요하면 `--report`로 만든다.

## 구성

| 경로 | 내용 |
|---|---|
| `core/` | 공용 코어. 표준 라이브러리만 쓰고, 바깥 세계는 `core/ports.py`의 어댑터 인터페이스로만 만난다. 모의 분기 문자열이 없다(정적 검사). 실제 실행기(T-OP-09)는 어댑터만 바꿔 같은 코어를 부른다 |
| `core/rules.py` | `core_contract.reads`로 만든 규칙 뷰. 설명 키(`when` 문장·`note`·`_*`)는 버린다. 읽기 목록 밖의 값은 `OUTSIDE_READS` 네 개뿐이고 모두 명세 공백 G51로 보고한다 |
| `core/transition_engine.py` | `transitions[]`의 `cond`·`guard`·`side_effects`·`return_code`·`on_cond_fail`, `noop_rules`, 가드 `on_fail` |
| `core/effects.py` | 부수 효과 id별 처리. 어떤 id를 어떤 순서·인자로 실행할지는 데이터다 |
| `core/lease.py` | `issue_lease`(세대를 바꾸는 유일한 곳), 임대 잠금, `lease_guards`, outbox 발송·재발송 |
| `core/fencing.py`, `core/envelope_validator.py` | `accept_envelope`, `fenced_write`, `validate_instruction`, 지시 봉투 작성, 수신 측 검증 |
| `core/handoff.py`, `core/recovery.py` | 인계 단계와 실패 처리, 재시작 복구, 정상 만료, 상태 손상 |
| `core/secret_scan.py` | 비밀값 패턴의 세 검사 지점. 일치한 문자열은 기록하지 않는다 |
| `core/observation.py` | CI·PR·리뷰·감리·병합 관측·결정 기록·선행 과제. 아래 "관측 계층" 참고 |
| `mock_adapters.py`, `mock_env.py` | 가상 시계, 메모리 저장소, 모의 빌더(수신 측 검증, `real_data_allowed`에 따른 단계 실행), 모의 Git(트리 OID 모델), 모의 리뷰어. 네트워크·CLI·실제 저장소·모델 호출 없음 |
| `mock_tasks.json` | 시험 전용 fixture(`origin=fixture`, `fixture_only=true`). 모의 과제(T-MOCK-*)와 모의 빌더(이름·실행기·계열). 규칙의 수치(ttl_s·heartbeat_s·max_attempts 등)는 두지 않는다(G01). 과제 `limits`(max_wall_s·max_retries)는 확정되지 않은 초안 기본값을 따라 쓴 fixture 값이고 제품 값이 아니다(G47) |
| `scenarios.py`, `scenarios_flow.py`, `bench.py` | M26·M28~M30·M33~M44(임대·봉투·재시작·인계)와 M1~M25·M27·M31·M32(큐에서 병합 관측·정기 감리까지, 중단·권한) |
| `static_checks.py` | 병합 API·네트워크·CLI·벽시계·스케줄러·두 번째 해시·모델 식별자·비용 상한이 없음, 세대 대입은 `issue_lease` 안에서만 |
| `spec_gaps.py` | 명세 공백 목록과 코어가 택한 해석 |

## 관측 계층(명세 공백 G51~G55)

`blocked→queued`와 PR 이후 전이(전이표 0, 43~85행)에는 `cond`가 없다. 어떤 사건을 낼지 정하는 규칙은 `when` 문장, `audit_triggers.immediate_rules[].rule`, `record_separation.merge_observation_fields._rule` 같은 문장이거나 읽기 목록 밖에 있다. 코어가 문장을 읽지 않으므로 `core/observation.py`가 04 §2.2·§4·§5의 규칙을 코드로 적용한다. 행이 하는 일은 여전히 전이표가 정한다. 이 해석은 모두 `spec_gaps.py`의 G51~G55에 적었고, 설계 담당이 구조화 필드로 옮기면 이 모듈을 그 필드를 읽도록 바꾼다.

## 현재 결과

- 필수 시험 ID 33개 전부와 M1~M44(M10a·M10b·M18a·M18b 포함)를 실행한다. 검사 수·실패 수는 `reports/dry_run.log`의 요약을 본다.
- G29~G50: 코어가 새 필드를 읽는다(`spec_gaps.py`의 `core_reads`). G47만 일부다. 기본값이 든 `envelopes.instruction.limits`를 `core_contract.reads`에 넣는 일은 `daemon_rules.json` 변경이라 이 과제의 허용 경로 밖이다. 코어는 과제 정의의 limits를 쓴다.
- 문장에서 꺼낸 토큰은 0종이다(`Rules.token_log`).
- 새 명세 공백 G51~G57은 열려 있다. 설계 담당이 정할 일이다.

## 증거 기록(reports/)

`reports/dry_run.log`(보고서)와 `reports/unittest.log`(시험 실행)의 머리말은 `generated from parent commit <sha> + tree hash of tools/daemon sources`로 시작한다. 로그는 커밋 전에 만들므로 로그 자신이 들어갈 커밋의 SHA를 적을 수 없다. 그래서 부모 커밋(이 변경을 얹은 바로 앞 커밋)과, 그 위에 얹은 소스의 내용 해시를 적는다. PR head는 부모 커밋에 이 변경 커밋 하나를 더한 것과 정확히 같다. 해시는 `tools/daemon/`(`reports/`·`__pycache__` 제외)과 `tools/tests/test_daemon_dry_run.py`의 파일 내용으로 만들고, 같은 소스면 같은 값이 나온다. 저장소 루트에서 다시 계산한다.

```sh
{ find tools/daemon -path tools/daemon/reports -prune -o -path '*/__pycache__' -prune -o -type f -print; \
  echo tools/tests/test_daemon_dry_run.py; } | LC_ALL=C sort | xargs sha256sum | sha256sum
```

`Cli.test_evidence_logs_name_the_parent_commit_and_source_hash`가 두 로그의 해시가 현재 소스와 맞는지 확인한다. 소스를 고치면 로그를 다시 만들어야 한다.

## 이 모의 검증이 증명하지 않는 것

실제 프로세스·파일 시스템(잠금·rename·fsync)·Git·원격 푸시·네트워크·CLI·모델 호출, 다중 프로세스 경쟁(스레드와 잠금으로만 시험), 실제 제공자 청구와 사용량 기록의 대조. 모의 Git의 트리 해시는 모델이다. 이것들은 T-OP-09(실제 실행기)에서 확인한다.
