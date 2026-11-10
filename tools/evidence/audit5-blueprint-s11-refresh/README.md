# audit5-blueprint-s11-refresh 검증 증거

노드: `audit5-blueprint-s11-refresh`. 기록일: 2026-11-10(UTC).
대상: [BLUEPRINT](../../../docs/BLUEPRINT.md) §11과
[감리 기록](../../../docs/blueprint/audits/2026-11-10_blueprint_s11_refresh.md).

## 실행 명령과 결과

| 명령 | 결과 | 로그 |
|---|---|---|
| `python3 -I -m unittest discover -s tools/tests -p 'test_blueprint_s11_refresh.py' -v` (수정 전) | 9건 중 5건 실패, 지적 문구·경로·날짜 검출(의도된 실패) | [before.log](before.log) |
| `python3 -I -m unittest discover -s tools/tests -p 'test_blueprint_s11_refresh.py' -v` (수정 후) | 9건 통과, 종료 0 | [focused.log](focused.log) |
| `python3 -I tools/blueprint_counts.py` | Rust 248 + doctest 3, 실제 조항 7, 변조 40, 어휘 49 일치, 종료 0 | [counts.log](counts.log) |
| `python3 -I tools/blueprint_status.py` | ADR·DEC 37개 색인 일치, 종료 0 | [status.log](status.log) |
| `python3 -I -m unittest discover -s tools/tests -p 'test_validation_test_counts.py' -v` | 역사적 42건 표기·재실행 근거·현재 표 포인터 포함 15건 통과, 종료 0 | [validation-count-tests.log](validation-count-tests.log) |
| `cargo build --locked --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir /tmp/onjeon-onto-audit5-s11` | 온톨로지 실행기 빌드 성공, 종료 0 | [ontology-build.log](ontology-build.log) |
| `ONJEON_ONTOLOGY_RUNNER=/tmp/onjeon-onto-audit5-s11/debug/ontology-case-runner python3 -I -m unittest discover -s tools/tests -v` | 1,459건: 통과, 기존 건너뜀 60건, 실패·오류 0, 종료 0 | [python-tests.log](python-tests.log) |
| `cargo test --all --locked` | 513건 통과, 실패 0, 기존 무시 1건, 종료 0 | [rust-tests.log](rust-tests.log) |
| `cargo test --locked --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir /tmp/onjeon-onto-audit5-s11` | 4건 통과, 종료 0 | [ontology-tests.log](ontology-tests.log) |
| 허용 경로·보호 문서·공백 검사 | 허용 경로만 변경, 보호 문서 diff 없음, `git diff --check` 깨끗함 | [scope.log](scope.log) |

`before.log`는 수정 전 회귀 시험이 실제로 감리 지적을 검출하는지 남긴
의도된 실패다. `focused.log`는 수정 후 같은 시험의 통과 기록이다.
Python 전체 시험의 건너뜀 60건은 기존 조건부 건너뜀이다. Rust 수는
무시된 시험을 포함한 등록 수가 아니라 실행 통과 수다.

## 범위

로컬 저장소의 문서·시험·검증 도구만 실행했다. commit·push·GitHub 호출·
비밀값 조회·R2/클라우드/프로덕션 접근은 하지 않았다. 이 증거는 문서
수치·경로·결정 색인의 회귀 검증이며, 실제 공시 데이터·소비자 화면·
P01~P19 첫 출시 완료 증거나 T-OP-08 출시 판정을 대신하지 않는다.
